"""Tests for /api/actions endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime


def _make_recommendation(project_id: str, status: str = "OPEN", rec_id: str | None = None) -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "id": rec_id or str(uuid.uuid4()),
        "project_id": project_id,
        "text": "Test recommendation",
        "category": "GOVERNANCE",
        "source_review_id": "review-001",
        "review_date": "2026-01-15",
        "status": status,
        "confidence": 0.85,
        "created_at": now,
    }


async def test_get_actions_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/actions/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


async def test_get_actions_populated(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("TEST001", status="OPEN"))
    response = await ac.get("/api/actions/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1


async def test_get_actions_status_filter_open(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("TEST001", status="OPEN"))
    store.upsert_recommendation(_make_recommendation("TEST001", status="CLOSED"))
    response = await ac.get("/api/actions/TEST001?status=OPEN")
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["status"] == "OPEN"


async def test_get_actions_status_filter_closed(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("TEST001", status="OPEN"))
    store.upsert_recommendation(_make_recommendation("TEST001", status="CLOSED"))
    response = await ac.get("/api/actions/TEST001?status=CLOSED")
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["status"] == "CLOSED"


async def test_get_actions_no_filter_returns_all(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("TEST001", status="OPEN"))
    store.upsert_recommendation(_make_recommendation("TEST001", status="CLOSED"))
    store.upsert_recommendation(_make_recommendation("TEST001", status="RECURRING"))
    response = await ac.get("/api/actions/TEST001")
    body = response.json()
    assert body["count"] == 3


async def test_get_actions_summary_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/actions/TEST001/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["open"] == 0
    assert body["closed"] == 0
    assert body["recurring"] == 0
    assert body["closure_rate"] == 0.0


async def test_get_actions_summary_closure_rate(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("TEST001", status="OPEN"))
    store.upsert_recommendation(_make_recommendation("TEST001", status="CLOSED"))
    store.upsert_recommendation(_make_recommendation("TEST001", status="CLOSED"))
    response = await ac.get("/api/actions/TEST001/summary")
    body = response.json()
    assert body["total"] == 3
    assert body["open"] == 1
    assert body["closed"] == 2
    assert abs(body["closure_rate"] - round(2 / 3, 3)) < 0.001


async def test_get_actions_summary_recurring(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("TEST001", status="RECURRING"))
    response = await ac.get("/api/actions/TEST001/summary")
    body = response.json()
    assert body["recurring"] == 1


async def test_get_actions_project_isolation(client):
    ac, store, registry = client
    store.upsert_recommendation(_make_recommendation("OTHER_PROJECT", status="OPEN"))
    response = await ac.get("/api/actions/TEST001")
    body = response.json()
    assert body["count"] == 0
