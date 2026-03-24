---
title: Full Autonomous Mode
nav_order: 7
parent: Concepts
---

# Full Autonomous Mode

## The Four Autonomy Modes

Alpha Oracle operates in one of four autonomy modes, set in `config/risk_limits.yaml` (`autonomy_mode`) or via `SA_RISK__AUTONOMY_MODE`:

| Mode | Behavior |
|------|----------|
| `PAPER_ONLY` | All orders simulated. No real trades. Default. |
| `MANUAL_APPROVAL` | All orders require human approval before submission. |
| `BOUNDED_AUTONOMOUS` | Orders up to $10,000 auto-approve through risk engine. Larger orders require approval. |
| `FULL_AUTONOMOUS` | All orders auto-approve if Layers 1-4 risk checks pass. |

## Transitioning Between Modes

Modes must be upgraded one step at a time. Skipping steps is rejected.

### PAPER_ONLY → MANUAL_APPROVAL

No financial requirements. System must be healthy (no tripped circuit breakers).

### MANUAL_APPROVAL → BOUNDED_AUTONOMOUS

All of the following must be met:
- Minimum **30 days** in `MANUAL_APPROVAL` mode
- Sharpe ratio ≥ **0.5** during the evaluation period
- Maximum drawdown ≤ **10%** during the evaluation period

### BOUNDED_AUTONOMOUS → FULL_AUTONOMOUS

All of the following must be met:
- Minimum **90 days** in `BOUNDED_AUTONOMOUS` mode (hardcoded — not configurable)
- Sharpe ratio ≥ **0.5** during the evaluation period
- Maximum drawdown ≤ **10%** during the evaluation period
- Circuit breakers must have been **triggered and tested** at least once
- LLM guardrails must have been **verified within the last 24 hours** (run `POST /api/risk/guardrails/verify`)
- **Typed confirmation:** the API call must include `"confirmation": "FULL_AUTONOMOUS"` in the request body

## What Safeguards Remain Active in FULL_AUTONOMOUS

Entering `FULL_AUTONOMOUS` does **not** disable any risk checks. All four layers remain fully active:

1. **Position limits** — 5% max per position, 25% sector, $5 min price, no leverage
2. **Portfolio limits** — 10% max drawdown halt, 3% daily loss halt, 10% cash reserve
3. **Circuit breakers** — VIX >35, stale data, reconciliation drift, dead man switch
4. **LLM guardrails** — verified that agents cannot access broker interfaces

The kill switch remains operable at all times. Typing `KILL` via `POST /api/risk/kill-switch/activate` halts all trading immediately regardless of autonomy mode.

## Downgrading

Any mode can be downgraded to any lower mode at any time, with no requirements. Downgrading is always instant.

## Checking Readiness

`GET /api/risk/autonomy-mode/readiness` returns the current mode, days in mode, and a checklist of transition requirements for the next mode up.

## Configuration

The thresholds used for mode transitions are configurable in `config/risk_limits.yaml`:

```yaml
autonomy_transition_min_days: 30      # Min days for MANUAL->BOUNDED
autonomy_min_sharpe: 0.5             # Min Sharpe for all upgrades
autonomy_max_drawdown_pct: 10.0      # Max drawdown allowed
autonomy_min_profitable_days: 30     # Min profitable days
```

The 90-day BOUNDED→FULL threshold is hardcoded and cannot be changed via config — it is a safety floor.
