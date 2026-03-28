"""Shared SQLite persistence store for pm-data-tools assurance modules.

All tables use CREATE TABLE IF NOT EXISTS so multiple features can initialise
the store safely without conflicts.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

DEFAULT_DB_PATH: Path = Path.home() / ".pm_data_tools" / "store.db"


class AssuranceStore:
    """Shared SQLite store for pm-data-tools assurance data.

    Manages two tables:

    - ``confidence_scores``: NISTA compliance score history per project/run.
    - ``recommendations``: Extracted assurance recommendations with status.

    All schema operations use ``CREATE TABLE IF NOT EXISTS`` so callers that
    only use one feature do not depend on the other feature's tables existing.

    Example::

        store = AssuranceStore()
        store.insert_confidence_score(
            project_id="PROJ-001",
            run_id="run-42",
            timestamp="2026-03-23T09:00:00",
            score=78.5,
            dimension_scores={"required": 85.0, "recommended": 60.0},
        )
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialise the store and create tables if absent.

        Args:
            db_path: Path to the SQLite database file.  Defaults to
                ``~/.pm_data_tools/store.db``.
        """
        self.db_path: Path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()
        logger.debug("assurance_store_ready", db_path=str(self.db_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with row-factory set.

        Returns:
            A configured :class:`sqlite3.Connection`.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        """Create all tables if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS confidence_scores (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id       TEXT    NOT NULL,
                    run_id           TEXT    NOT NULL,
                    timestamp        TEXT    NOT NULL,
                    score            REAL    NOT NULL,
                    dimension_scores TEXT    NOT NULL,
                    UNIQUE(project_id, run_id)
                );

                CREATE TABLE IF NOT EXISTS recommendations (
                    id               TEXT PRIMARY KEY,
                    project_id       TEXT NOT NULL,
                    text             TEXT NOT NULL,
                    category         TEXT NOT NULL,
                    source_review_id TEXT NOT NULL,
                    review_date      TEXT NOT NULL,
                    status           TEXT NOT NULL,
                    owner            TEXT,
                    recurrence_of    TEXT,
                    confidence       REAL NOT NULL,
                    created_at       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS divergence_snapshots (
                    id               TEXT PRIMARY KEY,
                    project_id       TEXT NOT NULL,
                    review_id        TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    sample_scores    TEXT NOT NULL,
                    signal_type      TEXT NOT NULL,
                    timestamp        TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # Confidence scores
    # ------------------------------------------------------------------

    def insert_confidence_score(
        self,
        project_id: str,
        run_id: str,
        timestamp: str,
        score: float,
        dimension_scores: dict[str, float],
    ) -> None:
        """Persist a NISTA confidence score record.

        Uses ``INSERT OR REPLACE`` so re-running the same ``run_id`` updates
        the stored values rather than raising a unique-constraint error.

        Args:
            project_id: Identifier for the project being validated.
            run_id: Unique identifier for this validation run.
            timestamp: ISO-8601 timestamp string of the run.
            score: Overall compliance score (0-100).
            dimension_scores: Per-dimension scores keyed by dimension name.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO confidence_scores
                    (project_id, run_id, timestamp, score, dimension_scores)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    run_id,
                    timestamp,
                    score,
                    json.dumps(dimension_scores),
                ),
            )
        logger.debug(
            "confidence_score_persisted",
            project_id=project_id,
            run_id=run_id,
            score=score,
        )

    def get_confidence_scores(self, project_id: str) -> list[dict[str, object]]:
        """Retrieve all confidence score records for a project, oldest first.

        Args:
            project_id: The project identifier.

        Returns:
            List of row dicts with keys: id, project_id, run_id, timestamp,
            score, dimension_scores (already deserialised from JSON).
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, run_id, timestamp, score, dimension_scores
                FROM confidence_scores
                WHERE project_id = ?
                ORDER BY timestamp ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()

        result: list[dict[str, object]] = []
        for row in rows:
            record = dict(row)
            raw = record.get("dimension_scores")
            record["dimension_scores"] = json.loads(raw) if isinstance(raw, str) else {}
            result.append(record)
        return result

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def upsert_recommendation(self, data: dict[str, object]) -> None:
        """Insert or replace a recommendation record.

        Args:
            data: Dict with keys matching the ``recommendations`` table columns.
                Must include ``id``, ``project_id``, ``text``, ``category``,
                ``source_review_id``, ``review_date``, ``status``,
                ``confidence``, ``created_at``.  ``owner`` and
                ``recurrence_of`` are optional.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO recommendations
                    (id, project_id, text, category, source_review_id,
                     review_date, status, owner, recurrence_of, confidence,
                     created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["project_id"],
                    data["text"],
                    data["category"],
                    data["source_review_id"],
                    data["review_date"],
                    data["status"],
                    data.get("owner"),
                    data.get("recurrence_of"),
                    data["confidence"],
                    data["created_at"],
                ),
            )
        logger.debug(
            "recommendation_persisted",
            id=data["id"],
            project_id=data["project_id"],
        )

    def get_recommendations(
        self,
        project_id: str,
        status_filter: Optional[str] = None,
    ) -> list[dict[str, object]]:
        """Retrieve recommendations for a project, optionally filtered by status.

        Args:
            project_id: The project identifier.
            status_filter: Optional status value to filter by (e.g. ``"OPEN"``).

        Returns:
            List of recommendation row dicts ordered by review_date ascending.
        """
        if status_filter is not None:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM recommendations
                    WHERE project_id = ? AND status = ?
                    ORDER BY review_date ASC
                    """,
                    (project_id, status_filter),
                )
                rows = cursor.fetchall()
        else:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM recommendations
                    WHERE project_id = ?
                    ORDER BY review_date ASC
                    """,
                    (project_id,),
                )
                rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def update_recommendation_status(self, rec_id: str, status: str) -> None:
        """Update the status of a single recommendation.

        Args:
            rec_id: The recommendation ``id``.
            status: New status string (e.g. ``"CLOSED"``).
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE recommendations SET status = ? WHERE id = ?",
                (status, rec_id),
            )
        logger.debug("recommendation_status_updated", id=rec_id, status=status)

    # ------------------------------------------------------------------
    # Divergence snapshots (P4)
    # ------------------------------------------------------------------

    def insert_divergence_snapshot(
        self,
        snapshot_id: str,
        project_id: str,
        review_id: str,
        confidence_score: float,
        sample_scores: list[float],
        signal_type: str,
        timestamp: str,
    ) -> None:
        """Persist a confidence divergence snapshot.

        Uses ``INSERT OR REPLACE`` so re-submitting the same ``snapshot_id``
        updates the record rather than raising a unique-constraint error.

        Args:
            snapshot_id: UUID for this snapshot.
            project_id: The project identifier.
            review_id: The review identifier.
            confidence_score: Overall consensus confidence score (0–1).
            sample_scores: Individual per-sample confidence scores.
            signal_type: Signal classification (e.g. ``"STABLE"``).
            timestamp: ISO-8601 timestamp string of the check.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO divergence_snapshots
                    (id, project_id, review_id, confidence_score,
                     sample_scores, signal_type, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    project_id,
                    review_id,
                    confidence_score,
                    json.dumps(sample_scores),
                    signal_type,
                    timestamp,
                ),
            )
        logger.debug(
            "divergence_snapshot_persisted",
            snapshot_id=snapshot_id,
            project_id=project_id,
            signal_type=signal_type,
        )

    def get_divergence_history(self, project_id: str) -> list[dict[str, object]]:
        """Retrieve all divergence snapshots for a project, oldest first.

        Args:
            project_id: The project identifier.

        Returns:
            List of row dicts with keys: id, project_id, review_id,
            confidence_score, sample_scores (deserialised list), signal_type,
            timestamp.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, review_id, confidence_score,
                       sample_scores, signal_type, timestamp
                FROM divergence_snapshots
                WHERE project_id = ?
                ORDER BY timestamp ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()

        result: list[dict[str, object]] = []
        for row in rows:
            record = dict(row)
            raw = record.get("sample_scores")
            record["sample_scores"] = json.loads(raw) if isinstance(raw, str) else []
            result.append(record)
        return result
