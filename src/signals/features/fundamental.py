"""Fundamental feature calculator with sector-relative rankings."""

from __future__ import annotations

import pandas as pd
from scipy import stats

from src.core.models import FundamentalData


def _percentile_rank(value: float, values: list[float]) -> float:
    """Compute percentile rank (0-1) of value within values.

    Single-element lists return 0.5.
    """
    if len(values) <= 1:
        return 0.5
    rank = stats.percentileofscore(values, value, kind="rank") / 100.0
    return rank


class FundamentalFeatureCalculator:
    """Compute fundamental features with sector-relative rankings."""

    # Valuation metrics where lower is better (inverted ranking)
    _INVERTED = {"pe_ratio", "pb_ratio", "ps_ratio", "ev_ebitda", "debt_to_equity"}

    # All rankable fields and whether they are inverted
    _RANK_FIELDS = {
        "pe_ratio": "pe_sector_rank",
        "pb_ratio": "pb_sector_rank",
        "ps_ratio": "ps_sector_rank",
        "ev_ebitda": "ev_ebitda_sector_rank",
        "roe": "roe_sector_rank",
        "revenue_growth": "revenue_growth_rank",
        "earnings_growth": "earnings_growth_rank",
        "debt_to_equity": "debt_to_equity_rank",
        "dividend_yield": "dividend_yield_rank",
    }

    def compute(
        self,
        target: FundamentalData,
        sector_peers: list[FundamentalData],
    ) -> dict[str, float | None]:
        """Compute fundamental features for one stock relative to its sector peers.

        Returns dict of feature_name -> value (None for missing data).
        """
        features: dict[str, float | None] = {}

        # Compute sector percentile ranks for each field
        for field, feature_name in self._RANK_FIELDS.items():
            target_val = getattr(target, field)
            if target_val is None:
                features[feature_name] = None
                continue

            # Collect non-None peer values (including target)
            peer_vals = [
                getattr(p, field)
                for p in sector_peers
                if getattr(p, field) is not None
            ]
            if not peer_vals:
                features[feature_name] = None
                continue

            rank = _percentile_rank(target_val, peer_vals)
            # Invert for metrics where lower is better
            if field in self._INVERTED:
                rank = 1.0 - rank
            features[feature_name] = rank

        # Current ratio flag
        cr = target.current_ratio
        if cr is None:
            features["current_ratio_flag"] = None
        elif cr > 1.5:
            features["current_ratio_flag"] = 1.0
        elif cr > 1.0:
            features["current_ratio_flag"] = 0.5
        else:
            features["current_ratio_flag"] = 0.0

        # Quality score: average of ROE rank and current_ratio rank (normalized)
        roe_rank = features.get("roe_sector_rank")
        cr_rank = self._current_ratio_rank(target, sector_peers)
        if roe_rank is not None and cr_rank is not None:
            features["quality_score"] = (roe_rank + cr_rank) / 2.0
        else:
            features["quality_score"] = None

        # Value composite: average of inverted PE, PB, PS ranks
        val_ranks = [
            features.get(k)
            for k in ("pe_sector_rank", "pb_sector_rank", "ps_sector_rank")
        ]
        non_none_vals = [v for v in val_ranks if v is not None]
        features["value_composite"] = (
            sum(non_none_vals) / len(non_none_vals) if non_none_vals else None
        )

        # Growth composite: average of revenue and earnings growth ranks
        growth_ranks = [
            features.get(k)
            for k in ("revenue_growth_rank", "earnings_growth_rank")
        ]
        non_none_growth = [v for v in growth_ranks if v is not None]
        features["growth_composite"] = (
            sum(non_none_growth) / len(non_none_growth) if non_none_growth else None
        )

        return features

    def compute_batch(
        self,
        fundamentals: list[FundamentalData],
    ) -> pd.DataFrame:
        """Compute features for multiple stocks. Groups by sector automatically.

        Returns DataFrame with symbol as index and feature columns.
        """
        if not fundamentals:
            return pd.DataFrame()

        # Group by sector
        sector_groups: dict[str, list[FundamentalData]] = {}
        for fd in fundamentals:
            sector_groups.setdefault(fd.sector, []).append(fd)

        rows: list[dict[str, float | None]] = []
        symbols: list[str] = []

        for sector, peers in sector_groups.items():
            for stock in peers:
                features = self.compute(stock, peers)
                rows.append(features)
                symbols.append(stock.symbol)

        df = pd.DataFrame(rows, index=symbols)
        df.index.name = "symbol"
        return df

    def _current_ratio_rank(
        self,
        target: FundamentalData,
        sector_peers: list[FundamentalData],
    ) -> float | None:
        """Percentile rank of current_ratio within sector (higher = better)."""
        if target.current_ratio is None:
            return None
        peer_vals = [
            p.current_ratio for p in sector_peers if p.current_ratio is not None
        ]
        if not peer_vals:
            return None
        return _percentile_rank(target.current_ratio, peer_vals)
