"""Tests for AlternativeFeatureCalculator."""
from datetime import datetime, timedelta

import numpy as np
import pytest

from src.core.models import InsiderTransaction, ShortInterestData
from src.signals.features.alternative import AlternativeFeatureCalculator


@pytest.fixture
def calc():
    return AlternativeFeatureCalculator()


def _make_insider_txn(
    symbol: str,
    filed_date: datetime,
    txn_type: str,
    shares: float = 1000.0,
) -> InsiderTransaction:
    return InsiderTransaction(
        symbol=symbol,
        filed_date=filed_date,
        insider_name="John Doe",
        insider_title="CEO",
        transaction_type=txn_type,
        shares=shares,
    )


class TestInsiderBuyRatio:
    def test_buy_ratio(self, calc):
        """3 buys, 2 sales -> ratio = 0.6."""
        base = datetime(2024, 6, 1)
        txns = [
            _make_insider_txn("AAPL", base - timedelta(days=10), "P"),
            _make_insider_txn("AAPL", base - timedelta(days=20), "P"),
            _make_insider_txn("AAPL", base - timedelta(days=30), "P"),
            _make_insider_txn("AAPL", base - timedelta(days=40), "S"),
            _make_insider_txn("AAPL", base - timedelta(days=50), "S"),
        ]
        features = calc.compute_insider_features(txns, [base])
        assert features["insider_buy_ratio"].iloc[0] == pytest.approx(0.6)

    def test_cluster_buy_detected(self, calc):
        """3+ buys in 90 days -> cluster_buy = 1."""
        base = datetime(2024, 6, 1)
        txns = [
            _make_insider_txn("AAPL", base - timedelta(days=10), "P"),
            _make_insider_txn("AAPL", base - timedelta(days=20), "P"),
            _make_insider_txn("AAPL", base - timedelta(days=30), "P"),
        ]
        features = calc.compute_insider_features(txns, [base])
        assert features["insider_cluster_buy"].iloc[0] == 1

    def test_no_cluster_with_fewer_buys(self, calc):
        """Fewer than 3 buys -> cluster_buy = 0."""
        base = datetime(2024, 6, 1)
        txns = [
            _make_insider_txn("AAPL", base - timedelta(days=10), "P"),
            _make_insider_txn("AAPL", base - timedelta(days=20), "P"),
        ]
        features = calc.compute_insider_features(txns, [base])
        assert features["insider_cluster_buy"].iloc[0] == 0

    def test_net_shares(self, calc):
        """10000 bought - 5000 sold = 5000 net."""
        base = datetime(2024, 6, 1)
        txns = [
            _make_insider_txn("AAPL", base - timedelta(days=10), "P", shares=10000),
            _make_insider_txn("AAPL", base - timedelta(days=20), "S", shares=5000),
        ]
        features = calc.compute_insider_features(txns, [base])
        assert features["insider_net_shares"].iloc[0] == pytest.approx(5000)


class TestInsiderEmpty:
    def test_empty_transactions(self, calc):
        """Empty transaction list returns NaN columns."""
        features = calc.compute_insider_features([], [datetime(2024, 6, 1)])
        assert features["insider_buy_ratio"].isna().all()
        assert features["insider_net_shares"].isna().all()


class TestShortInterest:
    def test_short_interest_ratio(self, calc):
        """Short interest / avg daily volume gives days to cover."""
        base = datetime(2024, 6, 1)
        data = [
            ShortInterestData(
                symbol="AAPL",
                settlement_date=base - timedelta(days=5),
                short_interest=10_000_000,
                avg_daily_volume=2_000_000,
                days_to_cover=5.0,
                short_pct_float=8.5,
                change_pct=2.0,
            )
        ]
        features = calc.compute_short_interest_features(data, [base])
        assert features["short_interest_ratio"].iloc[0] == pytest.approx(5.0)
        assert features["short_pct_float"].iloc[0] == pytest.approx(8.5)
        assert features["short_interest_change"].iloc[0] == pytest.approx(2.0)

    def test_short_interest_zscore(self, calc):
        """Z-score should reflect position relative to historical mean/std."""
        base = datetime(2024, 6, 1)
        # Mean = 5M, std ≈ known. Last value = 8M.
        data = [
            ShortInterestData(
                symbol="AAPL",
                settlement_date=base - timedelta(days=60),
                short_interest=4_000_000,
                avg_daily_volume=1_000_000,
            ),
            ShortInterestData(
                symbol="AAPL",
                settlement_date=base - timedelta(days=45),
                short_interest=5_000_000,
                avg_daily_volume=1_000_000,
            ),
            ShortInterestData(
                symbol="AAPL",
                settlement_date=base - timedelta(days=30),
                short_interest=6_000_000,
                avg_daily_volume=1_000_000,
            ),
            ShortInterestData(
                symbol="AAPL",
                settlement_date=base - timedelta(days=15),
                short_interest=5_000_000,
                avg_daily_volume=1_000_000,
            ),
            ShortInterestData(
                symbol="AAPL",
                settlement_date=base - timedelta(days=5),
                short_interest=8_000_000,
                avg_daily_volume=1_000_000,
            ),
        ]
        features = calc.compute_short_interest_features(data, [base])
        zscore = features["short_interest_zscore"].iloc[0]
        # Mean = 5.6M, std ~= 1.517M, zscore = (8M - 5.6M)/1.517M ≈ 1.58
        assert zscore > 1.0, f"Expected positive z-score > 1, got {zscore}"

    def test_empty_short_data(self, calc):
        """Empty short interest data returns NaN columns."""
        features = calc.compute_short_interest_features([], [datetime(2024, 6, 1)])
        assert features["short_interest_ratio"].isna().all()
        assert features["short_pct_float"].isna().all()
        assert features["short_interest_change"].isna().all()
        assert features["short_interest_zscore"].isna().all()
