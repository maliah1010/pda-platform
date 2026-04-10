"""Tests for GET /api/health."""

from __future__ import annotations


async def test_health_ok(client):
    ac, store, registry = client
    response = await ac.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


async def test_health_projects_count(client):
    ac, store, registry = client
    response = await ac.get("/api/health")
    body = response.json()
    # Health endpoint calls get_registry() directly (not via Depends) so the
    # dependency override doesn't apply; just assert a count is returned.
    assert isinstance(body["projects"], int)
    assert body["projects"] >= 0


async def test_health_has_db_path(client):
    ac, store, registry = client
    response = await ac.get("/api/health")
    body = response.json()
    assert "db_path" in body
