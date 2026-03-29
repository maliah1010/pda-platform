"""Lessons router — /api/lessons (P7)."""

from __future__ import annotations

import json
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..config import get_store

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


def _deserialise(record: dict) -> dict:
    """Deserialise tags_json field."""
    raw = record.get("tags_json")
    record["tags"] = json.loads(raw) if isinstance(raw, str) else []
    return record


@router.get("")
async def list_lessons(
    category: Optional[str] = Query(default=None),
    sentiment: Optional[str] = Query(default=None),
    store=Depends(get_store),
) -> dict:
    """All lessons in the corpus, optionally filtered by category or sentiment."""
    records = store.get_lessons(category=category, sentiment=sentiment)
    items = [_deserialise(r) for r in records]
    return {"count": len(items), "items": items}


@router.get("/search")
async def search_lessons(
    q: str = Query(..., description="Keyword search across title, description, tags"),
    store=Depends(get_store),
) -> dict:
    """Keyword search across lessons corpus."""
    records = store.search_lessons_keyword(q)
    items = [_deserialise(r) for r in records]
    return {"query": q, "count": len(items), "items": items}


@router.get("/patterns")
async def lesson_patterns(store=Depends(get_store)) -> dict:
    """Corpus-wide pattern summary: counts by category, sentiment, department."""
    records = store.get_all_lessons()
    by_category: Counter = Counter(r["category"] for r in records)
    by_sentiment: Counter = Counter(r["sentiment"] for r in records)
    by_department: Counter = Counter(r["department"] for r in records if r.get("department"))

    return {
        "total": len(records),
        "by_category": dict(by_category),
        "by_sentiment": dict(by_sentiment),
        "by_department": dict(by_department),
    }
