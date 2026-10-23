
"""Hourly graph feature job (FR-4).

Builds an undirected graph and computes account-level graph features.
Publishes Redis features and point-in-time database snapshots.
"""
import argparse
import os
import time
from datetime import datetime, timezone

import networkx as nx
import pandas as pd

from . import definitions as D

PREFIX = {
    "account": "acct",
    "device": "dev",
    "ip": "ip",
    "merchant": "mer",
    "counterparty": "counterparty",
}

EDGES_SQL = """
SELECT src_type, src_id, dst_type, dst_id, weight
FROM entity_edges
"""

FRAUD_SQL = """
SELECT entity_id
FROM known_fraud_entities
WHERE entity_type = 'account' AND confirmed_at <= %s
"""

SNAP_SQL = """
INSERT INTO graph_feature_snapshots
    (entity_id, computed_at, component_size, dist_to_fraud, risk_rank)
VALUES (%s, %s, %s, %s, %s)
"""


def node(entity_type: str, entity_id) -> str:
    prefix = PREFIX.get(entity_type)
    if prefix is None:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    return f"{prefix}:{entity_id}"


def build_graph(edges) -> nx.Graph:
    """Build an undirected graph; edge weights represent link strength."""
    graph = nx.Graph()

    for src_type, src_id, dst_type, dst_id, weight in edges:
        a = node(src_type, src_id)
        b = node(dst_type, dst_id)
        w = float(weight or 1.0)

        if graph.has_edge(a, b):
            graph[a][b]["weight"] += w
        else:
            graph.add_edge(a, b, weight=w)

    return graph


def compute(graph: nx.Graph, fraud_accounts) -> pd.DataFrame:
    accounts = [n for n in graph if n.startswith("acct:")]

    component_size = {}
    for component in nx.connected_components(graph):
        for n in component:
            component_size[n] = len(component)

    sources = [
        node("account", account_id)
        for account_id in fraud_accounts
        if node("account", account_id) in graph
    ]

    distances = {}
    ranks = {}

    if sources:
        # Every edge costs one hop; weight measures strength, not distance.
        distances = nx.multi_source_dijkstra_path_length(
            graph, sources, weight=lambda u, v, data: 1
        )
        ranks = nx.pagerank(
            graph,
            alpha=0.85,
            personalization={source: 1.0 for source in sources},
            weight="weight",
        )

    return pd.DataFrame({
        "entity_id": [account.split(":", 1)[1] for account in accounts],
        "component_size": [int(component_size[account]) for account in accounts],
        "dist_to_fraud": [
            int(distances[account]) if account in distances else -1
            for account in accounts
        ],
        "risk_rank": [
            float(ranks.get(account, 0.0)) for account in accounts
        ],
    })


def publish(conn, redis_client, features: pd.DataFrame,
            computed_at: datetime) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            SNAP_SQL,
            [
                (
                    row.entity_id,
                    computed_at,
                    row.component_size,
                    row.dist_to_fraud,
                    row.risk_rank,
                )
                for row in features.itertuples(index=False)
            ],
        )
    conn.commit()

    pipeline = redis_client.pipeline(transaction=False)
    for row in features.itertuples(index=False):
        key = f"gfeat:acct:{row.entity_id}"
        pipeline.hset(key, mapping={
            "component_size": row.component_size,
            "dist_to_fraud": row.dist_to_fraud,
            "risk_rank": repr(row.risk_rank),
            "computed_at": computed_at.isoformat(),
        })
        pipeline.expire(key, D.GRAPH_TTL_S)

    pipeline.execute()


def run_once(conn, redis_client) -> int:
    now = datetime.now(timezone.utc)
    graph = build_graph(conn.execute(EDGES_SQL).fetchall())
    fraud = [
        row[0] for row in conn.execute(FRAUD_SQL, (now,)).fetchall()
    ]
    features = compute(graph, fraud)
    publish(conn, redis_client, features, now)
    return len(features)


def main():
    import psycopg
    import redis

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-s", type=int, default=3600)
    args = parser.parse_args()

    dsn = os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    redis_client = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    while True:
        started = time.monotonic()
        try:
            with psycopg.connect(dsn) as conn:
                count = run_once(conn, redis_client)
                print(f"graph features for {count} accounts", flush=True)
        except Exception as exc:
            print(f"graph pass failed: {exc}", flush=True)

        if args.once:
            break
        time.sleep(max(0, args.interval_s - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
