"""Tests for /api/projects endpoints."""

from __future__ import annotations


async def test_list_projects_returns_registry(client):
    ac, store, registry = client
    response = await ac.get("/api/projects")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert len(body["items"]) == 1


async def test_list_projects_item_has_name(client):
    ac, store, registry = client
    response = await ac.get("/api/projects")
    body = response.json()
    item = body["items"][0]
    assert item["name"] == "Test Project"


async def test_get_project_known(client):
    ac, store, registry = client
    response = await ac.get("/api/projects/TEST001")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Test Project"
    assert body["department"] == "HMRC"


async def test_get_project_unknown_404(client):
    ac, store, registry = client
    response = await ac.get("/api/projects/DOES_NOT_EXIST")
    assert response.status_code == 404


async def test_get_project_summary_known(client):
    ac, store, registry = client
    response = await ac.get("/api/projects/TEST001/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "TEST001"
    assert body["name"] == "Test Project"
    assert "latest_score" in body
    assert "open_actions" in body


async def test_get_project_summary_unknown_404(client):
    ac, store, registry = client
    response = await ac.get("/api/projects/UNKNOWN/summary")
    assert response.status_code == 404
