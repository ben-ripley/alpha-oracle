# Writing a Custom Data Adapter

Data adapters fetch market data from external sources (APIs, databases, files). All adapters implement the [DataSourceInterface](../glossary.md#abc) abstract base class.

## DataSourceInterface

**Location:** `src/core/interfaces.py`

```python
from abc import ABC, abstractmethod
from datetime import datetime
from src.core.models import OHLCV, FundamentalData

class DataSourceInterface(ABC):
    @abstractmethod
    async def get_historical_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str = "1Day"
    ) -> list[OHLCV]:
        """Fetch historical OHLCV bars for a symbol."""
        ...

    @abstractmethod
    async def get_latest_bar(self, symbol: str) -> OHLCV | None:
        """Fetch the most recent OHLCV bar for a symbol."""
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> FundamentalData | None:
        """Fetch fundamental financial metrics for a symbol."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the data source is reachable and healthy."""
        ...
```

---

## Example: Custom CSV Data Adapter

### Use Case
Load historical data from local CSV files (useful for offline development or custom datasets).

### Implementation

**Location:** `src/data/adapters/csv_adapter.py`

```python
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from src.core.interfaces import DataSourceInterface
from src.core.models import OHLCV, FundamentalData

logger = structlog.get_logger(__name__)


class CSVDataAdapter(DataSourceInterface):
    """Data adapter for loading OHLCV data from CSV files.

    Expected directory structure:
        data/
          AAPL.csv
          MSFT.csv
          ...

    CSV format:
        timestamp,open,high,low,close,volume
        2024-01-02 00:00:00+00:00,180.50,182.00,180.00,181.50,50000000
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        if not self._data_dir.exists():
            raise ValueError(f"Data directory does not exist: {data_dir}")
        logger.info("csv_adapter_initialized", data_dir=str(self._data_dir))

    def _csv_path(self, symbol: str) -> Path:
        """Return the CSV file path for a symbol."""
        return self._data_dir / f"{symbol}.csv"

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse timestamp string to datetime."""
        # Try ISO format first
        try:
            return datetime.fromisoformat(ts_str)
        except ValueError:
            pass

        # Try common date format
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        # Try date-only format
        dt = datetime.strptime(ts_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)

    async def get_historical_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str = "1Day"
    ) -> list[OHLCV]:
        """Load historical bars from CSV file."""
        csv_path = self._csv_path(symbol)
        if not csv_path.exists():
            logger.warning("csv_file_not_found", symbol=symbol, path=str(csv_path))
            return []

        bars: list[OHLCV] = []
        try:
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    timestamp = self._parse_timestamp(row["timestamp"])

                    # Filter to requested time range
                    if not (start <= timestamp <= end):
                        continue

                    bar = OHLCV(
                        symbol=symbol,
                        timestamp=timestamp,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                        adjusted_close=float(row.get("adjusted_close", row["close"])),
                        source="csv",
                    )
                    bars.append(bar)

            logger.info("csv_bars_loaded", symbol=symbol, count=len(bars))
            return bars

        except Exception as exc:
            logger.error("csv_load_failed", symbol=symbol, error=str(exc))
            raise

    async def get_latest_bar(self, symbol: str) -> OHLCV | None:
        """Return the most recent bar from CSV."""
        csv_path = self._csv_path(symbol)
        if not csv_path.exists():
            return None

        try:
            # Read last line of file (most recent bar if sorted ascending)
            with open(csv_path, "rb") as f:
                # Seek to end and read backwards to find last line
                f.seek(0, 2)
                file_size = f.tell()
                if file_size == 0:
                    return None

                # Read last 1KB (should contain last line)
                f.seek(max(0, file_size - 1024))
                lines = f.read().decode("utf-8").splitlines()

            if len(lines) < 2:  # Header + at least one data row
                return None

            # Parse last line
            last_line = lines[-1]
            row = dict(zip(lines[0].split(","), last_line.split(",")))

            return OHLCV(
                symbol=symbol,
                timestamp=self._parse_timestamp(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                source="csv",
            )

        except Exception as exc:
            logger.error("csv_latest_bar_failed", symbol=symbol, error=str(exc))
            return None

    async def get_fundamentals(self, symbol: str) -> FundamentalData | None:
        """CSV adapter does not provide fundamental data."""
        return None

    async def health_check(self) -> bool:
        """Check if data directory is accessible."""
        try:
            return self._data_dir.exists() and self._data_dir.is_dir()
        except Exception:
            return False
```

---

## Rate Limiting

For API-based adapters, implement rate limiting:

```python
from src.data.rate_limiter import RateLimiter

class APIDataAdapter(DataSourceInterface):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        # 5 requests per minute
        self._rate_limiter = RateLimiter(
            name="custom_api",
            max_tokens=5,
            refill_rate=5 / 60,  # 5 per minute = 0.083 per second
        )

    async def get_historical_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str = "1Day"
    ) -> list[OHLCV]:
        # Wait for rate limiter
        await self._rate_limiter.acquire()

        # Make API call
        response = await self._fetch_from_api(symbol, start, end)
        return self._parse_response(response)
```

**RateLimiter usage:**
- `await rate_limiter.acquire()` — Blocks until a token is available
- Tokens refill automatically based on `refill_rate`
- Backed by Redis for distributed rate limiting

---

## Error Handling

### Transient Errors

Retry with exponential backoff:

```python
import asyncio

async def get_historical_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str = "1Day") -> list[OHLCV]:
    for attempt in range(3):
        try:
            await self._rate_limiter.acquire()
            response = await self._api_call(symbol, start, end)
            return self._parse_response(response)
        except (ConnectionError, TimeoutError) as exc:
            if attempt == 2:  # Last attempt
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning("api_retry", symbol=symbol, attempt=attempt + 1, wait=wait, error=str(exc))
            await asyncio.sleep(wait)
```

### Invalid Data

Return empty list rather than raising:

```python
async def get_historical_bars(...) -> list[OHLCV]:
    try:
        response = await self._api_call(symbol, start, end)
        if not response or "error" in response:
            logger.warning("api_no_data", symbol=symbol)
            return []  # Empty list, not an error
        return self._parse_response(response)
    except Exception as exc:
        logger.error("api_call_failed", symbol=symbol, error=str(exc))
        raise  # Re-raise unexpected errors
```

---

## Testing

### Unit Test

**Location:** `tests/unit/test_csv_adapter.py`

```python
import pytest
from datetime import datetime, timezone
from pathlib import Path
from src.data.adapters.csv_adapter import CSVDataAdapter


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a sample CSV file."""
    csv_file = tmp_path / "AAPL.csv"
    csv_file.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02,180.50,182.00,180.00,181.50,50000000\n"
        "2024-01-03,181.50,183.00,181.00,182.50,60000000\n"
    )
    return tmp_path


@pytest.mark.asyncio
async def test_csv_adapter_historical_bars(sample_csv):
    adapter = CSVDataAdapter(sample_csv)

    bars = await adapter.get_historical_bars(
        symbol="AAPL",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 31, tzinfo=timezone.utc),
    )

    assert len(bars) == 2
    assert bars[0].symbol == "AAPL"
    assert bars[0].close == 181.50
    assert bars[1].close == 182.50


@pytest.mark.asyncio
async def test_csv_adapter_latest_bar(sample_csv):
    adapter = CSVDataAdapter(sample_csv)

    latest = await adapter.get_latest_bar("AAPL")

    assert latest is not None
    assert latest.symbol == "AAPL"
    assert latest.close == 182.50  # Last row


@pytest.mark.asyncio
async def test_csv_adapter_health_check(sample_csv):
    adapter = CSVDataAdapter(sample_csv)

    is_healthy = await adapter.health_check()

    assert is_healthy is True
```

---

## Registration

### Option 1: Configuration-Driven

Add to `config/settings.yaml`:

```yaml
data:
  sources:
    - name: csv
      adapter: src.data.adapters.csv_adapter.CSVDataAdapter
      config:
        data_dir: /path/to/csv/files
```

### Option 2: Programmatic

```python
from src.data.manager import DataManager
from src.data.adapters.csv_adapter import CSVDataAdapter

manager = DataManager()
csv_adapter = CSVDataAdapter("/path/to/csv/files")
manager.register_adapter("csv", csv_adapter)

# Use adapter
bars = await manager.get_historical_bars(
    symbol="AAPL",
    start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
    source="csv",
)
```

---

## Real-World Example: Alpha Vantage Adapter

Reference implementation at `src/data/adapters/alpha_vantage_adapter.py`:

**Key features:**
- Rate limiting (5 req/min free tier)
- Retry with exponential backoff
- API error handling
- Response parsing and normalization
- Health check via test API call

**Study this adapter** for best practices on API integration.

---

## Best Practices

1. **Always implement rate limiting** for API adapters (avoid bans)
2. **Retry transient errors** (network issues, timeouts) with exponential backoff
3. **Return empty list for "no data"** rather than raising exceptions
4. **Log all API calls** for debugging and audit trail
5. **Normalize timestamps to UTC** — use timezone-aware `datetime` objects
6. **Cache responses** for frequently accessed data (use Redis with TTL)
7. **Test health check** — ensure it's fast (<1s) and reliable
8. **Handle API changes** — version your adapter, don't assume API stability
9. **Document data format** — CSV schema, API response structure, units (USD, shares, etc.)
10. **Respect provider TOS** — don't exceed rate limits, don't resell data

---

## Advanced: WebSocket Feed Adapter

For real-time streaming data:

```python
from src.core.interfaces import DataSourceInterface

class WebSocketFeedAdapter(DataSourceInterface):
    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._ws = None
        self._subscribers: dict[str, list[callable]] = {}

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        self._ws = await websockets.connect(self._ws_url)
        asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        """Listen for messages and dispatch to subscribers."""
        async for message in self._ws:
            data = json.loads(message)
            symbol = data["symbol"]
            if symbol in self._subscribers:
                bar = self._parse_bar(data)
                for callback in self._subscribers[symbol]:
                    await callback(bar)

    async def subscribe(self, symbol: str, callback: callable) -> None:
        """Subscribe to real-time updates for a symbol."""
        if symbol not in self._subscribers:
            self._subscribers[symbol] = []
        self._subscribers[symbol].append(callback)

        # Send subscription message to server
        await self._ws.send(json.dumps({"action": "subscribe", "symbol": symbol}))
```

See `src/data/feeds/ibkr_feed.py` for a complete WebSocket feed implementation.

---

## Next Steps

- Read existing adapters in `src/data/adapters/` for examples
- Check [Data Pipeline](../modules/data.md) for integration points
- Review [ADR-002](../../specs/adrs/002-market-data-strategy.md) for data source selection criteria

---

<!-- DIAGRAM: Data adapter architecture showing interface, rate limiter, error handling, and storage integration -->
