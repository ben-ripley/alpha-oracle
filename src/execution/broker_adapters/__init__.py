__all__ = ["IBKRBrokerAdapter"]


def __getattr__(name: str):
    if name == "IBKRBrokerAdapter":
        from src.execution.broker_adapters.ibkr_adapter import IBKRBrokerAdapter
        return IBKRBrokerAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
