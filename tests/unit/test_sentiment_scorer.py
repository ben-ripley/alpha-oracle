"""Tests for the FinBERT sentiment scorer."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.sentiment_scorer import FinBERTSentimentPipeline, _load_finbert


class TestLoadFinbert:
    """Test _load_finbert lazy loader."""

    def test_returns_none_when_transformers_missing(self):
        with patch.dict(sys.modules, {"transformers": None}):
            result = _load_finbert()
        assert result is None

    def test_returns_pipeline_when_transformers_available(self):
        mock_pipeline_fn = MagicMock(return_value=MagicMock())
        mock_transformers = MagicMock()
        mock_transformers.pipeline = mock_pipeline_fn

        with patch.dict(sys.modules, {"transformers": mock_transformers}):
            result = _load_finbert()

        mock_pipeline_fn.assert_called_once_with(
            "text-classification", model="ProsusAI/finbert", device=-1
        )
        assert result is not None

    def test_returns_none_on_exception(self):
        mock_transformers = MagicMock()
        mock_transformers.pipeline.side_effect = RuntimeError("CUDA error")

        with patch.dict(sys.modules, {"transformers": mock_transformers}):
            result = _load_finbert()

        assert result is None


class TestFinBERTSentimentPipeline:
    """Test FinBERTSentimentPipeline scoring behavior."""

    @pytest.mark.asyncio
    async def test_empty_texts_returns_empty(self):
        scorer = FinBERTSentimentPipeline()
        results = await scorer.score_texts("AAPL", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pipeline(self):
        scorer = FinBERTSentimentPipeline()
        with patch.object(scorer, "_get_pipeline", return_value=None):
            results = await scorer.score_texts("AAPL", ["Apple reports strong earnings"])
        assert results == []

    @pytest.mark.asyncio
    async def test_positive_label_maps_to_positive_sentiment(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "positive", "score": 0.9}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", ["Apple beats earnings"])

        assert len(results) == 1
        assert results[0].sentiment == pytest.approx(0.9)
        assert results[0].confidence == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_negative_label_maps_to_negative_sentiment(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "negative", "score": 0.85}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", ["Apple misses earnings"])

        assert len(results) == 1
        assert results[0].sentiment == pytest.approx(-0.85)
        assert results[0].confidence == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_neutral_label_maps_to_zero(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "neutral", "score": 0.7}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", ["Apple holds annual meeting"])

        assert len(results) == 1
        assert results[0].sentiment == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_batch_processing(self):
        scorer = FinBERTSentimentPipeline()
        texts = [f"Article {i}" for i in range(5)]
        outputs = [{"label": "positive", "score": 0.8}] * 5
        mock_pipe = MagicMock(return_value=outputs)

        mock_settings = MagicMock()
        mock_settings.sentiment.batch_size = 3  # force batching

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe), \
             patch("src.core.config.get_settings", return_value=mock_settings):
            results = await scorer.score_texts("AAPL", texts)

        assert len(results) == 5
        # Should have called pipe twice: [0:3] and [3:5]
        assert mock_pipe.call_count == 2

    @pytest.mark.asyncio
    async def test_result_symbol_and_source_set(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "positive", "score": 0.6}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("TSLA", ["Tesla soars"], source="filing")

        assert results[0].symbol == "TSLA"
        assert results[0].source == "filing"

    @pytest.mark.asyncio
    async def test_text_snippet_truncated_to_200_chars(self):
        scorer = FinBERTSentimentPipeline()
        long_text = "x" * 500
        mock_pipe = MagicMock(return_value=[{"label": "neutral", "score": 0.5}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", [long_text])

        assert len(results[0].text_snippet) == 200

    @pytest.mark.asyncio
    async def test_timestamp_is_utc(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "neutral", "score": 0.5}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", ["test"])

        assert results[0].timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_batch_exception_skipped(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(side_effect=RuntimeError("CUDA OOM"))

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", ["Article about Apple"])

        assert results == []

    @pytest.mark.asyncio
    async def test_optional_dep_fallback_no_crash(self):
        """Full end-to-end: if transformers is not importable, score_texts returns []."""
        scorer = FinBERTSentimentPipeline()

        with patch.dict(sys.modules, {"transformers": None}):
            # Reset cached pipeline
            scorer._pipeline = None
            results = await scorer.score_texts("AAPL", ["Some news"])

        assert results == []

    @pytest.mark.asyncio
    async def test_lazy_load_on_first_call(self):
        scorer = FinBERTSentimentPipeline()
        assert scorer._pipeline is None

        mock_pipe = MagicMock(return_value=[{"label": "neutral", "score": 0.5}])
        with patch("src.agents.sentiment_scorer._load_finbert", return_value=mock_pipe):
            await scorer.score_texts("AAPL", ["test"])

        assert scorer._pipeline is mock_pipe

    @pytest.mark.asyncio
    async def test_pipeline_reused_across_calls(self):
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "neutral", "score": 0.5}])

        with patch("src.agents.sentiment_scorer._load_finbert", return_value=mock_pipe) as mock_load:
            await scorer.score_texts("AAPL", ["first call"])
            await scorer.score_texts("AAPL", ["second call"])

        # _load_finbert should only be called once
        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_sentiment_scores_not_news_articles(self):
        from src.core.models import SentimentScore
        scorer = FinBERTSentimentPipeline()
        mock_pipe = MagicMock(return_value=[{"label": "positive", "score": 0.7}])

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", ["positive news"])

        assert all(isinstance(r, SentimentScore) for r in results)

    @pytest.mark.asyncio
    async def test_sentiment_within_valid_range(self):
        scorer = FinBERTSentimentPipeline()
        outputs = [
            {"label": "positive", "score": 0.95},
            {"label": "negative", "score": 0.80},
            {"label": "neutral", "score": 0.60},
        ]
        mock_pipe = MagicMock(return_value=outputs)
        texts = ["bullish", "bearish", "neutral"]

        with patch.object(scorer, "_get_pipeline", return_value=mock_pipe):
            results = await scorer.score_texts("AAPL", texts)

        for r in results:
            assert -1.0 <= r.sentiment <= 1.0
            assert 0.0 <= r.confidence <= 1.0
