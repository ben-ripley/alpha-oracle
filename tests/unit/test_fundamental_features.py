"""Tests for FundamentalFeatureCalculator."""

from datetime import datetime

import pytest

from src.core.models import FundamentalData
from src.signals.features.fundamental import FundamentalFeatureCalculator


def _make_stock(
    symbol: str,
    sector: str = "Technology",
    **kwargs,
) -> FundamentalData:
    return FundamentalData(
        symbol=symbol,
        timestamp=datetime(2026, 1, 15),
        sector=sector,
        **kwargs,
    )


@pytest.fixture
def calc():
    return FundamentalFeatureCalculator()


class TestSectorPercentileRanking:
    """Sector percentile ranking: 5 tech stocks with known PE ratios."""

    def test_pe_rank_order(self, calc):
        # Lower PE = higher rank (inverted)
        peers = [
            _make_stock("A", pe_ratio=10.0),
            _make_stock("B", pe_ratio=15.0),
            _make_stock("C", pe_ratio=20.0),
            _make_stock("D", pe_ratio=25.0),
            _make_stock("E", pe_ratio=30.0),
        ]
        rank_a = calc.compute(peers[0], peers)["pe_sector_rank"]
        rank_e = calc.compute(peers[4], peers)["pe_sector_rank"]
        # A has lowest PE -> highest rank
        assert rank_a > rank_e
        # A should be near 1.0, E near 0.0
        assert rank_a > 0.7
        assert rank_e < 0.3


class TestQualityScore:
    """Quality score formula with known ROE and current_ratio."""

    def test_quality_score_calculation(self, calc):
        peers = [
            _make_stock("LOW", roe=0.05, current_ratio=0.8),
            _make_stock("MID", roe=0.12, current_ratio=1.2),
            _make_stock("HIGH", roe=0.20, current_ratio=2.0),
            _make_stock("TOP", roe=0.25, current_ratio=2.5),
        ]
        target = peers[2]  # HIGH: roe=0.20, current_ratio=2.0
        features = calc.compute(target, peers)
        # ROE rank should be high (0.20 is 3rd of 4 values)
        assert features["roe_sector_rank"] is not None
        assert features["roe_sector_rank"] > 0.5
        # Quality score is average of ROE rank and current_ratio rank
        assert features["quality_score"] is not None
        assert 0.0 <= features["quality_score"] <= 1.0


class TestValueComposite:
    """Value composite: average of inverted PE/PB/PS ranks."""

    def test_value_composite(self, calc):
        peers = [
            _make_stock("CHEAP", pe_ratio=8.0, pb_ratio=1.0, ps_ratio=0.5),
            _make_stock("MID", pe_ratio=15.0, pb_ratio=2.5, ps_ratio=2.0),
            _make_stock("PRICEY", pe_ratio=30.0, pb_ratio=5.0, ps_ratio=4.0),
        ]
        cheap_features = calc.compute(peers[0], peers)
        pricey_features = calc.compute(peers[2], peers)
        # Cheap stock should have higher value composite than pricey one
        assert cheap_features["value_composite"] > pricey_features["value_composite"]
        # Cheap stock should be near 1.0
        assert cheap_features["value_composite"] > 0.5


class TestMissingFundamentals:
    """Missing fundamentals (None fields) produce None, not crashes."""

    def test_none_fields_produce_none(self, calc):
        peers = [
            _make_stock("A", pe_ratio=10.0),
            _make_stock("B"),  # All metrics None
        ]
        features = calc.compute(peers[1], peers)
        assert features["pe_sector_rank"] is None
        assert features["value_composite"] is None
        assert features["quality_score"] is None
        assert features["growth_composite"] is None
        assert features["current_ratio_flag"] is None

    def test_partial_none_no_crash(self, calc):
        peers = [
            _make_stock("A", pe_ratio=10.0, pb_ratio=2.0),
            _make_stock("B", pe_ratio=15.0),  # pb_ratio is None
        ]
        features = calc.compute(peers[1], peers)
        assert features["pe_sector_rank"] is not None
        assert features["pb_sector_rank"] is None
        # Value composite uses only available ranks
        assert features["value_composite"] is not None


class TestSingleStockInSector:
    """Single stock in sector gets rank 0.5 (middle)."""

    def test_single_stock_rank(self, calc):
        stock = _make_stock(
            "ALONE",
            pe_ratio=20.0,
            pb_ratio=3.0,
            roe=0.15,
            revenue_growth=0.10,
            earnings_growth=0.08,
            debt_to_equity=0.5,
            dividend_yield=0.02,
            current_ratio=1.8,
        )
        features = calc.compute(stock, [stock])
        # With a single stock, percentile rank is 0.5
        # Inverted fields: 1.0 - 0.5 = 0.5
        assert features["pe_sector_rank"] == pytest.approx(0.5)
        assert features["roe_sector_rank"] == pytest.approx(0.5)
        assert features["value_composite"] == pytest.approx(0.5)
        assert features["growth_composite"] == pytest.approx(0.5)


class TestBatchCompute:
    """Batch compute groups by sector correctly."""

    def test_batch_groups_by_sector(self, calc):
        stocks = [
            _make_stock("AAPL", sector="Technology", pe_ratio=25.0, roe=0.30),
            _make_stock("MSFT", sector="Technology", pe_ratio=30.0, roe=0.25),
            _make_stock("GOOG", sector="Technology", pe_ratio=20.0, roe=0.20),
            _make_stock("JPM", sector="Finance", pe_ratio=12.0, roe=0.12),
            _make_stock("BAC", sector="Finance", pe_ratio=10.0, roe=0.08),
        ]
        df = calc.compute_batch(stocks)
        assert len(df) == 5
        assert df.index.name == "symbol"
        assert set(df.index) == {"AAPL", "MSFT", "GOOG", "JPM", "BAC"}
        # GOOG has lowest PE in tech -> highest pe_sector_rank in tech
        assert df.loc["GOOG", "pe_sector_rank"] > df.loc["MSFT", "pe_sector_rank"]
        # BAC has lowest PE in finance -> highest pe_sector_rank in finance
        assert df.loc["BAC", "pe_sector_rank"] > df.loc["JPM", "pe_sector_rank"]

    def test_batch_empty_list(self, calc):
        df = calc.compute_batch([])
        assert df.empty
