"""Alternative data feature calculator for ML signal pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.core.models import InsiderTransaction, ShortInterestData


class AlternativeFeatureCalculator:
    """Compute features from insider transactions and short interest data."""

    def compute_insider_features(
        self,
        transactions: list[InsiderTransaction],
        as_of_dates: list[datetime],
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Compute insider transaction features for given dates."""
        if not as_of_dates:
            return pd.DataFrame(
                columns=[
                    "insider_buy_ratio",
                    "insider_net_shares",
                    "insider_buy_count",
                    "insider_sell_count",
                    "insider_cluster_buy",
                ]
            )

        index = pd.DatetimeIndex(sorted(as_of_dates), name="date")
        features = pd.DataFrame(index=index)

        if not transactions:
            for col in [
                "insider_buy_ratio",
                "insider_net_shares",
                "insider_buy_count",
                "insider_sell_count",
                "insider_cluster_buy",
            ]:
                features[col] = np.nan
            return features

        buy_ratios = []
        net_shares = []
        buy_counts = []
        sell_counts = []
        cluster_buys = []

        for dt in index:
            cutoff = dt - timedelta(days=lookback_days)
            window = [
                t
                for t in transactions
                if cutoff <= t.filed_date <= dt
                and t.transaction_type in ("P", "S")
            ]
            buys = [t for t in window if t.transaction_type == "P"]
            sells = [t for t in window if t.transaction_type == "S"]

            total = len(buys) + len(sells)
            if total == 0:
                buy_ratios.append(np.nan)
                net_shares.append(np.nan)
                buy_counts.append(0)
                sell_counts.append(0)
                cluster_buys.append(0)
            else:
                buy_ratios.append(len(buys) / total)
                bought = sum(t.shares for t in buys)
                sold = sum(t.shares for t in sells)
                net_shares.append(bought - sold)
                buy_counts.append(len(buys))
                sell_counts.append(len(sells))
                cluster_buys.append(1 if len(buys) >= 3 else 0)

        features["insider_buy_ratio"] = buy_ratios
        features["insider_net_shares"] = net_shares
        features["insider_buy_count"] = buy_counts
        features["insider_sell_count"] = sell_counts
        features["insider_cluster_buy"] = cluster_buys

        return features

    def compute_short_interest_features(
        self,
        short_data: list[ShortInterestData],
        as_of_dates: list[datetime],
    ) -> pd.DataFrame:
        """Compute short interest features for given dates."""
        if not as_of_dates:
            return pd.DataFrame(
                columns=[
                    "short_interest_ratio",
                    "short_pct_float",
                    "short_interest_change",
                    "short_interest_zscore",
                ]
            )

        index = pd.DatetimeIndex(sorted(as_of_dates), name="date")
        features = pd.DataFrame(index=index)

        if not short_data:
            for col in [
                "short_interest_ratio",
                "short_pct_float",
                "short_interest_change",
                "short_interest_zscore",
            ]:
                features[col] = np.nan
            return features

        # Build a DataFrame from short interest data, sorted by date
        si_df = pd.DataFrame([s.model_dump() for s in short_data])
        si_df = si_df.sort_values("settlement_date").reset_index(drop=True)

        si_ratios = []
        si_pct_floats = []
        si_changes = []
        si_zscores = []

        for dt in index:
            # Find the most recent short interest report on or before as_of_date
            available = si_df[si_df["settlement_date"] <= dt]
            if available.empty:
                si_ratios.append(np.nan)
                si_pct_floats.append(np.nan)
                si_changes.append(np.nan)
                si_zscores.append(np.nan)
                continue

            latest = available.iloc[-1]

            # Short interest ratio (days to cover)
            if latest["avg_daily_volume"] > 0:
                si_ratios.append(latest["short_interest"] / latest["avg_daily_volume"])
            else:
                si_ratios.append(np.nan)

            si_pct_floats.append(latest.get("short_pct_float", np.nan))
            si_changes.append(latest.get("change_pct", np.nan))

            # Z-score of current short interest vs all historical data up to this date
            hist_si = available["short_interest"].values
            if len(hist_si) >= 2:
                mean = hist_si.mean()
                std = hist_si.std(ddof=1)
                if std > 0:
                    si_zscores.append((latest["short_interest"] - mean) / std)
                else:
                    si_zscores.append(0.0)
            else:
                si_zscores.append(np.nan)

        features["short_interest_ratio"] = si_ratios
        features["short_pct_float"] = si_pct_floats
        features["short_interest_change"] = si_changes
        features["short_interest_zscore"] = si_zscores

        return features
