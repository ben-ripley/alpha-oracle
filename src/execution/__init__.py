from src.execution.engine import ExecutionEngine
from src.execution.order_generator import OrderGenerator

__all__ = [
    "ExecutionEngine",
    "OrderGenerator",
]


def __getattr__(name: str):
    if name == "AlpacaBrokerAdapter":
        from src.execution.broker_adapters.alpaca_adapter import AlpacaBrokerAdapter
        return AlpacaBrokerAdapter
    if name == "ExecutionTracker":
        from src.execution.tracker import ExecutionTracker
        return ExecutionTracker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
