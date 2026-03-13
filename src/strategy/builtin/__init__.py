__all__ = [
    "InsiderFollowing",
    "MeanReversion",
    "SwingMomentum",
    "ValueFactor",
]


def __getattr__(name: str):
    if name == "InsiderFollowing":
        from src.strategy.builtin.insider_following import InsiderFollowing
        return InsiderFollowing
    if name == "MeanReversion":
        from src.strategy.builtin.mean_reversion import MeanReversion
        return MeanReversion
    if name == "SwingMomentum":
        from src.strategy.builtin.swing_momentum import SwingMomentum
        return SwingMomentum
    if name == "ValueFactor":
        from src.strategy.builtin.value_factor import ValueFactor
        return ValueFactor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
