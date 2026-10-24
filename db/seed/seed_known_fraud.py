"""Seed pre-T0 confirmed fraud accounts without inventing labels."""

import os
import sys
from datetime import datetime

import psycopg

LABEL_TABLE = "ground_truth_labels"

def main() -> int:
    dsn = os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1
    )

    with psycopg.connect(dsn) as conn:
        exists = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = %s
            )
            """,
            (LABEL_TABLE,),
        ).fetchone()[0]

        if not exists:
            print(
                "ERROR: ground_truth_labels does not exist. "
                "No known-fraud records were changed. "
                "Provide a verified fraud-label source before seeding.",
                file=sys.stderr,
            )
            return 2

        columns = {
            row[0]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                """,
                (LABEL_TABLE,),
            ).fetchall()
        }

        required = {"transaction_id", "is_fraud"}
        if not required.issubset(columns):
            print(
                f"ERROR: label table is missing columns: "
                f"{sorted(required - columns)}. No records were changed.",
                file=sys.stderr,
            )
            return 2

        cutoff_env = os.getenv("KNOWN_FRAUD_CUTOFF")
        if cutoff_env:
            cutoff = datetime.fromisoformat(
                cutoff_env.replace("Z", "+00:00")
            )
        else:
            cutoff = conn.execute(
                """
                SELECT percentile_disc(0.10)
                WITHIN GROUP (ORDER BY occurred_at)
                FROM transactions
                """
            ).fetchone()[0]

        if cutoff is None:
            print("ERROR: no transactions available to determine T0.",
                  file=sys.stderr)
            return 2

        rows = conn.execute(
            """
            SELECT t.account_id, MIN(t.occurred_at) AS confirmed_at
            FROM ground_truth_labels g
            JOIN transactions t ON t.txn_id = g.transaction_id
            WHERE g.is_fraud IS TRUE
              AND t.occurred_at < %s
            GROUP BY t.account_id
            """,
            (cutoff,),
        ).fetchall()

        conn.execute(
            "DELETE FROM known_fraud_entities WHERE source = 'seed_pre_T0'"
        )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO known_fraud_entities
                    (entity_type, entity_id, confirmed_at, source)
                VALUES ('account', %s, %s, 'seed_pre_T0')
                ON CONFLICT DO NOTHING
                """,
                rows,
            )

    print(f"T0 = {cutoff.isoformat()} -> {len(rows)} known-fraud accounts seeded")
    print("M3 training data must start at or after T0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())