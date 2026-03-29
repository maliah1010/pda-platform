"""PDA Platform API — FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_artefacts, get_registry, get_store, settings
from .routers import (
    actions,
    classifier,
    compliance,
    currency,
    divergence,
    lessons,
    overhead,
    overrides,
    portfolio,
    projects,
    schedule,
    workflows,
)

app = FastAPI(
    title="PDA Platform API",
    version="0.1.0",
    description="Read-only REST API serving AssuranceStore data for the UDS renderer.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(projects.router)
app.include_router(portfolio.router)
app.include_router(compliance.router)
app.include_router(actions.router)
app.include_router(divergence.router)
app.include_router(schedule.router)
app.include_router(overrides.router)
app.include_router(lessons.router)
app.include_router(overhead.router)
app.include_router(workflows.router)
app.include_router(classifier.router)
app.include_router(currency.router)


@app.on_event("startup")
async def startup() -> None:
    """Warm up the singleton store and registry on startup."""
    get_store()
    get_registry()
    get_artefacts()


@app.get("/api/health", tags=["health"])
async def health() -> dict:
    """Health check endpoint."""
    registry = get_registry()
    return {
        "status": "ok",
        "projects": len(registry),
        "db_path": settings.db_path,
    }
