"""Tests for /api/gate-readiness endpoints."""

from __future__ import annotations

import json
import uuid


def _make_gate_assessment(project_id: str, assessment_id: str | None = None, gate: str = "GATE_2") -> dict:
    result = {"criteria": [], "summary": "Test assessment result"}
    return {
        "id": assessment_id or str(uuid.uuid4()),
        "project_id": project_id,
        "gate": gate,
        "readiness": "AMBER",
        "composite_score": 68.5,
        "assessed_at": "2026-03-15T10:00:00",
        "result_json": json.dumps(result),
    }


async def test_get_gate_readiness_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/gate-readiness/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


async def test_get_gate_readiness_latest_empty_404(client):
    ac, store, registry = client
    response = await ac.get("/api/gate-readiness/TEST001/latest")
    assert response.status_code == 404


async def test_get_gate_readiness_detail_unknown_404(client):
    ac, store, registry = client
    response = await ac.get("/api/gate-readiness/non-existent-id/detail")
    assert response.status_code == 404


async def test_get_gate_readiness_populated(client):
    ac, store, registry = client
    store.insert_gate_readiness_assessment(_make_gate_assessment("TEST001"))
    response = await ac.get("/api/gate-readiness/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1


async def test_get_gate_readiness_result_json_expanded(client):
    ac, store, registry = client
    store.insert_gate_readiness_assessment(_make_gate_assessment("TEST001"))
    response = await ac.get("/api/gate-readiness/TEST001")
    body = response.json()
    item = body["items"][0]
    assert "result_json" not in item
    assert "result" in item
    assert isinstance(item["result"], dict)
    assert "summary" in item["result"]


async def test_get_gate_readiness_item_shape(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.insert_gate_readiness_assessment(_make_gate_assessment("TEST001", assessment_id=aid))
    response = await ac.get("/api/gate-readiness/TEST001")
    body = response.json()
    item = body["items"][0]
    assert item["id"] == aid
    assert item["project_id"] == "TEST001"
    assert item["gate"] == "GATE_2"
    assert item["readiness"] == "AMBER"
    assert item["composite_score"] == 68.5


async def test_get_gate_readiness_filter_by_gate(client):
    ac, store, registry = client
    store.insert_gate_readiness_assessment(_make_gate_assessment("TEST001", gate="GATE_2"))
    store.insert_gate_readiness_assessment(_make_gate_assessment("TEST001", gate="GATE_4"))
    response = await ac.get("/api/gate-readiness/TEST001?gate=GATE_2")
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["gate"] == "GATE_2"


async def test_get_gate_readiness_latest_returns_most_recent(client):
    ac, store, registry = client
    store.insert_gate_readiness_assessment(
        _make_gate_assessment("TEST001") | {"assessed_at": "2026-01-01T10:00:00", "composite_score": 60.0}
    )
    store.insert_gate_readiness_assessment(
        _make_gate_assessment("TEST001") | {"assessed_at": "2026-03-01T10:00:00", "composite_score": 75.0}
    )
    response = await ac.get("/api/gate-readiness/TEST001/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["composite_score"] == 75.0
    assert "result" in body


async def test_get_gate_readiness_detail_by_id(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.insert_gate_readiness_assessment(_make_gate_assessment("TEST001", assessment_id=aid))
    response = await ac.get(f"/api/gate-readiness/{aid}/detail")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == aid
    assert body["project_id"] == "TEST001"
    assert "result" in body
    assert "result_json" not in body


async def test_get_gate_readiness_project_isolation(client):
    ac, store, registry = client
    store.insert_gate_readiness_assessment(_make_gate_assessment("OTHER_PROJECT"))
    response = await ac.get("/api/gate-readiness/TEST001")
    body = response.json()
    assert body["count"] == 0
