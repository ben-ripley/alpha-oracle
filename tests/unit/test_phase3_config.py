from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.core.config import (
    AgentSettings,
    OptionsFlowSettings,
    RiskSettings,
    SchedulerSettings,
    SentimentSettings,
    Settings,
    TrendsSettings,
)


# --- AgentSettings ---

class TestAgentSettings:
    def test_defaults(self):
        settings = AgentSettings()
        assert settings.analyst_model == "claude-sonnet-4-20250514"
        assert settings.advisor_model == "claude-haiku-4-5-20251001"
        assert settings.briefing_model == "claude-sonnet-4-20250514"
        assert settings.temperature == 0.0
        assert settings.max_input_tokens == 50000
        assert settings.max_output_tokens == 4096
        assert settings.daily_budget_usd == 5.0
        assert settings.monthly_budget_usd == 100.0
        assert settings.enabled is True
        assert settings.cache_ttl_seconds == 14400
        assert settings.rate_limit_analyses_per_hour == 10
        assert settings.rate_limit_recommendations_per_hour == 50

    def test_env_var_override_enabled(self):
        with patch.dict(os.environ, {"SA_AGENT__ENABLED": "false"}):
            settings = AgentSettings()
            # Note: AgentSettings is BaseSettings, env_prefix not set on subclass
            # Env var overrides are applied through the parent Settings class
        # Verify the field exists and can be set to False
        settings = AgentSettings(enabled=False)
        assert settings.enabled is False

    def test_budget_can_be_overridden(self):
        settings = AgentSettings(daily_budget_usd=10.0, monthly_budget_usd=200.0)
        assert settings.daily_budget_usd == 10.0
        assert settings.monthly_budget_usd == 200.0

    def test_rate_limits_can_be_overridden(self):
        settings = AgentSettings(
            rate_limit_analyses_per_hour=5,
            rate_limit_recommendations_per_hour=20,
        )
        assert settings.rate_limit_analyses_per_hour == 5
        assert settings.rate_limit_recommendations_per_hour == 20

    def test_cache_ttl_can_be_overridden(self):
        settings = AgentSettings(cache_ttl_seconds=3600)
        assert settings.cache_ttl_seconds == 3600

    def test_model_fields_can_be_overridden(self):
        settings = AgentSettings(
            analyst_model="claude-opus-4-20250514",
            advisor_model="claude-sonnet-4-20250514",
        )
        assert settings.analyst_model == "claude-opus-4-20250514"
        assert settings.advisor_model == "claude-sonnet-4-20250514"


# --- SentimentSettings ---

class TestSentimentSettings:
    def test_defaults(self):
        settings = SentimentSettings()
        assert settings.model_name == "ProsusAI/finbert"
        assert settings.device == "cpu"
        assert settings.batch_size == 32
        assert settings.cache_ttl_seconds == 86400
        assert settings.max_articles_per_symbol == 20

    def test_can_override_device(self):
        settings = SentimentSettings(device="cuda")
        assert settings.device == "cuda"

    def test_can_override_batch_size(self):
        settings = SentimentSettings(batch_size=64)
        assert settings.batch_size == 64

    def test_can_override_model_name(self):
        settings = SentimentSettings(model_name="custom/finbert")
        assert settings.model_name == "custom/finbert"


# --- OptionsFlowSettings ---

class TestOptionsFlowSettings:
    def test_defaults(self):
        settings = OptionsFlowSettings()
        assert settings.provider == "stub"
        assert settings.enabled is False

    def test_can_enable(self):
        settings = OptionsFlowSettings(enabled=True, provider="real_provider")
        assert settings.enabled is True
        assert settings.provider == "real_provider"


# --- TrendsSettings ---

class TestTrendsSettings:
    def test_defaults(self):
        settings = TrendsSettings()
        assert settings.provider == "stub"
        assert settings.enabled is False

    def test_can_enable(self):
        settings = TrendsSettings(enabled=True)
        assert settings.enabled is True


# --- SchedulerSettings extensions ---

class TestSchedulerSettingsExtensions:
    def test_new_cron_defaults(self):
        settings = SchedulerSettings()
        assert settings.daily_sentiment_cron == "30 17 * * 1-5"
        assert settings.daily_briefing_cron == "0 8 * * 1-5"

    def test_existing_crons_unchanged(self):
        settings = SchedulerSettings()
        assert settings.daily_bars_cron == "0 17 * * 1-5"
        assert settings.weekly_fundamentals_cron == "0 6 * * 6"
        assert settings.biweekly_altdata_cron == "0 7 1,15 * *"
        assert settings.weekly_retrain_cron == "0 2 * * 0"

    def test_new_crons_can_be_overridden(self):
        settings = SchedulerSettings(
            daily_sentiment_cron="0 18 * * 1-5",
            daily_briefing_cron="30 7 * * 1-5",
        )
        assert settings.daily_sentiment_cron == "0 18 * * 1-5"
        assert settings.daily_briefing_cron == "30 7 * * 1-5"


# --- RiskSettings extensions ---

class TestRiskSettingsExtensions:
    def test_autonomy_transition_defaults(self):
        settings = RiskSettings()
        assert settings.autonomy_transition_min_days == 30
        assert settings.autonomy_min_sharpe == 0.5
        assert settings.autonomy_max_drawdown_pct == 10.0
        assert settings.autonomy_min_profitable_days == 30

    def test_existing_fields_unchanged(self):
        settings = RiskSettings()
        assert settings.autonomy_mode == "PAPER_ONLY"
        assert settings.position_limits is not None
        assert settings.portfolio_limits is not None
        assert settings.pdt_guard is not None
        assert settings.circuit_breakers is not None
        assert settings.kill_switch is not None

    def test_autonomy_thresholds_can_be_overridden(self):
        settings = RiskSettings(
            autonomy_transition_min_days=60,
            autonomy_min_sharpe=1.0,
            autonomy_max_drawdown_pct=5.0,
            autonomy_min_profitable_days=45,
        )
        assert settings.autonomy_transition_min_days == 60
        assert settings.autonomy_min_sharpe == 1.0
        assert settings.autonomy_max_drawdown_pct == 5.0
        assert settings.autonomy_min_profitable_days == 45


# --- Settings class integration ---

class TestSettingsIntegration:
    def test_settings_has_new_sub_configs(self):
        settings = Settings()
        assert hasattr(settings, "sentiment")
        assert hasattr(settings, "options_flow")
        assert hasattr(settings, "trends")

    def test_settings_sentiment_defaults(self):
        settings = Settings()
        assert isinstance(settings.sentiment, SentimentSettings)
        assert settings.sentiment.model_name == "ProsusAI/finbert"

    def test_settings_options_flow_defaults(self):
        settings = Settings()
        assert isinstance(settings.options_flow, OptionsFlowSettings)
        assert settings.options_flow.enabled is False

    def test_settings_trends_defaults(self):
        settings = Settings()
        assert isinstance(settings.trends, TrendsSettings)
        assert settings.trends.enabled is False

    def test_settings_agent_has_new_fields(self):
        settings = Settings()
        assert hasattr(settings.agent, "analyst_model")
        assert hasattr(settings.agent, "advisor_model")
        assert hasattr(settings.agent, "briefing_model")
        assert hasattr(settings.agent, "cache_ttl_seconds")
        assert hasattr(settings.agent, "rate_limit_analyses_per_hour")
        assert hasattr(settings.agent, "rate_limit_recommendations_per_hour")

    def test_settings_scheduler_has_new_crons(self):
        settings = Settings()
        assert hasattr(settings.scheduler, "daily_sentiment_cron")
        assert hasattr(settings.scheduler, "daily_briefing_cron")

    def test_settings_risk_has_new_fields(self):
        settings = Settings()
        assert hasattr(settings.risk, "autonomy_transition_min_days")
        assert hasattr(settings.risk, "autonomy_min_sharpe")
        assert hasattr(settings.risk, "autonomy_max_drawdown_pct")
        assert hasattr(settings.risk, "autonomy_min_profitable_days")

    def test_from_yaml_loads_without_error(self):
        # from_yaml should load without raising exceptions
        settings = Settings.from_yaml()
        assert settings is not None
        assert settings.sentiment.model_name == "ProsusAI/finbert"
        assert settings.options_flow.provider == "stub"
        assert settings.trends.provider == "stub"

    def test_from_yaml_agent_new_fields(self):
        settings = Settings.from_yaml()
        assert settings.agent.analyst_model == "claude-sonnet-4-20250514"
        assert settings.agent.advisor_model == "claude-haiku-4-5-20251001"
        assert settings.agent.cache_ttl_seconds == 14400

    def test_from_yaml_scheduler_new_crons(self):
        settings = Settings.from_yaml()
        assert settings.scheduler.daily_sentiment_cron == "30 17 * * 1-5"
        assert settings.scheduler.daily_briefing_cron == "0 8 * * 1-5"

    def test_env_var_overrides_agent_enabled(self):
        with patch.dict(os.environ, {"SA_AGENT__ENABLED": "false"}):
            settings = Settings()
            assert settings.agent.enabled is False

    def test_env_var_overrides_sentiment_device(self):
        with patch.dict(os.environ, {"SA_SENTIMENT__DEVICE": "cuda"}):
            settings = Settings()
            assert settings.sentiment.device == "cuda"
