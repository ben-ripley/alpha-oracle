"""Tests for Phase 3 scheduling jobs: daily_sentiment, daily_briefing,
weekly_options_flow, weekly_trends."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scheduling.jobs import (
    daily_briefing_job,
    daily_sentiment_job,
    weekly_options_flow_job,
    weekly_trends_job,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_redis(*, done_exists: bool = False) -> AsyncMock:
    mr = AsyncMock()
    mr.exists.return_value = 1 if done_exists else 0
    mr.sismember.return_value = False
    # set(nx=True) returns None if key exists, True if set — simulates atomic lock
    mr.set = AsyncMock(side_effect=lambda *a, **kw: None if (done_exists and kw.get("nx")) else True)
    mr.get = AsyncMock(return_value=None)
    mr.publish = AsyncMock()
    return mr


def _mock_settings(agent_enabled: bool = True, max_articles: int = 20) -> MagicMock:
    settings = MagicMock()
    settings.agent.enabled = agent_enabled
    settings.sentiment.max_articles_per_symbol = max_articles
    return settings


def _mock_universe(symbols: list[str]) -> AsyncMock:
    mu = AsyncMock()
    mu.get_symbols.return_value = symbols
    return mu


# ---------------------------------------------------------------------------
# daily_sentiment_job
# ---------------------------------------------------------------------------

class TestDailySentimentJob:

    @pytest.mark.asyncio
    async def test_skips_when_agent_disabled(self):
        mock_redis = _mock_redis()
        with patch("src.core.config.get_settings", return_value=_mock_settings(agent_enabled=False)), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)):
            await daily_sentiment_job()

        mock_redis.exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_done_key_exists(self):
        mock_redis = _mock_redis(done_exists=True)
        mock_universe = _mock_universe(["AAPL"])

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe):
            await daily_sentiment_job()

        # Universe should not be consulted when done key exists
        mock_universe.get_symbols.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_news_and_scores_sentiment(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL"])

        mock_news_adapter = AsyncMock()
        mock_article = MagicMock()
        mock_article.summary = "Apple beats earnings"
        mock_article.title = "Apple Q4 results"
        mock_news_adapter.get_news.return_value = [mock_article]

        mock_scorer = AsyncMock()
        mock_score = MagicMock()
        mock_scorer.score_texts.return_value = [mock_score]

        mock_storage = AsyncMock()

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.news_adapter.NewsAdapter", return_value=mock_news_adapter), \
             patch("src.agents.sentiment_scorer.FinBERTSentimentPipeline", return_value=mock_scorer), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await daily_sentiment_job()

        mock_news_adapter.get_news.assert_called_once_with("AAPL", limit=20)
        mock_scorer.score_texts.assert_called_once()
        mock_storage.store_sentiment.assert_called_once_with([mock_score])

    @pytest.mark.asyncio
    async def test_sets_done_key_after_completion(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL"])

        mock_news_adapter = AsyncMock()
        mock_news_adapter.get_news.return_value = []

        mock_scorer = AsyncMock()
        mock_storage = AsyncMock()

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.news_adapter.NewsAdapter", return_value=mock_news_adapter), \
             patch("src.agents.sentiment_scorer.FinBERTSentimentPipeline", return_value=mock_scorer), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await daily_sentiment_job()

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "jobs:daily_sentiment:" in call_args[0][0]
        assert ":done" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_skips_symbol_with_no_news(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL", "MSFT"])

        mock_news_adapter = AsyncMock()
        mock_news_adapter.get_news.return_value = []

        mock_scorer = AsyncMock()
        mock_storage = AsyncMock()

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.news_adapter.NewsAdapter", return_value=mock_news_adapter), \
             patch("src.agents.sentiment_scorer.FinBERTSentimentPipeline", return_value=mock_scorer), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await daily_sentiment_job()

        mock_scorer.score_texts.assert_not_called()
        mock_storage.store_sentiment.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_after_symbol_error(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL", "MSFT"])

        mock_news_adapter = AsyncMock()
        mock_article = MagicMock()
        mock_article.summary = "news"
        mock_article.title = "title"
        mock_news_adapter.get_news.side_effect = [RuntimeError("API down"), [mock_article]]

        mock_scorer = AsyncMock()
        mock_scorer.score_texts.return_value = []
        mock_storage = AsyncMock()

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.news_adapter.NewsAdapter", return_value=mock_news_adapter), \
             patch("src.agents.sentiment_scorer.FinBERTSentimentPipeline", return_value=mock_scorer), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await daily_sentiment_job()  # must not raise

        # Second symbol should still be processed
        assert mock_news_adapter.get_news.call_count == 2


# ---------------------------------------------------------------------------
# daily_briefing_job
# ---------------------------------------------------------------------------

class TestDailyBriefingJob:

    @pytest.mark.asyncio
    async def test_skips_when_agent_disabled(self):
        mock_redis = _mock_redis()
        with patch("src.core.config.get_settings", return_value=_mock_settings(agent_enabled=False)), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)):
            await daily_briefing_job()

        mock_redis.exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_briefing_already_exists(self):
        mock_redis = _mock_redis(done_exists=True)

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)):
            await daily_briefing_job()

        # set is called once for the lock attempt (nx=True), but should not store briefing data
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert kwargs.get("nx") is True  # Only the lock attempt, not a briefing store
        mock_redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_agent_and_stores_briefing(self):
        mock_redis = _mock_redis()

        mock_briefing = MagicMock()
        mock_briefing.model_dump_json.return_value = '{"date": "2026-03-13"}'

        mock_result = MagicMock()
        mock_result.output = mock_briefing

        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result

        mock_broker = AsyncMock()
        mock_portfolio = MagicMock()
        mock_portfolio.positions = {}
        mock_broker.get_portfolio.return_value = mock_portfolio

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.agents.briefing.PortfolioReviewAgent", return_value=mock_agent), \
             patch("src.execution.broker_adapters.paper_stub.PaperStubBroker", return_value=mock_broker):
            await daily_briefing_job()

        mock_agent.run.assert_called_once()
        # set called twice: once for the lock (nx=True), once for the briefing data
        assert mock_redis.set.call_count == 2
        mock_redis.publish.assert_called_once()
        publish_channel = mock_redis.publish.call_args[0][0]
        assert publish_channel == "agent:briefing"

    @pytest.mark.asyncio
    async def test_no_publish_when_agent_returns_none(self):
        mock_redis = _mock_redis()

        mock_result = MagicMock()
        mock_result.output = None
        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result

        mock_broker = AsyncMock()
        mock_portfolio = MagicMock()
        mock_portfolio.positions = {}
        mock_broker.get_portfolio.return_value = mock_portfolio

        with patch("src.core.config.get_settings", return_value=_mock_settings()), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.agents.briefing.PortfolioReviewAgent", return_value=mock_agent), \
             patch("src.execution.broker_adapters.paper_stub.PaperStubBroker", return_value=mock_broker):
            await daily_briefing_job()

        # set called once for the lock only — no briefing data stored when output is None
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert kwargs.get("nx") is True
        mock_redis.publish.assert_not_called()


# ---------------------------------------------------------------------------
# weekly_options_flow_job
# ---------------------------------------------------------------------------

class TestWeeklyOptionsFlowJob:

    @pytest.mark.asyncio
    async def test_skips_when_done_key_exists(self):
        mock_redis = _mock_redis(done_exists=True)
        mock_universe = _mock_universe(["AAPL"])

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe):
            await weekly_options_flow_job()

        mock_universe.get_symbols.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_and_stores_options_flow(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL", "MSFT"])

        mock_record = MagicMock()
        mock_adapter = AsyncMock()
        mock_adapter.get_options_flow.return_value = [mock_record]

        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.options_flow_adapter.OptionsFlowAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_options_flow_job()

        assert mock_adapter.get_options_flow.call_count == 2
        assert mock_storage.store_options_flow.call_count == 2

    @pytest.mark.asyncio
    async def test_sets_done_key_after_completion(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL"])
        mock_adapter = AsyncMock()
        mock_adapter.get_options_flow.return_value = []
        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.options_flow_adapter.OptionsFlowAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_options_flow_job()

        mock_redis.set.assert_called_once()
        done_key = mock_redis.set.call_args[0][0]
        assert "jobs:weekly_options_flow:" in done_key
        assert ":done" in done_key

    @pytest.mark.asyncio
    async def test_continues_after_symbol_error(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL", "MSFT"])
        mock_adapter = AsyncMock()
        mock_adapter.get_options_flow.side_effect = [RuntimeError("stub error"), [MagicMock()]]
        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.options_flow_adapter.OptionsFlowAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_options_flow_job()  # must not raise

        assert mock_adapter.get_options_flow.call_count == 2


# ---------------------------------------------------------------------------
# weekly_trends_job
# ---------------------------------------------------------------------------

class TestWeeklyTrendsJob:

    @pytest.mark.asyncio
    async def test_skips_when_done_key_exists(self):
        mock_redis = _mock_redis(done_exists=True)
        mock_universe = _mock_universe(["AAPL"])

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe):
            await weekly_trends_job()

        mock_universe.get_symbols.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_and_stores_trends(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL", "MSFT"])

        mock_record = MagicMock()
        mock_adapter = AsyncMock()
        mock_adapter.get_trends.return_value = [mock_record]

        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.google_trends_adapter.GoogleTrendsAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_trends_job()

        assert mock_adapter.get_trends.call_count == 2
        assert mock_storage.store_trends.call_count == 2

    @pytest.mark.asyncio
    async def test_sets_done_key_after_completion(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL"])
        mock_adapter = AsyncMock()
        mock_adapter.get_trends.return_value = []
        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.google_trends_adapter.GoogleTrendsAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_trends_job()

        mock_redis.set.assert_called_once()
        done_key = mock_redis.set.call_args[0][0]
        assert "jobs:weekly_trends:" in done_key
        assert ":done" in done_key

    @pytest.mark.asyncio
    async def test_continues_after_symbol_error(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["AAPL", "MSFT"])
        mock_adapter = AsyncMock()
        mock_adapter.get_trends.side_effect = [RuntimeError("stub error"), [MagicMock()]]
        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.google_trends_adapter.GoogleTrendsAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_trends_job()  # must not raise

        assert mock_adapter.get_trends.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_symbol_as_keyword(self):
        mock_redis = _mock_redis()
        mock_universe = _mock_universe(["TSLA"])
        mock_adapter = AsyncMock()
        mock_adapter.get_trends.return_value = []
        mock_storage = AsyncMock()

        with patch("src.core.redis.get_redis", new=AsyncMock(return_value=mock_redis)), \
             patch("src.data.universe.SymbolUniverse", return_value=mock_universe), \
             patch("src.data.adapters.google_trends_adapter.GoogleTrendsAdapter", return_value=mock_adapter), \
             patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage):
            await weekly_trends_job()

        mock_adapter.get_trends.assert_called_once_with("TSLA", keywords=["TSLA"])
