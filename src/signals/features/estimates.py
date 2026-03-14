"""Analyst estimates feature calculator for ML signal pipeline."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.core.models import AnalystEstimate

_ESTIMATES_COLS = [
    "earnings_surprise_pct",
    "earnings_revision_momentum",
    "revenue_surprise_pct",
    "analyst_coverage_count",
    "estimate_dispersion",
]


class EstimatesFeatureCalculator:
    """Compute analyst estimate features with point-in-time safety."""

    def compute(
        self,
        estimates: list[AnalystEstimate] | None,
        as_of_dates: list[datetime],
    ) -> pd.DataFrame:
        """Compute estimate features for each as_of_date.

        Returns DataFrame indexed by date. NaN columns when no data (graceful degradation).
        """
        if not as_of_dates:
            return pd.DataFrame(columns=_ESTIMATES_COLS)

        index = pd.DatetimeIndex(sorted(as_of_dates), name="date")
        features = pd.DataFrame(index=index)

        if not estimates:
            for col in _ESTIMATES_COLS:
                features[col] = np.nan
            return features

        # Sort estimates by fiscal_date_ending (PIT proxy)
        sorted_estimates = sorted(estimates, key=lambda e: e.fiscal_date_ending)

        surprise_pcts, revision_momentums, revenue_surprises, coverages, dispersions = (
            [], [], [], [], []
        )

        for dt in index:
            # PIT: use estimates whose fiscal_date_ending <= as_of_date string
            dt_str = dt.strftime("%Y-%m-%d")
            available = [e for e in sorted_estimates if e.fiscal_date_ending <= dt_str]

            if not available:
                surprise_pcts.append(np.nan)
                revision_momentums.append(np.nan)
                revenue_surprises.append(np.nan)
                coverages.append(np.nan)
                dispersions.append(np.nan)
                continue

            latest = available[-1]

            # Earnings surprise pct (use model field if present)
            surprise_pcts.append(
                float(latest.surprise_pct) if latest.surprise_pct is not None else np.nan
            )

            # Coverage count from most recent estimate
            coverages.append(float(latest.num_analysts))

            # Revision momentum: compare latest surprise vs prior
            prior = available[-2] if len(available) >= 2 else None
            if prior is not None and prior.surprise_pct is not None and latest.surprise_pct is not None:
                revision_momentums.append(float(latest.surprise_pct) - float(prior.surprise_pct))
            else:
                revision_momentums.append(np.nan)

            # Revenue surprise: not separately modeled in AV data, use earnings as proxy
            revenue_surprises.append(
                float(latest.surprise_pct) if latest.surprise_pct is not None else np.nan
            )

            # Estimate dispersion: std of consensus estimates over last 4 quarters
            recent = available[-4:]
            consenses = [e.consensus_estimate for e in recent]
            if len(consenses) >= 2:
                dispersions.append(float(np.std(consenses, ddof=1)))
            else:
                dispersions.append(np.nan)

        features["earnings_surprise_pct"] = surprise_pcts
        features["earnings_revision_momentum"] = revision_momentums
        features["revenue_surprise_pct"] = revenue_surprises
        features["analyst_coverage_count"] = coverages
        features["estimate_dispersion"] = dispersions

        return features
