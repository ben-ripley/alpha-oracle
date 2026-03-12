__all__ = ["AlpacaBrokerAdapter", "IBKRBrokerAdapter"]


def __getattr__(name: str):
    if name == "AlpacaBrokerAdapter":
        from src.execution.broker_adapters.alpaca_adapter import AlpacaBrokerAdapter
        return AlpacaBrokerAdapter
    if name == "IBKRBrokerAdapter":
        from src.execution.broker_adapters.ibkr_adapter import IBKRBrokerAdapter
        return IBKRBrokerAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
