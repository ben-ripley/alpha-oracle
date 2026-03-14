# LLM Guardrails (Layer 4)

## Overview

Layer 4 of the risk architecture ensures LLM agents are advisory-only and cannot access execution interfaces. It is implemented across two files:

- `src/agents/guardrails.py` — runtime output validation and self-test
- `src/risk/llm_guardrails.py` — risk-layer engine used by `AutonomyValidator`

## What Guardrails Prevent

Agents must never:
- Import or reference `BrokerAdapter` at module level
- Produce output containing broker method names (`place_order`, `submit_order`, `cancel_order`, `execute_trade`, etc.)
- Return executable instructions rather than advisory data

## Runtime Enforcement (`src/agents/guardrails.py`)

### The `@guardrail` Decorator

Every `BaseAgent.run()` method is decorated with `@guardrail`:

```python
@guardrail
async def run(self, context: AgentContext) -> AgentResult:
    ...
```

After `run()` returns, `validate_output(result)` scans `str(result.output)` for any of the restricted patterns. If a pattern is found, `GuardrailViolationError` is raised immediately — the result is never returned to the caller.

### Restricted Patterns

```python
_BROKER_ACCESS_PATTERNS = [
    "BrokerAdapter", "place_order", "submit_order",
    "cancel_order", "get_portfolio", "execute_trade",
]
```

### `LLMGuardrailsChecker.verify()`

Runs a self-test:
1. Passes a result containing `"BrokerAdapter.place_order()"` — must raise `GuardrailViolationError`
2. Passes a clean result — must pass through
3. Stores current timestamp in Redis: `risk:guardrails:last_verified`

Returns `True` if both checks pass.

## Risk-Layer Engine (`src/risk/llm_guardrails.py`)

`LLMGuardrailsEngine` is used by the risk module (not the agents module) to verify guardrail integrity as a precondition for `FULL_AUTONOMOUS` mode.

```python
engine = LLMGuardrailsEngine()
engine.verify_guardrails()         # synchronous; checks module imports + stores timestamp
engine.is_recently_verified()      # True if verified within last 24h
engine.get_status()                # dict for risk dashboard
```

`verify_guardrails()` checks that no loaded `src.agents.*` module exposes a `BrokerAdapter` instance or class in its namespace (module-level import check).

## Integration with Autonomy Validator

`AutonomyValidator._validate_bounded_to_full()` calls `_guardrails_recently_verified()` which reads the Redis key `risk:guardrails:last_verified`. If the key is missing or older than 24 hours, the FULL_AUTONOMOUS transition is blocked:

```
LLM guardrails have not been verified recently — run guardrail self-test first
```

To clear this blocker: `POST /api/risk/guardrails/verify` (triggers `LLMGuardrailsChecker.verify()`).

## Design Decisions

- **Why two separate files?** `src/agents/guardrails.py` owns runtime enforcement (decorators, output validation). `src/risk/llm_guardrails.py` owns the risk-layer view (module import checks, dashboard status). The risk module has no hard dependency on the agents package at import time.
- **Why not a sandbox?** The codebase is a monolith — full OS-level sandboxing is disproportionate. The guardrail approach is proportionate: enforce the invariant that agents import nothing from `src/execution/` at module level, and validate outputs at runtime.
- **Fail-safe direction:** if the module-level import check errors (e.g., module not loaded yet), it returns `True` (safe). The output pattern check has no such fallback — a violation always raises.
