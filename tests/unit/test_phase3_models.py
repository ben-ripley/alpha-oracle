from __future__ import annotations

from datetime import datetime

import pytest

from src.core.models import (
    AgentAnalysis,
    AgentAnalysisType,
    AnalystEstimate,
    DailyBriefing,
    LLMUsageRecord,
    MarketRegime,
    MonteCarloResult,
    NewsArticle,
    OptionsFlowRecord,
    OptimizationResult,
    RecommendationAction,
    RegimeAnalysis,
    SentimentScore,
    StrategyAllocation,
    TradeRecommendation,
    TrendsData,
)


# --- Enum tests ---

class TestAgentAnalysisType:
    def test_values(self):
        assert AgentAnalysisType.FILING_10K == "FILING_10K"
        assert AgentAnalysisType.FILING_10Q == "FILING_10Q"
        assert AgentAnalysisType.FILING_8K == "FILING_8K"
        assert AgentAnalysisType.EARNINGS_SUMMARY == "EARNINGS_SUMMARY"

    def test_is_str_enum(self):
        assert isinstance(AgentAnalysisType.FILING_10K, str)


class TestRecommendationAction:
    def test_values(self):
        assert RecommendationAction.BUY == "BUY"
        assert RecommendationAction.SELL == "SELL"
        assert RecommendationAction.HOLD == "HOLD"

    def test_is_str_enum(self):
        assert isinstance(RecommendationAction.BUY, str)


class TestMarketRegime:
    def test_values(self):
        assert MarketRegime.BULL == "BULL"
        assert MarketRegime.BEAR == "BEAR"
        assert MarketRegime.SIDEWAYS == "SIDEWAYS"
        assert MarketRegime.HIGH_VOLATILITY == "HIGH_VOLATILITY"

    def test_is_str_enum(self):
        assert isinstance(MarketRegime.BULL, str)


# --- AgentAnalysis ---

class TestAgentAnalysis:
    def test_instantiation_required_fields(self):
        analysis = AgentAnalysis(
            symbol="AAPL",
            analysis_type=AgentAnalysisType.FILING_10K,
            summary="Strong revenue growth noted.",
        )
        assert analysis.symbol == "AAPL"
        assert analysis.analysis_type == AgentAnalysisType.FILING_10K
        assert analysis.summary == "Strong revenue growth noted."

    def test_schema_version_default(self):
        analysis = AgentAnalysis(
            symbol="MSFT",
            analysis_type=AgentAnalysisType.FILING_10Q,
            summary="Solid quarter.",
        )
        assert analysis.schema_version == 1

    def test_optional_fields_defaults(self):
        analysis = AgentAnalysis(
            symbol="GOOG",
            analysis_type=AgentAnalysisType.EARNINGS_SUMMARY,
            summary="Beat expectations.",
        )
        assert analysis.key_points == []
        assert analysis.risk_flags == []
        assert analysis.financial_highlights == {}
        assert analysis.tokens_used == 0
        assert analysis.cost_usd == 0.0
        assert analysis.model_name == ""

    def test_serialization(self):
        analysis = AgentAnalysis(
            symbol="AAPL",
            analysis_type=AgentAnalysisType.FILING_8K,
            summary="Material event disclosed.",
            key_points=["Point 1", "Point 2"],
            sentiment_score=0.7,
            tokens_used=1200,
            cost_usd=0.05,
            model_name="claude-sonnet-4-20250514",
        )
        data = analysis.model_dump()
        assert data["symbol"] == "AAPL"
        assert data["schema_version"] == 1
        assert data["key_points"] == ["Point 1", "Point 2"]

    def test_roundtrip(self):
        analysis = AgentAnalysis(
            symbol="TSLA",
            analysis_type=AgentAnalysisType.FILING_10K,
            summary="Annual report.",
            schema_version=1,
        )
        restored = AgentAnalysis(**analysis.model_dump())
        assert restored.symbol == analysis.symbol
        assert restored.schema_version == analysis.schema_version


# --- LLMUsageRecord ---

class TestLLMUsageRecord:
    def test_instantiation(self):
        record = LLMUsageRecord(
            agent_name="analyst",
            model_name="claude-sonnet-4-20250514",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.02,
            task_type="filing_analysis",
        )
        assert record.agent_name == "analyst"
        assert record.input_tokens == 500
        assert record.output_tokens == 200

    def test_serialization(self):
        record = LLMUsageRecord(
            agent_name="advisor",
            model_name="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            task_type="recommendation",
        )
        data = record.model_dump()
        assert data["cost_usd"] == 0.001


# --- TradeRecommendation ---

class TestTradeRecommendation:
    def test_instantiation(self):
        rec = TradeRecommendation(
            symbol="AAPL",
            action=RecommendationAction.BUY,
            confidence=0.85,
            rationale="Strong momentum signals.",
        )
        assert rec.symbol == "AAPL"
        assert rec.action == RecommendationAction.BUY
        assert rec.confidence == 0.85

    def test_schema_version_default(self):
        rec = TradeRecommendation(
            symbol="MSFT",
            action=RecommendationAction.HOLD,
            confidence=0.5,
            rationale="Neutral outlook.",
        )
        assert rec.schema_version == 1

    def test_human_approved_default_none(self):
        rec = TradeRecommendation(
            symbol="GOOG",
            action=RecommendationAction.SELL,
            confidence=0.7,
            rationale="Overbought signals.",
        )
        assert rec.human_approved is None

    def test_optional_price_fields(self):
        rec = TradeRecommendation(
            symbol="NVDA",
            action=RecommendationAction.BUY,
            confidence=0.9,
            rationale="AI tailwinds.",
            suggested_entry=450.0,
            suggested_stop=420.0,
            suggested_target=500.0,
        )
        assert rec.suggested_entry == 450.0
        assert rec.suggested_stop == 420.0
        assert rec.suggested_target == 500.0

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            TradeRecommendation(
                symbol="X",
                action=RecommendationAction.BUY,
                confidence=1.5,
                rationale="Invalid.",
            )

    def test_serialization(self):
        rec = TradeRecommendation(
            symbol="AMD",
            action=RecommendationAction.BUY,
            confidence=0.75,
            rationale="Bullish setup.",
            supporting_signals=["RSI divergence", "Volume spike"],
            risk_factors=["Earnings next week"],
        )
        data = rec.model_dump()
        assert data["supporting_signals"] == ["RSI divergence", "Volume spike"]
        assert data["schema_version"] == 1


# --- DailyBriefing ---

class TestDailyBriefing:
    def test_instantiation(self):
        now = datetime.utcnow()
        briefing = DailyBriefing(
            date=now,
            portfolio_summary="Portfolio performing well.",
            daily_pnl=250.0,
            risk_utilization=0.65,
            market_regime="BULL",
        )
        assert briefing.daily_pnl == 250.0
        assert briefing.risk_utilization == 0.65

    def test_schema_version_default(self):
        briefing = DailyBriefing(
            date=datetime.utcnow(),
            portfolio_summary="Summary.",
            daily_pnl=0.0,
            risk_utilization=0.5,
            market_regime="SIDEWAYS",
        )
        assert briefing.schema_version == 1

    def test_optional_list_defaults(self):
        briefing = DailyBriefing(
            date=datetime.utcnow(),
            portfolio_summary="Summary.",
            daily_pnl=100.0,
            risk_utilization=0.4,
            market_regime="BEAR",
        )
        assert briefing.upcoming_catalysts == []
        assert briefing.suggested_exits == []
        assert briefing.key_observations == []

    def test_serialization(self):
        now = datetime.utcnow()
        briefing = DailyBriefing(
            date=now,
            portfolio_summary="Good day.",
            daily_pnl=500.0,
            risk_utilization=0.7,
            upcoming_catalysts=["AAPL earnings"],
            market_regime="BULL",
        )
        data = briefing.model_dump()
        assert data["daily_pnl"] == 500.0
        assert data["schema_version"] == 1


# --- SentimentScore ---

class TestSentimentScore:
    def test_instantiation(self):
        score = SentimentScore(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            source="news",
            text_snippet="Apple reports record profits.",
            sentiment=0.8,
            confidence=0.9,
        )
        assert score.sentiment == 0.8
        assert score.confidence == 0.9

    def test_sentiment_bounds(self):
        with pytest.raises(Exception):
            SentimentScore(
                symbol="X",
                timestamp=datetime.utcnow(),
                source="news",
                text_snippet="test",
                sentiment=1.5,
                confidence=0.9,
            )

    def test_negative_sentiment(self):
        score = SentimentScore(
            symbol="TSLA",
            timestamp=datetime.utcnow(),
            source="filing",
            text_snippet="Significant risks noted.",
            sentiment=-0.6,
            confidence=0.75,
        )
        assert score.sentiment == -0.6


# --- NewsArticle ---

class TestNewsArticle:
    def test_instantiation(self):
        article = NewsArticle(
            symbol="AMZN",
            title="Amazon Q4 earnings beat",
            source="Reuters",
            published_at=datetime.utcnow(),
            url="https://example.com/article",
            summary="Amazon reported record Q4 earnings.",
            sentiment=0.6,
        )
        assert article.symbol == "AMZN"
        assert article.sentiment == 0.6


# --- AnalystEstimate ---

class TestAnalystEstimate:
    def test_instantiation(self):
        est = AnalystEstimate(
            symbol="MSFT",
            fiscal_date_ending="2025-06-30",
            consensus_estimate=2.95,
            actual=3.10,
            surprise_pct=5.08,
            num_analysts=28,
        )
        assert est.surprise_pct == 5.08
        assert est.num_analysts == 28

    def test_optional_fields(self):
        est = AnalystEstimate(
            symbol="NVDA",
            fiscal_date_ending="2025-01-31",
            consensus_estimate=4.50,
            num_analysts=35,
        )
        assert est.actual is None
        assert est.surprise_pct is None


# --- OptionsFlowRecord ---

class TestOptionsFlowRecord:
    def test_instantiation(self):
        record = OptionsFlowRecord(
            symbol="SPY",
            timestamp=datetime.utcnow(),
            put_volume=50000,
            call_volume=60000,
            put_call_ratio=0.833,
            unusual_activity=True,
        )
        assert record.put_call_ratio == 0.833
        assert record.unusual_activity is True


# --- TrendsData ---

class TestTrendsData:
    def test_instantiation(self):
        trend = TrendsData(
            symbol="AAPL",
            keyword="Apple stock",
            timestamp=datetime.utcnow(),
            interest_over_time=72.5,
        )
        assert trend.interest_over_time == 72.5


# --- MonteCarloResult ---

class TestMonteCarloResult:
    def test_instantiation(self):
        result = MonteCarloResult(
            num_simulations=10000,
            time_horizon_days=252,
            percentiles={"5": [100.0, 95.0], "95": [150.0, 160.0]},
            probability_of_loss=0.25,
            value_at_risk_95=5000.0,
        )
        assert result.num_simulations == 10000
        assert result.probability_of_loss == 0.25
        assert result.value_at_risk_95 == 5000.0

    def test_defaults(self):
        result = MonteCarloResult(
            num_simulations=1000,
            time_horizon_days=30,
            probability_of_loss=0.3,
            value_at_risk_95=1000.0,
        )
        assert result.percentiles == {}
        assert result.simulation_paths == []


# --- RegimeAnalysis ---

class TestRegimeAnalysis:
    def test_instantiation(self):
        analysis = RegimeAnalysis(
            current_regime=MarketRegime.BULL,
            regime_probability=0.85,
        )
        assert analysis.current_regime == MarketRegime.BULL
        assert analysis.regime_probability == 0.85

    def test_defaults(self):
        analysis = RegimeAnalysis(
            current_regime=MarketRegime.BEAR,
            regime_probability=0.7,
        )
        assert analysis.strategy_performance_by_regime == {}
        assert analysis.regime_history == []


# --- StrategyAllocation ---

class TestStrategyAllocation:
    def test_instantiation(self):
        alloc = StrategyAllocation(
            strategy_name="MomentumStrategy",
            weight=0.35,
            expected_return=0.12,
            contribution_to_risk=0.08,
        )
        assert alloc.weight == 0.35
        assert alloc.strategy_name == "MomentumStrategy"


# --- OptimizationResult ---

class TestOptimizationResult:
    def test_instantiation(self):
        result = OptimizationResult(
            allocations=[
                StrategyAllocation(
                    strategy_name="MomentumStrategy",
                    weight=0.6,
                    expected_return=0.12,
                    contribution_to_risk=0.08,
                ),
                StrategyAllocation(
                    strategy_name="MeanReversionStrategy",
                    weight=0.4,
                    expected_return=0.08,
                    contribution_to_risk=0.05,
                ),
            ],
            portfolio_sharpe=1.2,
            portfolio_expected_return=0.10,
            portfolio_volatility=0.15,
        )
        assert result.portfolio_sharpe == 1.2
        assert len(result.allocations) == 2

    def test_defaults(self):
        result = OptimizationResult(
            portfolio_sharpe=0.8,
            portfolio_expected_return=0.06,
            portfolio_volatility=0.12,
        )
        assert result.allocations == []
