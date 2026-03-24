"""Temporal/calendar feature calculator for ML signal pipeline."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd


class TemporalFeatureCalculator:
    """Compute temporal/calendar features."""

    def compute(self, dates: list[datetime]) -> pd.DataFrame:
        """Compute temporal features for given dates.

        Features:
        - day_of_week: 0-4 (Mon-Fri)
        - month: 1-12
        - quarter: 1-4
        - is_month_end: 1 if last 3 business days of month, else 0
        - is_month_start: 1 if first 3 business days of month, else 0
        - is_quarter_end: 1 if last week of quarter
        - week_of_year: 1-52
        - days_since_year_start: 0-365
        """
        if not dates:
            return pd.DataFrame(
                columns=[
                    "day_of_week",
                    "month",
                    "quarter",
                    "is_month_end",
                    "is_month_start",
                    "is_quarter_end",
                    "week_of_year",
                    "days_since_year_start",
                ]
            )

        index = pd.DatetimeIndex(sorted(dates))
        features = pd.DataFrame(index=index)

        features["day_of_week"] = index.dayofweek
        features["month"] = index.month
        features["quarter"] = index.quarter
        features["week_of_year"] = index.isocalendar().week.values.astype(int)
        features["days_since_year_start"] = index.dayofyear - 1

        # is_month_end: 1 if within last 3 business days of month
        month_ends = []
        for dt in index:
            month_end = pd.Timestamp(dt) + pd.offsets.MonthEnd(0)
            # Count business days from dt to month end
            bdays = np.busday_count(
                np.datetime64(dt, "D"),
                np.datetime64(month_end.date(), "D"),
            )
            month_ends.append(1 if bdays <= 3 else 0)
        features["is_month_end"] = month_ends

        # is_month_start: 1 if within first 3 business days of month
        month_starts = []
        for dt in index:
            month_start = pd.Timestamp(dt).replace(day=1)
            bdays = np.busday_count(
                np.datetime64(month_start.date(), "D"),
                np.datetime64(dt, "D"),
            )
            month_starts.append(1 if bdays < 3 else 0)
        features["is_month_start"] = month_starts

        # is_quarter_end: 1 if in last week of quarter (last 5 business days)
        quarter_ends = []
        for dt in index:
            q_end_month = ((pd.Timestamp(dt).quarter) * 3)
            q_end = pd.Timestamp(year=dt.year, month=q_end_month, day=1) + pd.offsets.MonthEnd(0)
            bdays = np.busday_count(
                np.datetime64(dt, "D"),
                np.datetime64(q_end.date(), "D"),
            )
            quarter_ends.append(1 if bdays <= 5 else 0)
        features["is_quarter_end"] = quarter_ends

        return features
