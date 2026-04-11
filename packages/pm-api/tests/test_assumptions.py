"""Tests for /api/assumptions endpoints."""

from __future__ import annotations

import uuid
from datetime import date


def _make_assumption(project_id: str, assumption_id: str | None = None) -> dict:
    return {
        "id": assumption_id or str(uuid.uuid4()),
        "project_id": project_id,
        "text": "Team capacity remains stable at 80% utilisation.",
        "category": "RESOURCE",
        "baseline_value": 80.0,
        "current_value": 78.0,
        "unit": "percent",
        "tolerance_pct": 10.0,
        "source": "MANUAL",
        "dependencies": "[]",
        "created_date": date.today().isoformat(),
    }


async def test_get_assumptions_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/assumptions/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


async def test_get_assumptions_populated(client):
    ac, store, registry = client
    store.upsert_assumption(_make_assumption("TEST001"))
    response = await ac.get("/api/assumptions/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1


async def test_get_assumptions_item_shape(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.upsert_assumption(_make_assumption("TEST001", assumption_id=aid))
    response = await ac.get("/api/assumptions/TEST001")
    body = response.json()
    item = body["items"][0]
    assert item["id"] == aid
    assert item["project_id"] == "TEST001"
    assert item["category"] == "RESOURCE"


async def test_get_assumption_health_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/assumptions/TEST001/health")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "TEST001"
    assert body["total_assumptions"] == 0


async def test_get_assumption_health_populated(client):
    ac, store, registry = client
    store.upsert_assumption(_make_assumption("TEST001"))
    response = await ac.get("/api/assumptions/TEST001/health")
    assert response.status_code == 200
    body = response.json()
    assert body["total_assumptions"] == 1
    assert "drift_results" in body
    assert "by_severity" in body


async def test_get_stale_assumptions_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/assumptions/TEST001/stale")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0


async def test_get_validation_history_unknown_assumption_404(client):
    ac, store, registry = client
    response = await ac.get("/api/assumptions/non-existent-id/history")
    assert response.status_code == 404


async def test_get_validation_history_known_assumption_empty(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.upsert_assumption(_make_assumption("TEST001", assumption_id=aid))
    response = await ac.get(f"/api/assumptions/{aid}/history")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["assumption_id"] == aid


async def test_get_validation_history_with_validations(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.upsert_assumption(_make_assumption("TEST001", assumption_id=aid))
    store.insert_assumption_validation({
        "id": str(uuid.uuid4()),
        "assumption_id": aid,
        "validated_at": "2026-03-01T10:00:00",
        "previous_value": 80.0,
        "new_value": 78.0,
        "source": "MANUAL",
        "drift_pct": 2.5,
        "severity": "MINOR",
    })
    response = await ac.get(f"/api/assumptions/{aid}/history")
    body = response.json()
    assert body["count"] == 1
    record = body["items"][0]
    assert record["assumption_id"] == aid
    assert record["new_value"] == 78.0
