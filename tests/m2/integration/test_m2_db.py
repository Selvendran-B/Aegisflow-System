
"""Database integration tests against the existing M1 schema.

Requires DATABASE_URL and a migrated PostgreSQL database.
Creates isolated test rows and cleans them up afterwards.
"""
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="needs DATABASE_URL and the running stack",
)

import psycopg  # noqa: E402
import redis  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from aegis_ml.features import graph_features as G  # noqa: E402
from ingestion.persistence import PgStore, UnknownEntity  # noqa: E402
from ingestion.schemas import TransactionIn  # noqa: E402


@pytest.fixture()
def conn():
    dsn = os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(dsn) as connection:
        yield connection


@pytest.fixture()
def ring(conn):
    """Three isolated accounts connected through one device."""
    customer_ids = [uuid.uuid4() for _ in range(3)]
    account_ids = [uuid.uuid4() for _ in range(3)]
    device_id = f"it-device-{uuid.uuid4()}"
    redis_client = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    try:
        for customer_id, account_id in zip(customer_ids, account_ids):
            conn.execute(
                """
                INSERT INTO customers
                    (customer_id, external_ref, full_name, country_code)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    customer_id,
                    f"it-{uuid.uuid4()}",
                    "M2 Integration Test",
                    "IN",
                ),
            )
            conn.execute(
                """
                INSERT INTO accounts
                    (account_id, customer_id, account_number,
                     account_type, opened_on)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    account_id,
                    customer_id,
                    f"IT{uuid.uuid4().hex[:32]}",
                    "savings",
                    date(2026, 1, 1),
                ),
            )

        # This is test-only data, not a real fraud label.
        conn.execute(
            """
            INSERT INTO known_fraud_entities
                (entity_type, entity_id, confirmed_at, source)
            VALUES ('account', %s, %s, 'it_test')
            """,
            (account_ids[0], datetime(2026, 8, 1, tzinfo=timezone.utc)),
        )
        conn.commit()
        yield account_ids, device_id

    finally:
        # Remove only rows associated with these generated test IDs.
        ids = [str(account_id) for account_id in account_ids]
        conn.rollback()
        conn.execute(
            """
            DELETE FROM graph_feature_snapshots
            WHERE entity_id = ANY(%s::uuid[])
            """,
            (ids,),
        )
        conn.execute(
            """
            DELETE FROM entity_edges
            WHERE src_id = ANY(%s::text[])
               OR dst_id = ANY(%s::text[])
               OR dst_id = %s
            """,
            (ids, ids, device_id),
        )
        conn.execute(
            "DELETE FROM transactions WHERE account_id = ANY(%s::uuid[])",
            (ids,),
        )
        conn.execute(
            """
            DELETE FROM known_fraud_entities
            WHERE source = 'it_test'
              AND entity_id = ANY(%s::uuid[])
            """,
            (ids,),
        )
        conn.execute(
            "DELETE FROM accounts WHERE account_id = ANY(%s::uuid[])",
            (ids,),
        )
        conn.execute(
            "DELETE FROM customers WHERE customer_id = ANY(%s::uuid[])",
            ([str(customer_id) for customer_id in customer_ids],),
        )
        conn.commit()

        try:
            redis_client.delete(
                *[f"gfeat:acct:{account_id}" for account_id in account_ids]
            )
        finally:
            redis_client.close()


def txn(account_id, device_id, minute):
    return TransactionIn(
        id=uuid.uuid4(),
        account_id=account_id,
        device_id=device_id,
        ts=datetime(2026, 9, 1, 12, minute, tzinfo=timezone.utc),
        amount=Decimal("10.00"),
        currency="INR",
        channel="card",
        direction="debit",
    )


def test_store_is_idempotent_and_upserts_edges(conn, ring):
    (account_a, _, _), device_id = ring
    engine = create_engine(os.environ["DATABASE_URL"])

    try:
        store = PgStore(engine)
        first = txn(account_a, device_id, 0)

        assert store.store(first) is True
        assert store.store(first) is False
        assert store.store(txn(account_a, device_id, 1)) is True

        weight = conn.execute(
            """
            SELECT weight
            FROM entity_edges
            WHERE src_type = 'account'
              AND src_id = %s
              AND dst_type = 'device'
              AND dst_id = %s
              AND edge_type = 'uses_device'
            """,
            (str(account_a), device_id),
        ).fetchone()[0]

        assert weight == 2

        with pytest.raises(UnknownEntity):
            store.store(txn(uuid.uuid4(), device_id, 2))
    finally:
        engine.dispose()


def test_graph_job_publishes_snapshots_and_redis(conn, ring):
    (account_a, account_b, account_c), device_id = ring
    engine = create_engine(os.environ["DATABASE_URL"])
    client = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    try:
        client.ping()
        store = PgStore(engine)

        for minute, account_id in enumerate(
            (account_a, account_b, account_c), start=10
        ):
            assert store.store(txn(account_id, device_id, minute)) is True

        G.run_once(conn, client)

        row = conn.execute(
            """
            SELECT component_size, dist_to_fraud
            FROM graph_feature_snapshots
            WHERE entity_id = %s
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (account_b,),
        ).fetchone()

        assert row is not None
        assert row[0] >= 4
        assert row[1] == 2

        key = f"gfeat:acct:{account_b}"
        assert client.hget(key, "dist_to_fraud") == b"2"

        ttl = client.ttl(key)
        assert 0 < ttl <= 7200
    finally:
        engine.dispose()
        client.close()


def test_unique_edge_index_exists(conn):
    result = conn.execute(
        """
        SELECT 1
        FROM pg_indexes
        WHERE indexname = 'uq_entity_edges_key'
        """
    ).fetchone()

    assert result is not None
