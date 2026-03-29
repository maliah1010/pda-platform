"""Recurrence detection for assurance recommendations using sentence embeddings.

When sentence-transformers is available, :class:`RecurrenceDetector` uses
cosine similarity between recommendation texts to identify recommendations that
recur across review cycles.  When the library is unavailable the detector
falls back gracefully: recurrence detection is skipped and a warning is logged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:  # pragma: no cover
    SENTENCE_TRANSFORMERS_AVAILABLE = False

if TYPE_CHECKING:
    from .models import ReviewAction


class RecurrenceDetector:
    """Detect recurring recommendations across project review cycles.

    Uses sentence-transformer embeddings and cosine similarity to identify
    new recommendations that semantically match OPEN recommendations from
    prior review cycles.  When a match is found the new recommendation's
    status is set to :attr:`~.models.ReviewActionStatus.RECURRING` and
    :attr:`~.models.Recommendation.recurrence_of` is set to the prior
    recommendation's ``id``.

    If ``sentence-transformers`` is not installed, recurrence detection is
    silently skipped (a ``structlog`` warning is emitted) and the new
    recommendations are returned unchanged.

    Example::

        detector = RecurrenceDetector(similarity_threshold=0.85)
        updated = detector.detect_recurrences(
            new_recommendations=new_recs,
            prior_recommendations=prior_recs,
        )
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        """Initialise the recurrence detector.

        Args:
            similarity_threshold: Cosine similarity above which two
                recommendations are considered the same (default 0.85).
            model_name: Name of the sentence-transformer model to load.
        """
        self._threshold = similarity_threshold
        self._model_name = model_name
        self._model: Optional[object] = None  # lazy-loaded

    def _get_model(self) -> "SentenceTransformer":
        """Lazily load the sentence-transformer model.

        Returns:
            The loaded :class:`~sentence_transformers.SentenceTransformer`.
        """
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model  # type: ignore[return-value]

    def detect_recurrences(
        self,
        new_recommendations: "list[ReviewAction]",
        prior_recommendations: "list[ReviewAction]",
    ) -> "list[ReviewAction]":
        """Mark new recommendations as recurring where a prior match is found.

        Recommendations from ``new_recommendations`` are compared against
        ``prior_recommendations`` using cosine similarity.  The first prior
        recommendation whose similarity exceeds the threshold is used as the
        recurrence source.

        If ``sentence-transformers`` is unavailable the input list is returned
        unchanged and a warning is logged.

        Args:
            new_recommendations: Newly extracted recommendations to check.
            prior_recommendations: OPEN recommendations from prior review
                cycles for the same project.

        Returns:
            The ``new_recommendations`` list, potentially with some items
            updated to ``RECURRING`` status and ``recurrence_of`` set.
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning(
                "recurrence_detection_skipped",
                reason="sentence-transformers not installed",
            )
            return new_recommendations

        if not prior_recommendations or not new_recommendations:
            return new_recommendations

        from .models import ReviewActionStatus

        model = self._get_model()

        prior_texts = [r.text for r in prior_recommendations]
        new_texts = [r.text for r in new_recommendations]

        prior_embeddings = np.array(model.encode(prior_texts))  # type: ignore[attr-defined]
        new_embeddings = np.array(model.encode(new_texts))  # type: ignore[attr-defined]

        # Normalise for cosine similarity via dot product
        prior_norms = np.linalg.norm(prior_embeddings, axis=1, keepdims=True)
        new_norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)

        prior_normed = prior_embeddings / np.where(prior_norms == 0, 1, prior_norms)
        new_normed = new_embeddings / np.where(new_norms == 0, 1, new_norms)

        similarity_matrix = new_normed @ prior_normed.T  # shape: (new, prior)

        updated: list[ReviewAction] = []
        for idx, rec in enumerate(new_recommendations):
            best_sim = float(np.max(similarity_matrix[idx]))
            if best_sim >= self._threshold:
                best_prior_idx = int(np.argmax(similarity_matrix[idx]))
                prior_id = prior_recommendations[best_prior_idx].id
                rec = rec.model_copy(
                    update={
                        "status": ReviewActionStatus.RECURRING,
                        "recurrence_of": prior_id,
                    }
                )
                logger.info(
                    "recurrence_detected",
                    new_text=rec.text[:60],
                    prior_id=prior_id,
                    similarity=best_sim,
                )
            updated.append(rec)

        return updated
