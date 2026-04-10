"""Tests for /api/benefits endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime


def _make_benefit(project_id: str, benefit_id: str | None = None, status: str = "PLANNED") -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "id": benefit_id or str(uuid.uuid4()),
        "project_id": project_id,
        "title": "Reduced processing time",
        "description": "Automated workflow reduces manual processing overhead.",
        "financial_type": "CASHABLE",
        "recipient_type": "GOVERNMENT",
        "status": status,
        "target_value": 500000.0,
        "created_at": now,
        "updated_at": now,
    }


async def test_get_benefits_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/benefits/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


async def test_get_benefits_populated(client):
    ac, store, registry = client
    store.upsert_benefit(_make_benefit("TEST001"))
    response = await ac.get("/api/benefits/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1


async def test_get_benefits_item_shape(client):
    ac, store, registry = client
    bid = str(uuid.uuid4())
    store.upsert_benefit(_make_benefit("TEST001", benefit_id=bid))
    response = await ac.get("/api/benefits/TEST001")
    body = response.json()
    item = body["items"][0]
    assert item["id"] == bid
    assert item["project_id"] == "TEST001"
    assert item["financial_type"] == "CASHABLE"


async def test_get_benefits_status_filter(client):
    ac, store, registry = client
    store.upsert_benefit(_make_benefit("TEST001", status="PLANNED"))
    store.upsert_benefit(_make_benefit("TEST001", status="REALISED"))
    response = await ac.get("/api/benefits/TEST001?status=PLANNED")
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["status"] == "PLANNED"


async def test_get_benefits_summary_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/benefits/TEST001/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["by_status"] == {}
    assert body["total_target_value"] == 0.0


async def test_get_benefits_summary_populated(client):
    ac, store, registry = client
    store.upsert_benefit(_make_benefit("TEST001", status="PLANNED"))
    store.upsert_benefit(_make_benefit("TEST001", status="REALISED"))
    response = await ac.get("/api/benefits/TEST001/summary")
    body = response.json()
    assert body["total"] == 2
    assert "PLANNED" in body["by_status"]
    assert "REALISED" in body["by_status"]
    assert body["total_target_value"] == 1000000.0


async def test_get_benefits_summary_by_financial_type(client):
    ac, store, registry = client
    store.upsert_benefit(_make_benefit("TEST001"))
    response = await ac.get("/api/benefits/TEST001/summary")
    body = response.json()
    assert "by_financial_type" in body
    assert "CASHABLE" in body["by_financial_type"]


async def test_get_benefit_measurements_unknown_benefit_404(client):
    ac, store, registry = client
    response = await ac.get("/api/benefits/non-existent-id/measurements")
    assert response.status_code == 404


async def test_get_benefit_measurements_known_benefit_empty(client):
    ac, store, registry = client
    bid = str(uuid.uuid4())
    store.upsert_benefit(_make_benefit("TEST001", benefit_id=bid))
    response = await ac.get(f"/api/benefits/{bid}/measurements")
    assert response.status_code == 200
    body = response.json()
    assert body["benefit_id"] == bid
    assert body["count"] == 0


async def test_get_benefit_measurements_with_data(client):
    ac, store, registry = client
    bid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    store.upsert_benefit(_make_benefit("TEST001", benefit_id=bid))
    store.upsert_benefit_measurement({
        "id": str(uuid.uuid4()),
        "benefit_id": bid,
        "project_id": "TEST001",
        "measured_at": "2026-03-01T10:00:00",
        "value": 250000.0,
        "created_at": now,
    })
    response = await ac.get(f"/api/benefits/{bid}/measurements")
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["value"] == 250000.0


async def test_get_benefits_network_empty(client):
    ac, store, registry = client
    response = await ac.get("/api/benefits/TEST001/network")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "TEST001"
    assert body["nodes"] == []
    assert body["edges"] == []


async def test_get_benefits_project_isolation(client):
    ac, store, registry = client
    store.upsert_benefit(_make_benefit("OTHER_PROJECT"))
    response = await ac.get("/api/benefits/TEST001")
    body = response.json()
    assert body["count"] == 0
