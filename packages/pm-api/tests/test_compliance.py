"""Tests for /api/compliance endpoints."""

from __future__ import annotations


async def test_compliance_history_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/compliance/TEST001/history")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["records"] == []


async def test_compliance_trend_empty_404(client):
    ac, store, registry = client
    response = await ac.get("/api/compliance/TEST001/trend")
    assert response.status_code == 404


async def test_compliance_history_populated(client):
    ac, store, registry = client
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-001",
        timestamp="2026-01-01T10:00:00",
        score=75.0,
        dimension_scores={"required": 80.0, "recommended": 65.0},
    )
    response = await ac.get("/api/compliance/TEST001/history")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    record = body["records"][0]
    assert record["project_id"] == "TEST001"
    assert record["score"] == 75.0


async def test_compliance_history_multiple_records(client):
    ac, store, registry = client
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-001",
        timestamp="2026-01-01T10:00:00",
        score=70.0,
        dimension_scores={},
    )
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-002",
        timestamp="2026-02-01T10:00:00",
        score=80.0,
        dimension_scores={},
    )
    response = await ac.get("/api/compliance/TEST001/history")
    body = response.json()
    assert body["count"] == 2


async def test_compliance_trend_populated(client):
    ac, store, registry = client
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-001",
        timestamp="2026-01-01T10:00:00",
        score=70.0,
        dimension_scores={},
    )
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-002",
        timestamp="2026-02-01T10:00:00",
        score=80.0,
        dimension_scores={},
    )
    response = await ac.get("/api/compliance/TEST001/trend")
    assert response.status_code == 200
    body = response.json()
    assert "trend" in body
    assert body["trend"] == "IMPROVING"
    assert "latest_score" in body
    assert body["latest_score"] == 80.0


async def test_compliance_trend_stable(client):
    ac, store, registry = client
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-001",
        timestamp="2026-01-01T10:00:00",
        score=75.0,
        dimension_scores={},
    )
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-002",
        timestamp="2026-02-01T10:00:00",
        score=76.0,
        dimension_scores={},
    )
    response = await ac.get("/api/compliance/TEST001/trend")
    body = response.json()
    assert body["trend"] == "STABLE"


async def test_compliance_trend_breach_detection(client):
    ac, store, registry = client
    store.insert_confidence_score(
        project_id="TEST001",
        run_id="run-001",
        timestamp="2026-01-01T10:00:00",
        score=45.0,
        dimension_scores={},
    )
    response = await ac.get("/api/compliance/TEST001/trend")
    body = response.json()
    assert body["active_breaches"] == 1
    assert body["breach_threshold"] == 60.0


async def test_compliance_history_unknown_project_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/compliance/UNKNOWN_PROJECT/history")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
