"""
portfolio/risk.py — Point-in-Time Portfolio Risk Model and Covariance Matrix Construction.

Provides:
  - Historical return covariance matrix computed strictly using data <= T
  - Fallback logic for singular/insufficient covariance with explicit diagnostic flag
  - Portfolio variance (w^T * Sigma * w) and volatility (sqrt(w^T * Sigma * w))
  - Marginal and percentage risk contributions per asset and sector
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class PortfolioRiskModel:
    """
    Evaluates multi-asset portfolio risk using historical point-in-time returns.
    
    Zero-lookahead: All returns used in covariance and volatility are strictly <= as_of_date.
    """

    @staticmethod
    def compute_covariance_matrix(
        market_bars: Dict[str, pd.DataFrame],
        symbols: List[str],
        as_of_date: Union[str, pd.Timestamp],
        lookback_bars: int = 60,
        price_col: str = "close",
        timestamp_col: str = "timestamp",
    ) -> Tuple[pd.DataFrame, bool]:
        """
        Compute historical daily return covariance matrix strictly using data <= as_of_date.

        Parameters:
            market_bars: Dictionary mapping symbol to historical DataFrame.
            symbols: List of symbols to evaluate.
            as_of_date: Evaluation timestamp/date.
            lookback_bars: Lookback window for covariance estimation.

        Returns:
            Tuple of (cov_matrix: pd.DataFrame, is_fallback: bool)
        """
        target_dt = pd.to_datetime(as_of_date)
        ts_tz = target_dt.tzinfo

        returns_dict: Dict[str, pd.Series] = {}
        for sym in symbols:
            if sym not in market_bars or market_bars[sym].empty:
                continue
            df = market_bars[sym].copy()
            df[timestamp_col] = pd.to_datetime(df[timestamp_col])

            # Timezone reconciliation
            if ts_tz is not None and df[timestamp_col].dt.tz is None:
                df[timestamp_col] = df[timestamp_col].dt.tz_localize(ts_tz)
            elif ts_tz is None and df[timestamp_col].dt.tz is not None:
                df[timestamp_col] = df[timestamp_col].dt.tz_localize(None)

            # Filter strictly <= as_of_date
            hist_df = df[df[timestamp_col] <= target_dt].sort_values(timestamp_col)
            if len(hist_df) >= 5:
                tail_df = hist_df.tail(lookback_bars + 1).copy()
                ret = tail_df[price_col].astype(float).pct_change().dropna()
                if len(ret) >= 5:
                    returns_dict[sym] = ret.reset_index(drop=True)

        # Check sufficiency: all requested symbols must have returns
        all_present = all(sym in returns_dict for sym in symbols) and len(returns_dict) > 0

        if not all_present or len(symbols) == 0:
            # Fallback: diagonal variance matrix with conservative assumptions
            is_fallback = True
            cov_df = pd.DataFrame(index=symbols, columns=symbols, dtype=float)
            for sym in symbols:
                if sym in returns_dict and len(returns_dict[sym]) > 1:
                    var_val = float(returns_dict[sym].var())
                else:
                    # Default conservative 2% daily volatility (4e-4 variance)
                    var_val = 0.02 ** 2
                cov_df.loc[sym, sym] = var_val
            # Fill off-diagonals with zero
            cov_df = cov_df.fillna(0.0)
            return cov_df, is_fallback

        # Aligned covariance estimation
        ret_df = pd.DataFrame(returns_dict)[symbols]
        cov_matrix = ret_df.cov()

        # Check for numerical singularity / NaN values
        if cov_matrix.isna().any().any() or np.linalg.matrix_rank(cov_matrix.values) < min(len(symbols), 2):
            is_fallback = True
            # Regularize with shrinkage towards diagonal
            diag_vals = np.diag(cov_matrix.values)
            cov_matrix = pd.DataFrame(np.diag(diag_vals), index=symbols, columns=symbols)
            cov_matrix = cov_matrix.fillna(0.02 ** 2)
        else:
            is_fallback = False

        return cov_matrix, is_fallback

    @staticmethod
    def calculate_portfolio_variance(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
        """Calculate portfolio variance: w^T * Sigma * w."""
        w = np.asarray(weights, dtype=float)
        sigma = np.asarray(cov_matrix, dtype=float)
        var = float(np.dot(w.T, np.dot(sigma, w)))
        return max(0.0, var)

    @staticmethod
    def calculate_portfolio_volatility(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
        """Calculate portfolio volatility: sqrt(w^T * Sigma * w)."""
        var = PortfolioRiskModel.calculate_portfolio_variance(weights, cov_matrix)
        return float(np.sqrt(var))

    @staticmethod
    def calculate_risk_contributions(
        weights: np.ndarray,
        cov_matrix: np.ndarray,
        symbols: List[str],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Calculate Marginal Risk Contribution (MRC) and Percentage Risk Contribution (PRC).

        MRC_i = (Sigma * w)_i / sigma_p
        PRC_i = w_i * MRC_i / sigma_p
        """
        w = np.asarray(weights, dtype=float)
        sigma = np.asarray(cov_matrix, dtype=float)
        port_vol = PortfolioRiskModel.calculate_portfolio_volatility(w, sigma)

        mrc_dict: Dict[str, float] = {}
        prc_dict: Dict[str, float] = {}

        if port_vol <= 1e-8 or np.sum(w) <= 1e-8:
            for sym in symbols:
                mrc_dict[sym] = 0.0
                prc_dict[sym] = 0.0
            return mrc_dict, prc_dict

        sigma_w = np.dot(sigma, w)
        for idx, sym in enumerate(symbols):
            mrc = float(sigma_w[idx] / port_vol)
            prc = float((w[idx] * sigma_w[idx]) / (port_vol ** 2))
            mrc_dict[sym] = mrc
            prc_dict[sym] = prc

        return mrc_dict, prc_dict

    @staticmethod
    def calculate_sector_risk_contributions(
        percentage_risk_contributions: Dict[str, float],
        sector_lookup: Dict[str, str],
    ) -> Dict[str, float]:
        """Aggregate percentage risk contributions by sector."""
        sector_prc: Dict[str, float] = {}
        for sym, prc in percentage_risk_contributions.items():
            sec = sector_lookup.get(sym, "Unclassified")
            sector_prc[sec] = sector_prc.get(sec, 0.0) + prc
        return sector_prc
