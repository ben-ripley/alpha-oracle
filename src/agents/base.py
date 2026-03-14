"""BaseAgent ABC and shared dataclasses for the agent layer."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    symbol: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    output: Any
    tokens_used: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult: ...

    def get_token_budget(self) -> int:
        from src.core.config import get_settings
        return get_settings().agent.max_input_tokens
