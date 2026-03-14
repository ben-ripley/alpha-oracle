"""Graceful degradation integration tests for Phase 3 LLM agent features.

Tests verify that:
- Agent jobs return early (without errors) when agent.enabled=False
- API endpoints return HTTP 503 when agent.enabled=False
- FinBERT/sentiment scoring returns empty list when transformers not installed
- Agent disabled state does not affect non-agent features
- Scheduling jobs handle idempotency correctly
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Scheduling job graceful degradation
# ---------------------------------------------------------------------------

class TestDailySentimentJobDisabled:
    async def test_returns_early_when_agent_disabled(self):
        """daily_sentiment_job must return without error when agent.enabled=False."""
        mock_settings = MagicMock()
        mock_settings.agent.enabled = False

        with patch("src.core.config.get_settings", return_value=mock_settings):
            # Import inside test so patch is active
            from src.scheduling.jobs import daily_sentiment_job
            await daily_sentiment_job()  # Must not raise

    async def test_idempotent_via_done_key(self):
        """daily_sentiment_job skips processing when done key exists in Redis."""
        mock_settings = MagicMock()
        mock_settings.agent.enabled = True
        mock_settings.sentiment.max_articles_per_symbol = 5

        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1  # done key exists

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.core.redis.get_redis", return_value=mock_redis),
        ):
            from src.scheduling.jobs import daily_sentiment_job
            await daily_sentiment_job()

        # Universe should not be fetched if done key exists
        mock_redis.exists.assert_called_once()


class TestDailyBriefingJobDisabled:
    async def test_returns_early_when_agent_disabled(self):
        """daily_briefing_job must return without error when agent.enabled=False."""
        mock_settings = MagicMock()
        mock_settings.agent.enabled = False

        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.scheduling.jobs import daily_briefing_job
            await daily_briefing_job()  # Must not raise

    async def test_idempotent_via_done_key(self):
        """daily_briefing_job skips when briefing already exists in Redis."""
        mock_settings = MagicMock()
        mock_settings.agent.enabled = True

        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1  # briefing already done

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.core.redis.get_redis", return_value=mock_redis),
        ):
            from src.scheduling.jobs import daily_briefing_job
            await daily_briefing_job()

        mock_redis.exists.assert_called_once()


class TestWeeklyOptionsFlowJob:
    async def test_idempotent_via_done_key(self):
        """weekly_options_flow_job skips when done key exists."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1  # already done

        with patch("src.core.redis.get_redis", return_value=mock_redis):
            from src.scheduling.jobs import weekly_options_flow_job
            await weekly_options_flow_job()

        mock_redis.exists.assert_called_once()

    async def test_per_symbol_errors_are_isolated(self):
        """weekly_options_flow_job continues processing after a per-symbol error."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        mock_universe = AsyncMock()
        mock_universe.get_symbols.return_value = ["AAPL", "MSFT", "GOOG"]

        # OptionsFlowAdapter raises on MSFT, succeeds on others
        call_count = 0

        async def fake_get_options_flow(symbol):
            nonlocal call_count
            call_count += 1
            if symbol == "MSFT":
                raise RuntimeError("Simulated fetch error")
            from src.core.models import OptionsFlowRecord
            from datetime import datetime, timezone
            return [OptionsFlowRecord(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                put_volume=1000,
                call_volume=2000,
                put_call_ratio=0.5,
                unusual_activity=False,
            )]

        mock_adapter = AsyncMock()
        mock_adapter.get_options_flow = fake_get_options_flow

        mock_storage = AsyncMock()

        with (
            patch("src.core.redis.get_redis", return_value=mock_redis),
            patch("src.data.universe.SymbolUniverse", return_value=mock_universe),
            patch("src.data.adapters.options_flow_adapter.OptionsFlowAdapter", return_value=mock_adapter),
            patch("src.data.storage.TimeSeriesStorage", return_value=mock_storage),
        ):
            from src.scheduling.jobs import weekly_options_flow_job
            await weekly_options_flow_job()  # Must not raise despite MSFT error

        assert call_count == 3  # All symbols attempted


class TestWeeklyTrendsJob:
    async def test_idempotent_via_done_key(self):
        """weekly_trends_job skips when done key exists."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1

        with patch("src.core.redis.get_redis", return_value=mock_redis):
            from src.scheduling.jobs import weekly_trends_job
            await weekly_trends_job()

        mock_redis.exists.assert_called_once()


# ---------------------------------------------------------------------------
# FinBERT graceful degradation
# ---------------------------------------------------------------------------

class TestFinBERTGracefulDegradation:
    async def test_returns_empty_when_transformers_not_installed(self):
        """FinBERTSentimentPipeline.score_texts returns [] when transformers unavailable."""
        from src.agents.sentiment_scorer import FinBERTSentimentPipeline

        pipeline = FinBERTSentimentPipeline()

        # Simulate transformers import failure
        with patch("src.agents.sentiment_scorer._load_finbert", return_value=None):
            pipeline._pipeline = None  # Reset cached pipeline
            result = await pipeline.score_texts("AAPL", ["Strong earnings beat expectations."])

        assert result == []

    async def test_returns_empty_for_empty_input(self):
        """FinBERTSentimentPipeline.score_texts returns [] for empty input."""
        from src.agents.sentiment_scorer import FinBERTSentimentPipeline

        pipeline = FinBERTSentimentPipeline()
        result = await pipeline.score_texts("AAPL", [])
        assert result == []

    async def test_returns_scores_when_transformers_available(self):
        """FinBERTSentimentPipeline returns SentimentScore objects when pipeline loads."""
        from src.agents.sentiment_scorer import FinBERTSentimentPipeline
        from src.core.models import SentimentScore

        # Mock the pipeline outputs
        mock_pipe_fn = MagicMock(return_value=[{"label": "positive", "score": 0.9}])

        with patch("src.agents.sentiment_scorer._load_finbert", return_value=mock_pipe_fn):
            pipeline = FinBERTSentimentPipeline()
            pipeline._pipeline = None  # force reload
            result = await pipeline.score_texts("AAPL", ["Strong earnings beat expectations."])

        assert len(result) == 1
        assert isinstance(result[0], SentimentScore)
        assert result[0].symbol == "AAPL"
        assert result[0].sentiment > 0  # positive label -> positive score

    async def test_negative_sentiment_maps_to_negative_score(self):
        """Negative FinBERT label maps to negative sentiment score."""
        from src.agents.sentiment_scorer import FinBERTSentimentPipeline

        mock_pipe_fn = MagicMock(return_value=[{"label": "negative", "score": 0.85}])

        with patch("src.agents.sentiment_scorer._load_finbert", return_value=mock_pipe_fn):
            pipeline = FinBERTSentimentPipeline()
            pipeline._pipeline = None
            result = await pipeline.score_texts("AAPL", ["Earnings miss, guidance cut."])

        assert len(result) == 1
        assert result[0].sentiment < 0

    async def test_neutral_maps_to_zero(self):
        """Neutral FinBERT label maps to 0.0 sentiment score."""
        from src.agents.sentiment_scorer import FinBERTSentimentPipeline

        mock_pipe_fn = MagicMock(return_value=[{"label": "neutral", "score": 0.7}])

        with patch("src.agents.sentiment_scorer._load_finbert", return_value=mock_pipe_fn):
            pipeline = FinBERTSentimentPipeline()
            pipeline._pipeline = None
            result = await pipeline.score_texts("AAPL", ["Company reports quarterly results."])

        assert len(result) == 1
        assert result[0].sentiment == 0.0


# ---------------------------------------------------------------------------
# API endpoint 503 when agent disabled
# ---------------------------------------------------------------------------

class TestAgentAPIDisabled:
    """Tests that all agent endpoints return 503 when agent.enabled=False."""

    @pytest.fixture
    def client_with_agent_disabled(self):
        """TestClient with agent.enabled=False."""
        mock_settings = MagicMock()
        mock_settings.agent.enabled = False

        # Patch at config level
        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.api.main import app
            yield TestClient(app, raise_server_exceptions=False)

    def test_analyze_filing_returns_503(self, client_with_agent_disabled):
        resp = client_with_agent_disabled.post(
            "/api/agent/analyze-filing",
            json={"symbol": "AAPL", "filing_text": "test"},
        )
        assert resp.status_code == 503
        assert "disabled" in resp.json()["detail"].lower()

    def test_list_analyses_returns_503(self, client_with_agent_disabled):
        resp = client_with_agent_disabled.get("/api/agent/analyses?symbol=AAPL")
        assert resp.status_code == 503

    def test_recommend_returns_503(self, client_with_agent_disabled):
        resp = client_with_agent_disabled.post("/api/agent/recommend/AAPL")
        assert resp.status_code == 503

    def test_list_recommendations_returns_503(self, client_with_agent_disabled):
        resp = client_with_agent_disabled.get("/api/agent/recommendations")
        assert resp.status_code == 503

    def test_latest_briefing_returns_503(self, client_with_agent_disabled):
        resp = client_with_agent_disabled.get("/api/agent/briefing/latest")
        assert resp.status_code == 503

    def test_cost_summary_returns_503(self, client_with_agent_disabled):
        resp = client_with_agent_disabled.get("/api/agent/cost-summary")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Analysis endpoints always work (no agent dependency)
# ---------------------------------------------------------------------------

class TestAnalysisEndpointsAlwaysWork:
    """Analysis endpoints (Monte Carlo, regime, optimizer) never depend on agent.enabled."""

    def test_monte_carlo_works_when_agent_disabled(self):
        """POST /api/analysis/monte-carlo always works regardless of agent.enabled."""
        mock_settings = MagicMock()
        mock_settings.agent.enabled = False

        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.api.main import app
            client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/analysis/monte-carlo",
            json={"historical_returns": [0.01, -0.005, 0.02, -0.01, 0.015]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "percentiles" in data
        assert "probability_of_loss" in data

    def test_regime_post_works_when_agent_disabled(self):
        """POST /api/analysis/regime always works regardless of agent.enabled."""
        spy_prices = [400.0 + i * 0.5 for i in range(210)]
        vix_values = [15.0 + (i % 10) * 0.5 for i in range(210)]

        from src.api.main import app
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/analysis/regime",
            json={"spy_prices": spy_prices, "vix_values": vix_values},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "current_regime" in data

    def test_optimize_works_when_agent_disabled(self):
        """POST /api/analysis/optimize always works regardless of agent.enabled."""
        from src.api.main import app
        client = TestClient(app, raise_server_exceptions=False)

        returns = {"swing": [0.01, -0.005, 0.02], "momentum": [0.015, -0.01, 0.025]}
        resp = client.post(
            "/api/analysis/optimize",
            json={"strategy_returns": returns},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "allocations" in data
        assert "portfolio_sharpe" in data


# ---------------------------------------------------------------------------
# ClaudeAnalystAgent disabled state
# ---------------------------------------------------------------------------

class TestAnalystAgentDisabled:
    async def test_returns_none_output_when_agent_disabled(self):
        """ClaudeAnalystAgent.run() returns AgentResult(output=None) when disabled."""
        from src.agents.analyst import ClaudeAnalystAgent
        from src.agents.base import AgentContext

        mock_redis = AsyncMock()
        agent = ClaudeAnalystAgent(redis_client=mock_redis)

        mock_settings = MagicMock()
        mock_settings.agent.enabled = False

        context = AgentContext(
            symbol="AAPL",
            data={"filing_text": "test", "filing_type": "FILING_10K"},
        )

        with patch("src.core.config.get_settings", return_value=mock_settings):
            result = await agent.run(context)

        assert result.output is None
        assert result.metadata.get("disabled") is True

    async def test_no_api_call_when_disabled(self):
        """No Claude API call is made when agent.enabled=False."""
        from src.agents.analyst import ClaudeAnalystAgent
        from src.agents.base import AgentContext

        mock_redis = AsyncMock()
        agent = ClaudeAnalystAgent(redis_client=mock_redis)

        mock_settings = MagicMock()
        mock_settings.agent.enabled = False

        context = AgentContext(symbol="AAPL", data={"filing_text": "test"})

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.agents.client.get_anthropic_client") as mock_client,
        ):
            await agent.run(context)
            mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# Budget enforcement graceful rejection
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    async def test_analyst_agent_rejects_when_budget_exceeded(self):
        """ClaudeAnalystAgent raises BudgetExceededError when daily budget is exceeded."""
        from src.agents.analyst import ClaudeAnalystAgent
        from src.agents.base import AgentContext
        from src.agents.cost_tracker import BudgetExceededError

        mock_redis = AsyncMock()
        agent = ClaudeAnalystAgent(redis_client=mock_redis)

        mock_settings = MagicMock()
        mock_settings.agent.enabled = True
        mock_settings.agent.analyst_model = "claude-sonnet-4-20250514"
        mock_settings.agent.daily_budget_usd = 5.0
        mock_settings.agent.monthly_budget_usd = 100.0

        context = AgentContext(symbol="AAPL", data={"filing_text": "test", "filing_type": "FILING_10K"})

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch.object(
                agent._cost_tracker,
                "reject_if_over_budget",
                side_effect=BudgetExceededError("Daily budget exceeded: $5.00 >= $5.00"),
            ),
        ):
            with pytest.raises(BudgetExceededError, match="Daily budget exceeded"):
                await agent.run(context)
