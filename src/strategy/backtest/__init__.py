__all__ = [
    "BacktraderEngine",
    "VectorBTEngine",
]


def __getattr__(name: str):
    if name == "BacktraderEngine":
        from src.strategy.backtest.backtrader_engine import BacktraderEngine
        return BacktraderEngine
    if name == "VectorBTEngine":
        from src.strategy.backtest.vectorbt_engine import VectorBTEngine
        return VectorBTEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
