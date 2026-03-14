"""FinBERT sentiment pipeline — optional dependency (transformers + torch)."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from src.core.models import SentimentScore

logger = structlog.get_logger(__name__)


def _load_finbert():
    """Attempt to load the FinBERT pipeline. Returns None if transformers/torch unavailable."""
    try:
        from transformers import pipeline  # noqa: PLC0415
        return pipeline("text-classification", model="ProsusAI/finbert", device=-1)
    except ImportError:
        logger.warning(
            "finbert.unavailable",
            message="transformers/torch not installed — FinBERT unavailable, returning empty sentiment",
        )
        return None
    except Exception:
        logger.warning("finbert.load_failed", exc_info=True)
        return None


class FinBERTSentimentPipeline:
    """Batch sentiment scorer using ProsusAI/finbert.

    Optional dependency: requires `transformers` and `torch`.
    Returns empty list gracefully when they are not installed.
    """

    def __init__(self) -> None:
        self._pipeline = None  # lazy load on first use

    def _get_pipeline(self):
        if self._pipeline is None:
            self._pipeline = _load_finbert()
        return self._pipeline

    async def score_texts(
        self,
        symbol: str,
        texts: list[str],
        source: str = "news",
    ) -> list[SentimentScore]:
        """Score a batch of texts. Returns empty list if transformers not installed.

        Label mapping:
          positive -> +score (0 to +1)
          negative -> -score (-1 to 0)
          neutral  -> 0.0
        """
        if not texts:
            return []

        pipe = self._get_pipeline()
        if pipe is None:
            return []

        from src.core.config import get_settings  # noqa: PLC0415
        settings = get_settings()
        # Gracefully handle configs that may not have .sentiment yet (pre-T13 config)
        batch_size = getattr(getattr(settings, "sentiment", None), "batch_size", 32)

        results: list[SentimentScore] = []
        now = datetime.now(timezone.utc)

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                outputs = pipe(batch, truncation=True, max_length=512)
            except Exception:
                logger.warning("finbert.score_batch_failed", symbol=symbol, exc_info=True)
                continue

            for text, output in zip(batch, outputs):
                label = output["label"].lower()
                score_raw = float(output["score"])

                if label == "positive":
                    sentiment = score_raw
                elif label == "negative":
                    sentiment = -score_raw
                else:
                    sentiment = 0.0

                results.append(
                    SentimentScore(
                        symbol=symbol,
                        timestamp=now,
                        source=source,
                        text_snippet=text[:200],
                        sentiment=sentiment,
                        confidence=score_raw,
                    )
                )

        return results
