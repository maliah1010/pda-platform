"""Settings and shared dependency providers for the PDA API."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application configuration.

    All fields can be overridden via environment variables prefixed with
    ``PDA_`` (e.g. ``PDA_DB_PATH=/data/store.db``).
    """

    db_path: str = "demo_store.db"
    registry_path: str = "demo_registry.json"
    artefacts_path: str = "demo_artefacts.json"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_prefix = "PDA_"


settings = Settings()

# ---------------------------------------------------------------------------
# Path resolution helper
# ---------------------------------------------------------------------------


def _resolve(path: str) -> Path:
    """Resolve a path relative to the repo root if not absolute."""
    p = Path(path)
    if p.is_absolute():
        return p
    # When running from repo root the path is relative to CWD
    return Path.cwd() / p


# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

_store = None
_registry: Optional[dict] = None
_artefacts: Optional[dict] = None

# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_store():
    """Return the singleton AssuranceStore, initialising on first call."""
    global _store
    if _store is None:
        # Ensure pm_data_tools is importable when invoked from packages/pm-api
        _pkg_src = Path(__file__).resolve().parents[3] / "pm-data-tools" / "src"
        if str(_pkg_src) not in sys.path:
            sys.path.insert(0, str(_pkg_src))

        from pm_data_tools.db.store import AssuranceStore  # noqa: PLC0415

        _store = AssuranceStore(db_path=_resolve(settings.db_path))
    return _store


def get_registry() -> dict:
    """Return the singleton project registry dict, loading on first call."""
    global _registry
    if _registry is None:
        _registry = json.loads(_resolve(settings.registry_path).read_text())
    return _registry


def get_artefacts() -> dict:
    """Return the singleton artefacts dict, loading on first call."""
    global _artefacts
    if _artefacts is None:
        _artefacts = json.loads(_resolve(settings.artefacts_path).read_text())
    return _artefacts
