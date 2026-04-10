"""Tests for /api/armm endpoints."""

from __future__ import annotations

import json
import uuid


def _make_armm_assessment(project_id: str, assessment_id: str | None = None) -> dict:
    return {
        "id": assessment_id or str(uuid.uuid4()),
        "project_id": project_id,
        "assessed_at": "2026-03-01T10:00:00",
        "assessed_by": "test-assessor",
        "overall_level": 2,
        "overall_score_pct": 55.0,
        "criteria_total": 20,
        "criteria_met": 11,
        "topic_scores_json": json.dumps({}),
        "topic_levels_json": json.dumps({}),
        "dimension_scores_json": json.dumps({}),
        "dimension_levels_json": json.dumps({}),
        "dimension_blocking_json": json.dumps({}),
        "notes": "",
    }


async def test_get_armm_report_empty_404(client):
    ac, store, registry = client
    response = await ac.get("/api/armm/TEST001")
    assert response.status_code == 404


async def test_get_armm_history_empty_404(client):
    ac, store, registry = client
    response = await ac.get("/api/armm/TEST001/history")
    assert response.status_code == 404


async def test_get_armm_report_populated(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.upsert_armm_assessment(_make_armm_assessment("TEST001", assessment_id=aid))
    response = await ac.get("/api/armm/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "TEST001"
    assert body["overall_level"] == 2
    assert body["overall_score_pct"] == 55.0
    assert "dimensions" in body


async def test_get_armm_history_populated(client):
    ac, store, registry = client
    store.upsert_armm_assessment(_make_armm_assessment("TEST001"))
    response = await ac.get("/api/armm/TEST001/history")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["project_id"] == "TEST001"


async def test_get_armm_history_multiple_records(client):
    ac, store, registry = client
    store.upsert_armm_assessment(
        _make_armm_assessment("TEST001") | {"assessed_at": "2026-01-01T10:00:00"}
    )
    store.upsert_armm_assessment(
        _make_armm_assessment("TEST001") | {"assessed_at": "2026-02-01T10:00:00"}
    )
    response = await ac.get("/api/armm/TEST001/history")
    body = response.json()
    assert body["count"] == 2


async def test_get_armm_history_item_shape(client):
    ac, store, registry = client
    aid = str(uuid.uuid4())
    store.upsert_armm_assessment(_make_armm_assessment("TEST001", assessment_id=aid))
    response = await ac.get("/api/armm/TEST001/history")
    body = response.json()
    item = body["items"][0]
    assert item["id"] == aid
    assert item["overall_level"] == 2
    assert isinstance(item["dimension_levels"], dict)
    assert isinstance(item["topic_levels"], dict)


async def test_get_armm_portfolio_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/armm/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["average_score_pct"] == 0.0


async def test_get_armm_portfolio_populated(client):
    ac, store, registry = client
    store.upsert_armm_assessment(_make_armm_assessment("TEST001"))
    response = await ac.get("/api/armm/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["average_score_pct"] == 55.0


async def test_get_armm_report_criteria_counts(client):
    ac, store, registry = client
    store.upsert_armm_assessment(_make_armm_assessment("TEST001"))
    response = await ac.get("/api/armm/TEST001")
    body = response.json()
    assert body["criteria_total"] == 20
    assert body["criteria_met"] == 11
