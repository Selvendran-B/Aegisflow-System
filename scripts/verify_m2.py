
"""M2 definition-of-done checks.

Needs the stack up, migrations applied, and DATABASE_URL/REDIS_URL exported.
Exit 0 means ready to tag v0.2.0-M2.
"""

import os
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

FILES = [
    "ml/src/aegis_ml/features/definitions.py",
    "ml/src/aegis_ml/features/offline.py",
    "ml/src/aegis_ml/features/graph_features.py",
    "services/ingestion/src/ingestion/config.py",
    "services/ingestion/src/ingestion/schemas.py",
    "services/ingestion/src/ingestion/persistence.py",
    "services/ingestion/src/ingestion/online_features.py",
    "services/ingestion/src/ingestion/deps.py",
    "services/ingestion/src/ingestion/main.py",
    "services/ingestion/src/ingestion/api/routes.py",
    "services/ingestion/Dockerfile",
    "services/ingestion/requirements.txt",
    "ml/Dockerfile.graph",
    "ml/requirements-graph.txt",
    "db/migrations/versions/m2_0001_feature_store.py",
    "db/seed/seed_known_fraud.py",
    "docker-compose.m2.yml",
    "docs/adr/0001-feature-store.md",
    "tests/m2/unit/test_m2_parity.py",
    "tests/m2/unit/test_m2_offline.py",
    "tests/m2/unit/test_m2_graph.py",
    "tests/m2/api/test_m2_api.py",
    "tests/m2/integration/test_m2_db.py",
]

results = []


def ok(name, condition, detail=""):
    results.append(bool(condition))
    status = "OK " if condition else "XX "
    print(f"[{status}] {name} {detail}")


for filename in FILES:
    ok(f"file {filename}", (ROOT / filename).exists())

env = os.environ.copy()
env["PYTHONPATH"] = os.pathsep.join(
    [
        str(ROOT / "services" / "ingestion" / "src"),
        str(ROOT / "ml" / "src"),
        str(ROOT),
    ]
)

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/m2/unit",
        "tests/m2/api",
    ],
    cwd=ROOT,
    env=env,
)
ok("unit + API tests", result.returncode == 0)

if not os.getenv("DATABASE_URL"):
    ok("DATABASE_URL exported", False, "(set it before running verifier)")
else:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/m2/integration"],
        cwd=ROOT,
        env=env,
    )
    ok("integration tests (edges, FK, graph job)", result.returncode == 0)

    try:
        import psycopg
        import redis

        dsn = os.environ["DATABASE_URL"].replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

        with psycopg.connect(dsn) as connection:
            transaction_count = connection.execute(
                "SELECT count(*) FROM transactions"
            ).fetchone()[0]
            ok("transactions stored", transaction_count > 0, f"({transaction_count})")

            duplicate_edges = connection.execute(
                """
                SELECT count(*)
                FROM (
                    SELECT 1
                    FROM entity_edges
                    GROUP BY src_type, src_id, dst_type, dst_id, edge_type
                    HAVING count(*) > 1
                ) duplicates
                """
            ).fetchone()[0]
            ok("no duplicate edges", duplicate_edges == 0)

            snapshot = connection.execute(
                """
                SELECT max(computed_at) > now() - interval '65 minutes'
                FROM graph_feature_snapshots
                """
            ).fetchone()[0]
            ok("graph snapshot within the last hour", bool(snapshot))

            known_fraud_count = connection.execute(
                "SELECT count(*) FROM known_fraud_entities"
            ).fetchone()[0]
            ok(
                "known fraud seeded (pre-T0)",
                known_fraud_count > 0,
                f"({known_fraud_count})",
            )

        redis_client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0")
        )
        ok(
            "feat:acct:* keys present",
            next(redis_client.scan_iter("feat:acct:*", count=1000), None) is not None,
        )
        ok(
            "gfeat:acct:* keys present",
            next(redis_client.scan_iter("gfeat:acct:*", count=1000), None) is not None,
        )

    except Exception as exc:
        ok("database and Redis verification", False, str(exc)[:160])

base_url = os.getenv("INGEST_URL", "http://localhost:8001")

for path in ("/health", "/ready"):
    try:
        status_code = urllib.request.urlopen(
            base_url + path, timeout=5
        ).status
    except Exception as exc:
        status_code = str(exc)[:60]

    ok(f"ingestion {path}", status_code == 200, f"({status_code})")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
