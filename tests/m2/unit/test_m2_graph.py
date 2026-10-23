
"""Graph features on a ring fixture.

A, B and C share device D; A is known fraud.
E is disconnected and shares device F.
"""
from aegis_ml.features.graph_features import build_graph, compute


EDGES = [
    ("account", "A", "device", "D", 1),
    ("account", "B", "device", "D", 3),
    ("account", "C", "device", "D", 1),
    ("account", "E", "device", "F", 1),
    ("account", "B", "device", "D", 1),
]


def test_build_graph_is_undirected_and_accumulates_weights():
    graph = build_graph(EDGES)

    assert graph.has_edge("acct:A", "dev:D")
    assert graph.has_edge("dev:D", "acct:A")
    assert graph["acct:B"]["dev:D"]["weight"] == 4.0


def test_connected_component_sizes():
    graph = build_graph(EDGES)
    features = compute(graph, ["A"]).set_index("entity_id")

    # A, B, C and D are connected.
    assert features.loc["A", "component_size"] == 4
    assert features.loc["B", "component_size"] == 4
    assert features.loc["C", "component_size"] == 4

    # E and F form a separate component.
    assert features.loc["E", "component_size"] == 2


def test_distance_to_nearest_fraud_account():
    graph = build_graph(EDGES)
    features = compute(graph, ["A"]).set_index("entity_id")

    assert features.loc["A", "dist_to_fraud"] == 0
    assert features.loc["B", "dist_to_fraud"] == 2
    assert features.loc["C", "dist_to_fraud"] == 2
    assert features.loc["E", "dist_to_fraud"] == -1


def test_risk_rank_is_finite_and_higher_near_fraud():
    graph = build_graph(EDGES)
    features = compute(graph, ["A"]).set_index("entity_id")

    assert features["risk_rank"].map(
        lambda value: value >= 0 and value < float("inf")
    ).all()
    assert features.loc["A", "risk_rank"] > features.loc["E", "risk_rank"]


def test_no_fraud_accounts_produces_default_graph_scores():
    graph = build_graph(EDGES)
    features = compute(graph, []).set_index("entity_id")

    assert (features["dist_to_fraud"] == -1).all()
    assert (features["risk_rank"] == 0.0).all()
