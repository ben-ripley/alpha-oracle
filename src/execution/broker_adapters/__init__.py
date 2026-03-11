__all__ = ["AlpacaBrokerAdapter"]


def __getattr__(name: str):
    if name == "AlpacaBrokerAdapter":
        from src.execution.broker_adapters.alpaca_adapter import AlpacaBrokerAdapter
        return AlpacaBrokerAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
