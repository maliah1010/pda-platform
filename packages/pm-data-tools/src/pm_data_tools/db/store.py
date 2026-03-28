"""Shared SQLite persistence store for pm-data-tools assurance modules.

All tables use CREATE TABLE IF NOT EXISTS so multiple features can initialise
the store safely without conflicts.

Tables:

- ``confidence_scores``: NISTA compliance score history (P2).
- ``recommendations``: Extracted review actions (P3).
- ``divergence_snapshots``: AI confidence divergence records (P4).
- ``review_schedule_recommendations``: Adaptive review scheduling history (P5).
- ``override_decisions``: Governance override decision log (P6).
- ``lessons_learned``: Lessons learned knowledge base (P7).
- ``assurance_activities``: Assurance activity effort records (P8).
- ``overhead_analyses``: Persisted overhead analysis results (P8).
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

                CREATE TABLE IF NOT EXISTS review_schedule_recommendations (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id       TEXT    NOT NULL,
                    timestamp        TEXT    NOT NULL,
                    urgency          TEXT    NOT NULL,
                    recommended_date TEXT    NOT NULL,
                    composite_score  REAL    NOT NULL,
                    signals_json     TEXT    NOT NULL,
                    rationale        TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS override_decisions (
                    id                    TEXT PRIMARY KEY,
                    project_id            TEXT NOT NULL,
                    override_type         TEXT NOT NULL,
                    decision_date         TEXT NOT NULL,
                    authoriser            TEXT NOT NULL,
                    rationale             TEXT NOT NULL,
                    overridden_finding_id TEXT,
                    overridden_value      TEXT,
                    override_value        TEXT,
                    conditions_json       TEXT NOT NULL,
                    evidence_refs_json    TEXT NOT NULL,
                    outcome               TEXT NOT NULL,
                    outcome_date          TEXT,
                    outcome_notes         TEXT,
                    created_at            TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lessons_learned (
                    id                 TEXT PRIMARY KEY,
                    project_id         TEXT NOT NULL,
                    title              TEXT NOT NULL,
                    description        TEXT NOT NULL,
                    category           TEXT NOT NULL,
                    sentiment          TEXT NOT NULL,
                    project_type       TEXT,
                    project_phase      TEXT,
                    department         TEXT,
                    tags_json          TEXT NOT NULL,
                    date_recorded      TEXT NOT NULL,
                    recorded_by        TEXT,
                    impact_description TEXT,
                    created_at         TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assurance_activities (
                    id                  TEXT PRIMARY KEY,
                    project_id          TEXT NOT NULL,
                    activity_type       TEXT NOT NULL,
                    description         TEXT NOT NULL,
                    date                TEXT NOT NULL,
                    effort_hours        REAL NOT NULL,
                    participants        INTEGER NOT NULL,
                    artefacts_reviewed  TEXT NOT NULL,
                    findings_count      INTEGER NOT NULL,
                    confidence_before   REAL,
                    confidence_after    REAL,
                    created_at          TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS overhead_analyses (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id      TEXT NOT NULL,
                    timestamp       TEXT NOT NULL,
                    analysis_json   TEXT NOT NULL
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

    # ------------------------------------------------------------------
    # Review schedule recommendations (P5)
    # ------------------------------------------------------------------

    def insert_schedule_recommendation(
        self,
        project_id: str,
        timestamp: str,
        urgency: str,
        recommended_date: str,
        composite_score: float,
        signals_json: str,
        rationale: str,
    ) -> None:
        """Persist an adaptive review scheduling recommendation.

        Args:
            project_id: The project identifier.
            timestamp: ISO-8601 timestamp string of the recommendation.
            urgency: Urgency classification (e.g. ``"IMMEDIATE"``).
            recommended_date: ISO-8601 date string of the suggested review date.
            composite_score: Weighted composite severity score (0–1).
            signals_json: JSON-serialised list of contributing signals.
            rationale: Human-readable explanation of the recommendation.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO review_schedule_recommendations
                    (project_id, timestamp, urgency, recommended_date,
                     composite_score, signals_json, rationale)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    timestamp,
                    urgency,
                    recommended_date,
                    composite_score,
                    signals_json,
                    rationale,
                ),
            )
        logger.debug(
            "schedule_recommendation_persisted",
            project_id=project_id,
            urgency=urgency,
            recommended_date=recommended_date,
        )

    def get_schedule_history(self, project_id: str) -> list[dict[str, object]]:
        """Retrieve all scheduling recommendations for a project, oldest first.

        Args:
            project_id: The project identifier.

        Returns:
            List of row dicts.  ``signals_json`` is returned as a raw string.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, timestamp, urgency, recommended_date,
                       composite_score, signals_json, rationale
                FROM review_schedule_recommendations
                WHERE project_id = ?
                ORDER BY timestamp ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Override decisions (P6)
    # ------------------------------------------------------------------

    def upsert_override_decision(self, data: dict[str, object]) -> None:
        """Insert or replace an override decision record.

        Args:
            data: Dict with keys matching the ``override_decisions`` table
                columns.  Must include ``id``, ``project_id``,
                ``override_type``, ``decision_date``, ``authoriser``,
                ``rationale``, ``conditions_json``, ``evidence_refs_json``,
                ``outcome``, ``created_at``.  All other fields are optional.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO override_decisions
                    (id, project_id, override_type, decision_date, authoriser,
                     rationale, overridden_finding_id, overridden_value,
                     override_value, conditions_json, evidence_refs_json,
                     outcome, outcome_date, outcome_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["project_id"],
                    data["override_type"],
                    data["decision_date"],
                    data["authoriser"],
                    data["rationale"],
                    data.get("overridden_finding_id"),
                    data.get("overridden_value"),
                    data.get("override_value"),
                    data["conditions_json"],
                    data["evidence_refs_json"],
                    data["outcome"],
                    data.get("outcome_date"),
                    data.get("outcome_notes"),
                    data["created_at"],
                ),
            )
        logger.debug(
            "override_decision_persisted",
            id=data["id"],
            project_id=data["project_id"],
        )

    def get_override_decisions(
        self,
        project_id: str,
        override_type: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> list[dict[str, object]]:
        """Retrieve override decisions, optionally filtered by type and/or outcome.

        Args:
            project_id: The project identifier.
            override_type: Optional override type string to filter by.
            outcome: Optional outcome string to filter by.

        Returns:
            List of row dicts ordered by decision_date ascending.  List fields
            (``conditions_json``, ``evidence_refs_json``) are returned as raw
            JSON strings.
        """
        if override_type is not None and outcome is not None:
            sql = """
                SELECT * FROM override_decisions
                WHERE project_id = ? AND override_type = ? AND outcome = ?
                ORDER BY decision_date ASC
            """
            params: tuple[object, ...] = (project_id, override_type, outcome)
        elif override_type is not None:
            sql = """
                SELECT * FROM override_decisions
                WHERE project_id = ? AND override_type = ?
                ORDER BY decision_date ASC
            """
            params = (project_id, override_type)
        elif outcome is not None:
            sql = """
                SELECT * FROM override_decisions
                WHERE project_id = ? AND outcome = ?
                ORDER BY decision_date ASC
            """
            params = (project_id, outcome)
        else:
            sql = """
                SELECT * FROM override_decisions
                WHERE project_id = ?
                ORDER BY decision_date ASC
            """
            params = (project_id,)

        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_override_outcome(
        self,
        override_id: str,
        outcome: str,
        outcome_date: Optional[str] = None,
        outcome_notes: Optional[str] = None,
    ) -> None:
        """Update the outcome of a previously logged override decision.

        Args:
            override_id: The override decision ``id``.
            outcome: New outcome string (e.g. ``"SIGNIFICANT_IMPACT"``).
            outcome_date: Optional ISO-8601 date string when the outcome
                was observed.
            outcome_notes: Optional human-readable notes about the outcome.
        """
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE override_decisions
                SET outcome = ?, outcome_date = ?, outcome_notes = ?
                WHERE id = ?
                """,
                (outcome, outcome_date, outcome_notes, override_id),
            )
        logger.debug(
            "override_outcome_updated",
            id=override_id,
            outcome=outcome,
        )

    # ------------------------------------------------------------------
    # Lessons learned (P7)
    # ------------------------------------------------------------------

    def upsert_lesson(self, data: dict[str, object]) -> None:
        """Insert or replace a lessons learned record.

        Args:
            data: Dict with keys matching the ``lessons_learned`` table
                columns.  Must include ``id``, ``project_id``, ``title``,
                ``description``, ``category``, ``sentiment``,
                ``tags_json``, ``date_recorded``, and ``created_at``.
                All other fields are optional.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO lessons_learned
                    (id, project_id, title, description, category, sentiment,
                     project_type, project_phase, department, tags_json,
                     date_recorded, recorded_by, impact_description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["project_id"],
                    data["title"],
                    data["description"],
                    data["category"],
                    data["sentiment"],
                    data.get("project_type"),
                    data.get("project_phase"),
                    data.get("department"),
                    data["tags_json"],
                    data["date_recorded"],
                    data.get("recorded_by"),
                    data.get("impact_description"),
                    data["created_at"],
                ),
            )
        logger.debug(
            "lesson_persisted",
            id=data["id"],
            project_id=data["project_id"],
        )

    def get_lessons(
        self,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
        sentiment: Optional[str] = None,
    ) -> list[dict[str, object]]:
        """Retrieve lessons, optionally filtered by project, category, and sentiment.

        Args:
            project_id: Optional project identifier filter.
            category: Optional category string filter.
            sentiment: Optional sentiment string filter (e.g. ``"NEGATIVE"``).

        Returns:
            List of row dicts ordered by ``date_recorded`` descending.
        """
        conditions: list[str] = []
        params: list[object] = []

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        if category is not None:
            conditions.append("category = ?")
            params.append(category)
        if sentiment is not None:
            conditions.append("sentiment = ?")
            params.append(sentiment)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM lessons_learned {where} ORDER BY date_recorded DESC"

        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_all_lessons(self) -> list[dict[str, object]]:
        """Retrieve all lessons from the corpus, unfiltered.

        Returns:
            List of row dicts ordered by ``date_recorded`` descending.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM lessons_learned ORDER BY date_recorded DESC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def search_lessons_keyword(self, query: str) -> list[dict[str, object]]:
        """SQL LIKE search across title, description, and tags_json.

        Args:
            query: The search string; matched case-insensitively via
                SQLite's ``LIKE`` operator.

        Returns:
            Matching row dicts ordered by ``date_recorded`` descending.
        """
        like = f"%{query}%"
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM lessons_learned
                WHERE title LIKE ? OR description LIKE ? OR tags_json LIKE ?
                ORDER BY date_recorded DESC
                """,
                (like, like, like),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Assurance activities (P8)
    # ------------------------------------------------------------------

    def upsert_assurance_activity(self, data: dict[str, object]) -> None:
        """Insert or replace an assurance activity record.

        Args:
            data: Dict with keys matching the ``assurance_activities`` table
                columns.  Must include ``id``, ``project_id``,
                ``activity_type``, ``description``, ``date``,
                ``effort_hours``, ``participants``, ``artefacts_reviewed``,
                ``findings_count``, and ``created_at``.
                ``confidence_before`` and ``confidence_after`` are optional.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assurance_activities
                    (id, project_id, activity_type, description, date,
                     effort_hours, participants, artefacts_reviewed,
                     findings_count, confidence_before, confidence_after,
                     created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["id"],
                    data["project_id"],
                    data["activity_type"],
                    data["description"],
                    data["date"],
                    data["effort_hours"],
                    data["participants"],
                    data["artefacts_reviewed"],
                    data["findings_count"],
                    data.get("confidence_before"),
                    data.get("confidence_after"),
                    data["created_at"],
                ),
            )
        logger.debug(
            "assurance_activity_persisted",
            id=data["id"],
            project_id=data["project_id"],
        )

    def get_assurance_activities(
        self,
        project_id: str,
        activity_type: Optional[str] = None,
    ) -> list[dict[str, object]]:
        """Retrieve assurance activities for a project.

        Args:
            project_id: The project identifier.
            activity_type: Optional activity type string to filter by.

        Returns:
            List of row dicts ordered by date ascending.
        """
        if activity_type is not None:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM assurance_activities
                    WHERE project_id = ? AND activity_type = ?
                    ORDER BY date ASC
                    """,
                    (project_id, activity_type),
                )
                rows = cursor.fetchall()
        else:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM assurance_activities
                    WHERE project_id = ?
                    ORDER BY date ASC
                    """,
                    (project_id,),
                )
                rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def insert_overhead_analysis(
        self,
        project_id: str,
        timestamp: str,
        analysis_json: str,
    ) -> None:
        """Persist a complete overhead analysis result.

        Args:
            project_id: The project identifier.
            timestamp: ISO-8601 timestamp string of the analysis.
            analysis_json: Full :class:`~pm_data_tools.assurance.overhead.OverheadAnalysis`
                serialised as JSON.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO overhead_analyses
                    (project_id, timestamp, analysis_json)
                VALUES (?, ?, ?)
                """,
                (project_id, timestamp, analysis_json),
            )
        logger.debug(
            "overhead_analysis_persisted",
            project_id=project_id,
            timestamp=timestamp,
        )

    def get_overhead_history(self, project_id: str) -> list[dict[str, object]]:
        """Retrieve all overhead analysis results for a project.

        Args:
            project_id: The project identifier.

        Returns:
            List of row dicts ordered by timestamp ascending.
            ``analysis_json`` is returned as a raw JSON string.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, timestamp, analysis_json
                FROM overhead_analyses
                WHERE project_id = ?
                ORDER BY timestamp ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]
