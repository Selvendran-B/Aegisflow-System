
from datetime import datetime, timezone
from uuid import uuid4

import redis
import pytest
from fastapi.testclient import TestClient

from ingestion import config, deps
from ingestion.api import routes
from ingestion.main import app
from ingestion.persistence import MemoryStore


@pytest.fixture
def client(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(deps, "store", lambda: store)
    monkeypatch.setattr(deps, "redis_client", lambda: object())
    monkeypatch.setattr(routes, "update", lambda client, event: None)

    with TestClient(app) as test_client:
        yield test_client, store


def payload(**overrides):
    data = {
        "id": str(uuid4()),
        "external_ref": f"api-{uuid4().hex}",
        "ts": datetime.now(timezone.utc).isoformat(),
        "account_id": str(uuid4()),
        "amount": "1250.50",
        "currency": "INR",
        "channel": "upi",
        "direction": "debit",
        "device_id": "device-test-001",
        "ip_id": "192.0.2.10",
        "merchant_mcc": "5411",
        "country_code": "IN",
    }
    data.update(overrides)
    return data


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_service_key_returns_401(client):
    test_client, _ = client
    response = test_client.post("/api/v1/transactions", json=payload())
    assert response.status_code == 401


def test_invalid_channel_is_rejected(client):
    test_client, _ = client
    response = test_client.post(
        "/api/v1/transactions",
        json=payload(channel="wallet"),
        headers={"X-Service-Key": config.SERVICE_KEY},
    )
    assert response.status_code == 422


def test_naive_timestamp_is_rejected(client):
    test_client, _ = client
    response = test_client.post(
        "/api/v1/transactions",
        json=payload(ts="2026-10-23T12:00:00"),
        headers={"X-Service-Key": config.SERVICE_KEY},
    )
    assert response.status_code == 422


def test_create_returns_201_and_null_decision(client):
    test_client, store = client
    body = payload()
    response = test_client.post(
        "/api/v1/transactions",
        json=body,
        headers={"X-Service-Key": config.SERVICE_KEY},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": body["id"],
        "decision": None,
        "duplicate": False,
    }
    assert body["id"] in store.rows


def test_retry_returns_200_and_duplicate(client):
    test_client, store = client
    body = payload()
    headers = {"X-Service-Key": config.SERVICE_KEY}

    first = test_client.post("/api/v1/transactions", json=body, headers=headers)
    retry = test_client.post("/api/v1/transactions", json=body, headers=headers)

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert len(store.rows) == 1


def test_redis_failure_returns_503_and_retry_can_recover(client, monkeypatch):
    test_client, store = client
    body = payload()
    headers = {"X-Service-Key": config.SERVICE_KEY}

    def fail_update(client, event):
        raise redis.ConnectionError("test Redis outage")

    monkeypatch.setattr(routes, "update", fail_update)
    failed = test_client.post("/api/v1/transactions", json=body, headers=headers)

    assert failed.status_code == 503
    assert body["id"] in store.rows

    monkeypatch.setattr(routes, "update", lambda client, event: None)
    retry = test_client.post("/api/v1/transactions", json=body, headers=headers)

    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert len(store.rows) == 1
