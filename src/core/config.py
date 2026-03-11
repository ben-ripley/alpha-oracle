from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


class BrokerSettings(BaseSettings):
    provider: str = "alpaca"
    paper_trading: bool = True
    base_url: str = "https://paper-api.alpaca.markets"


class AlpacaDataSettings(BaseSettings):
    feed: str = "iex"
    max_bars_per_request: int = 10000


class AlphaVantageDataSettings(BaseSettings):
    rate_limit_per_minute: int = 5
    cache_ttl_hours: int = 24


class EdgarDataSettings(BaseSettings):
    user_agent: str = "stock-analysis bot@example.com"
    rate_limit_per_second: int = 10


class DataSettings(BaseSettings):
    alpaca: AlpacaDataSettings = AlpacaDataSettings()
    alpha_vantage: AlphaVantageDataSettings = AlphaVantageDataSettings()
    edgar: EdgarDataSettings = EdgarDataSettings()


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://trader:dev_password@localhost:5432/stock_analysis"
    pool_size: int = 10
    max_overflow: int = 20


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600


class WalkForwardSettings(BaseSettings):
    train_months: int = 24
    test_months: int = 6
    step_months: int = 3


class RankingWeights(BaseSettings):
    sharpe: float = 0.30
    sortino: float = 0.20
    max_drawdown_inverse: float = 0.20
    profit_factor: float = 0.15
    consistency: float = 0.15


class StrategySettings(BaseSettings):
    min_sharpe_ratio: float = 1.0
    min_profit_factor: float = 1.5
    max_drawdown_pct: float = 20.0
    min_trades: int = 100
    walk_forward: WalkForwardSettings = WalkForwardSettings()
    ranking_weights: RankingWeights = RankingWeights()


class ExecutionSettings(BaseSettings):
    default_order_type: str = "limit"
    limit_offset_pct: float = 0.05
    max_slippage_pct: float = 0.10
    position_sizing: str = "half_kelly"


class MonitoringSettings(BaseSettings):
    prometheus_port: int = 8001
    health_check_interval_seconds: int = 60


class PositionLimits(BaseSettings):
    max_position_pct: float = 5.0
    max_sector_pct: float = 25.0
    stop_loss_pct: float = 2.0
    min_price: float = 5.0
    no_leverage: bool = True


class PortfolioLimits(BaseSettings):
    max_drawdown_pct: float = 10.0
    max_daily_loss_pct: float = 3.0
    max_positions: int = 20
    max_daily_trades: int = 50
    min_cash_reserve_pct: float = 10.0


class PDTGuard(BaseSettings):
    enabled: bool = True
    max_day_trades: int = 3
    rolling_window_days: int = 5
    account_threshold: float = 25000.0


class CircuitBreakerSettings(BaseSettings):
    vix_threshold: float = 35.0
    stale_data_seconds: int = 300
    reconciliation_interval_seconds: int = 300
    max_reconciliation_drift_pct: float = 1.0
    dead_man_switch_hours: int = 48


class KillSwitchSettings(BaseSettings):
    http_enabled: bool = True
    telegram_enabled: bool = False
    cooldown_minutes: int = 60


class RiskSettings(BaseSettings):
    autonomy_mode: str = "PAPER_ONLY"
    position_limits: PositionLimits = PositionLimits()
    portfolio_limits: PortfolioLimits = PortfolioLimits()
    pdt_guard: PDTGuard = PDTGuard()
    circuit_breakers: CircuitBreakerSettings = CircuitBreakerSettings()
    kill_switch: KillSwitchSettings = KillSwitchSettings()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SA_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"

    # API keys from env
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpha_vantage_api_key: str = ""
    anthropic_api_key: str = ""

    # Sub-configs loaded from YAML + env overrides
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)

    @classmethod
    def from_yaml(cls) -> Settings:
        import os

        settings_data = _load_yaml("settings.yaml")
        risk_data = _load_yaml("risk_limits.yaml")

        flat: dict = {}
        if "app" in settings_data:
            flat["environment"] = settings_data["app"].get("environment", "development")
            flat["log_level"] = settings_data["app"].get("log_level", "INFO")

        for key in ["broker", "data", "database", "redis", "strategy", "execution", "monitoring"]:
            if key in settings_data:
                flat[key] = settings_data[key]

        if risk_data:
            flat["risk"] = risk_data

        # Let env vars (SA_ prefix with __ nesting) override YAML values.
        # pydantic-settings gives priority to explicit kwargs over env vars,
        # so we must remove any YAML keys that have a corresponding env override.
        prefix = (cls.model_config.get("env_prefix") or "").upper()
        delimiter = cls.model_config.get("env_nested_delimiter") or "__"
        for env_key in os.environ:
            if not env_key.startswith(prefix):
                continue
            parts = env_key[len(prefix):].lower().split(delimiter.lower())
            if len(parts) >= 2 and parts[0] in flat and isinstance(flat[parts[0]], dict):
                flat[parts[0]][parts[1]] = os.environ[env_key]

        return cls(**flat)


@functools.lru_cache
def get_settings() -> Settings:
    return Settings.from_yaml()
