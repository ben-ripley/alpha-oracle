from src.strategy.ranker import StrategyRanker

__all__ = [
    "StrategyRanker",
]


def __getattr__(name: str):
    if name == "StrategyEngine":
        from src.strategy.engine import StrategyEngine
        return StrategyEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
