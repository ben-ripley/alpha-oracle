"""Options flow feature calculator for ML signal pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.core.models import OptionsFlowRecord

_OPTIONS_COLS = [
    "put_call_ratio",
    "put_call_ratio_zscore",
    "unusual_options_activity",
    "options_volume_ratio",
]


class OptionsFlowFeatureCalculator:
    """Compute options flow features with point-in-time safety."""

    def compute(
        self,
        records: list[OptionsFlowRecord] | None,
        as_of_dates: list[datetime],
        lookback_days: int = 30,
    ) -> pd.DataFrame:
        """Compute options flow features for each as_of_date.

        Returns DataFrame indexed by date. NaN columns when no data (graceful degradation).
        """
        if not as_of_dates:
            return pd.DataFrame(columns=_OPTIONS_COLS)

        index = pd.DatetimeIndex(sorted(as_of_dates), name="date")
        features = pd.DataFrame(index=index)

        if not records:
            for col in _OPTIONS_COLS:
                features[col] = np.nan
            return features

        sorted_records = sorted(records, key=lambda r: r.timestamp)

        put_call_ratios, pcr_zscores, unusual_flags, volume_ratios = (
            [], [], [], []
        )

        for dt in index:
            dt_naive = dt.to_pydatetime().replace(tzinfo=None)

            # All records up to as_of_date within lookback window
            window = [
                r for r in sorted_records
                if r.timestamp.replace(tzinfo=None) <= dt_naive
                and r.timestamp.replace(tzinfo=None) > (dt_naive - timedelta(days=lookback_days))
            ]

            if not window:
                put_call_ratios.append(np.nan)
                pcr_zscores.append(np.nan)
                unusual_flags.append(np.nan)
                volume_ratios.append(np.nan)
                continue

            latest = window[-1]
            pcr = float(latest.put_call_ratio)
            put_call_ratios.append(pcr)

            # Unusual activity: latest record flag
            unusual_flags.append(1.0 if latest.unusual_activity else 0.0)

            # PCR z-score over lookback window
            all_pcr = [r.put_call_ratio for r in window]
            if len(all_pcr) >= 2:
                mean_pcr = float(np.mean(all_pcr))
                std_pcr = float(np.std(all_pcr, ddof=1))
                if std_pcr > 0:
                    pcr_zscores.append((pcr - mean_pcr) / std_pcr)
                else:
                    pcr_zscores.append(0.0)
            else:
                pcr_zscores.append(np.nan)

            # Volume ratio: put_volume / (put_volume + call_volume)
            total_vol = latest.put_volume + latest.call_volume
            if total_vol > 0:
                volume_ratios.append(float(latest.put_volume) / total_vol)
            else:
                volume_ratios.append(np.nan)

        features["put_call_ratio"] = put_call_ratios
        features["put_call_ratio_zscore"] = pcr_zscores
        features["unusual_options_activity"] = unusual_flags
        features["options_volume_ratio"] = volume_ratios

        return features
