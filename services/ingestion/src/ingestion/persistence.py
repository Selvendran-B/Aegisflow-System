
"""Persist M2 transactions and graph edges against the existing M1 schema."""
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .schemas import TransactionIn


INSERT_TXN = text("""
INSERT INTO transactions (
    txn_id, external_ref, account_id, counterparty_id,
    channel, direction, amount, currency, merchant_mcc,
    country_code, device_id, ip_address, occurred_at
)
VALUES (
    :id, :external_ref, :account_id, :counterparty_id,
    :channel, :direction, :amount, :currency, :merchant_mcc,
    :country_code, :device_id, :ip_address, :ts
)
ON CONFLICT DO NOTHING
RETURNING txn_id
""")

FIND_TXN = text("""
SELECT txn_id FROM transactions
WHERE txn_id = :id OR external_ref = :external_ref
LIMIT 1
""")

UPSERT_EDGE = text("""
INSERT INTO entity_edges (
    src_type, src_id, dst_type, dst_id, edge_type, first_seen, weight
)
VALUES (
    :src_type, :src_id, :dst_type, :dst_id, :edge_type, :ts, 1
)
ON CONFLICT (src_type, src_id, dst_type, dst_id, edge_type)
DO UPDATE SET weight = entity_edges.weight + 1
""")


class UnknownEntity(ValueError):
    """A referenced account or counterparty does not exist."""


def edges_for(t: TransactionIn) -> list[dict]:
    out = []

    for kind, value, edge in (
        ("device", t.device_id, "uses_device"),
        ("ip", str(t.ip_id) if t.ip_id else None, "uses_ip"),
    ):
        if value:
            out.append({
                "src_type": "account",
                "src_id": str(t.account_id),
                "dst_type": kind,
                "dst_id": str(value),
                "edge_type": edge,
                "ts": t.ts,
            })

    if t.counterparty_id and t.channel in {"wire", "upi", "ach"}:
        out.append({
            "src_type": "account",
            "src_id": str(t.account_id),
            "dst_type": "counterparty",
            "dst_id": str(t.counterparty_id),
            "edge_type": "transfers_to",
            "ts": t.ts,
        })

    return out


class PgStore:
    def __init__(self, engine):
        self.engine = engine

    def store(self, t: TransactionIn) -> bool:
        external_ref = t.external_ref or str(t.id)
        params = {
            "id": str(t.id),
            "external_ref": external_ref,
            "account_id": str(t.account_id),
            "counterparty_id": str(t.counterparty_id) if t.counterparty_id else None,
            "channel": t.channel,
            "direction": t.direction,
            "amount": t.amount,
            "currency": t.currency,
            "merchant_mcc": t.merchant_mcc,
            "country_code": t.country_code,
            "device_id": t.device_id,
            "ip_address": str(t.ip_id) if t.ip_id else None,
            "ts": t.ts,
        }

        try:
            with self.engine.begin() as conn:
                inserted = conn.execute(INSERT_TXN, params).first() is not None

                if inserted:
                    for edge in edges_for(t):
                        conn.execute(UPSERT_EDGE, edge)
                    return True

                # Handles duplicates by txn_id OR external_ref.
                existing = conn.execute(
                    FIND_TXN,
                    {"id": str(t.id), "external_ref": external_ref},
                ).first()
                if existing is not None:
                    return False

                # A conflict occurred that wasn't one of our idempotency keys.
                raise ValueError("Transaction insert conflicted with an existing unique value")

        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23503":
                raise UnknownEntity(str(exc.orig).splitlines()[0]) from None
            raise

    def ping(self) -> bool:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True


class MemoryStore:
    """Test double with the same interface."""

    def __init__(self, known_accounts=None):
        self.rows, self.edges, self.known = {}, {}, known_accounts

    def store(self, t: TransactionIn) -> bool:
        if self.known is not None and str(t.account_id) not in self.known:
            raise UnknownEntity("account not found")

        key = str(t.id)
        external_ref = t.external_ref or key

        if key in self.rows or any(
            (row.external_ref or str(row.id)) == external_ref
            for row in self.rows.values()
        ):
            return False

        self.rows[key] = t
        for edge in edges_for(t):
            edge_key = (
                edge["src_type"], str(edge["src_id"]),
                edge["dst_type"], str(edge["dst_id"]), edge["edge_type"],
            )
            self.edges[edge_key] = self.edges.get(edge_key, 0) + 1
        return True

    def ping(self) -> bool:
        return True
