from src.execution.engine import ExecutionEngine
from src.execution.order_generator import OrderGenerator
from src.execution.router import SmartOrderRouter

__all__ = [
    "ExecutionEngine",
    "OrderGenerator",
    "SmartOrderRouter",
]


def __getattr__(name: str):
    if name == "ExecutionTracker":
        from src.execution.tracker import ExecutionTracker
        return ExecutionTracker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
