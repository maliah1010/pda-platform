"""Shared fixtures for the PDA Platform API test suite."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pm_api.config import get_artefacts, get_registry, get_store
from pm_api.main import app


@pytest_asyncio.fixture
async def client(tmp_path):
    """Async HTTP client wired to a fresh in-memory SQLite store."""
    import sys
    from pathlib import Path

    _pkg_src = Path(__file__).resolve().parents[3] / "pm-data-tools" / "src"
    if str(_pkg_src) not in sys.path:
        sys.path.insert(0, str(_pkg_src))

    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore(db_path=tmp_path / "test.db")

    registry = {
        "TEST001": {
            "name": "Test Project",
            "department": "HMRC",
            "domain": "COMPLICATED",
        }
    }
    artefacts: dict = {}

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_artefacts] = lambda: artefacts

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, store, registry

    app.dependency_overrides.clear()
