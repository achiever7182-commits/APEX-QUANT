"""
features/engine.py — Orchestrates single-stock and cross-sectional feature generation.

Transforms:
  Raw / Adjusted OHLCV Data
      ↓
  Price, Trend, Momentum, Volatility, Volume, Relative Strength, Market Regime
      ↓
  Feature Validation (no infs, domain checks, zero lookahead)
      ↓
  Optional Cross-Sectional Normalization (Z-Score, Rank, Winsorize per timestamp)
      ↓
  ML-Ready Cross-Sectional Dataset: [timestamp, symbol, feature_1, ..., feature_k]
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Union
import pandas as pd

from features.models import FeatureConfig, FeatureSet
from features.price import calculate_price_features
from features.trend import calculate_trend_features
from features.momentum import calculate_momentum_features
from features.volatility import calculate_volatility_features
from features.volume import calculate_volume_features
from features.relative_strength import (
    BenchmarkProvider,
    calculate_relative_strength_features,
)
from features.market_regime import calculate_market_regime_features
from features.normalization import cross_sectional_zscore
from features.validators import FeatureValidator

logger = logging.getLogger("apex_quant.features")


class FeatureEngine:
    """
    Production-quality multi-stock feature engineering engine for Indian equities.

    Coordinates all feature modules and outputs zero-lookahead panel datasets.
    """

    def __init__(
        self,
        config: Optional[FeatureConfig] = None,
        benchmark_provider: Optional[BenchmarkProvider] = None,
    ):
        self.config = config or FeatureConfig()
        self.benchmark_provider = benchmark_provider

    def compute_stock_features(
        self,
        df: pd.DataFrame,
        symbol: str,
        benchmark_provider: Optional[BenchmarkProvider] = None,
    ) -> pd.DataFrame:
        """
        Extract all features for a single stock from its OHLCV DataFrame.

        Parameters:
            df: DataFrame containing at minimum 'timestamp', 'open', 'high', 'low', 'close', 'volume'.
            symbol: Ticker symbol (e.g. 'RELIANCE').
            benchmark_provider: Optional override for benchmark provider.

        Returns:
            DataFrame containing timestamp, symbol, all computed features, and sufficient_history flag.
        """
        if df.empty:
            return pd.DataFrame()

        clean = df.copy()
        clean["timestamp"] = pd.to_datetime(clean["timestamp"])
        clean = clean.sort_values("timestamp").reset_index(drop=True)

        bp = benchmark_provider or self.benchmark_provider

        # 1. Compute modular feature sets
        price_feats = calculate_price_features(
            clean,
            return_periods=self.config.return_periods,
            close_col="close",
            open_col="open",
            high_col="high",
            low_col="low",
        )

        trend_feats = calculate_trend_features(
            clean,
            sma_periods=self.config.sma_periods,
            ema_periods=self.config.ema_periods,
            close_col="close",
        )

        mom_feats = calculate_momentum_features(
            clean,
            rsi_period=self.config.rsi_period,
            roc_periods=self.config.roc_periods,
            mom_periods=self.config.mom_periods,
            close_col="close",
        )

        vol_feats = calculate_volatility_features(
            clean,
            volatility_periods=self.config.volatility_periods,
            atr_period=self.config.atr_period,
            downside_vol_period=self.config.downside_vol_period,
            close_col="close",
            high_col="high",
            low_col="low",
        )

        volume_feats = calculate_volume_features(
            clean,
            volume_sma_periods=self.config.volume_sma_periods,
            volume_momentum_period=self.config.volume_momentum_period,
            volume_col="volume",
            close_col="close",
        )

        # 2. Relative strength & market regime (if benchmark provider is available)
        rs_feats = pd.DataFrame(index=clean.index)
        regime_feats = pd.DataFrame(index=clean.index)
        if bp is not None:
            try:
                rs_feats = calculate_relative_strength_features(
                    clean,
                    bp,
                    relative_return_periods=self.config.relative_return_periods,
                    stock_close_col="close",
                    timestamp_col="timestamp",
                )
                regime_feats = calculate_market_regime_features(
                    clean,
                    bp,
                    sma_fast=self.config.regime_sma_fast,
                    sma_slow=self.config.regime_sma_slow,
                    return_period=self.config.regime_return_period,
                    volatility_period=self.config.regime_volatility_period,
                    timestamp_col="timestamp",
                )
            except Exception as e:
                logger.warning(f"Could not compute benchmark features for {symbol}: {e}")

        # 3. Concatenate all features
        all_feats = pd.concat(
            [price_feats, trend_feats, mom_feats, vol_feats, volume_feats, rs_feats, regime_feats],
            axis=1,
        )

        # 4. Attach identifiers and status flags
        result = pd.DataFrame(index=clean.index)
        result["timestamp"] = clean["timestamp"]
        result["symbol"] = symbol
        
        # Combine identifiers with feature columns
        for col in all_feats.columns:
            result[col] = all_feats[col]

        # Sufficient history flag: row index >= min_history_bars
        # (e.g. 60 bars for basic models, or full_warmup_bars for 200d MA)
        row_indices = pd.Series(range(len(result)), index=result.index)
        result["has_sufficient_history"] = row_indices >= self.config.min_history_bars
        result["has_full_warmup"] = row_indices >= self.config.full_warmup_bars

        return result

    def generate_cross_sectional_panel(
        self,
        stock_dfs: Dict[str, pd.DataFrame],
        benchmark_provider: Optional[BenchmarkProvider] = None,
        normalize: bool = False,
    ) -> FeatureSet:
        """
        Generate a multi-stock cross-sectional feature dataset from multiple OHLCV DataFrames.

        Parameters:
            stock_dfs: Mapping of symbol -> OHLCV DataFrame.
            benchmark_provider: Optional BenchmarkProvider. If None and config specifies,
                                a synthetic equal-weighted benchmark is constructed from stock_dfs.
            normalize: If True, applies cross-sectional z-score normalization per timestamp.

        Returns:
            FeatureSet containing the cross-sectional dataset and validation diagnostics.
        """
        if not stock_dfs:
            return FeatureSet(
                data=pd.DataFrame(),
                config=self.config,
                feature_columns=[],
                symbols=[],
            )

        # Construct synthetic benchmark if none provided
        bp = benchmark_provider or self.benchmark_provider
        if bp is None:
            try:
                bp = BenchmarkProvider.build_synthetic_equal_weighted_benchmark(stock_dfs)
                logger.info("Constructed synthetic equal-weighted benchmark for feature engine.")
            except Exception as e:
                logger.warning(f"Failed to build synthetic benchmark: {e}")

        # Compute single stock features
        stock_feature_list = []
        for symbol, df in stock_dfs.items():
            if df.empty:
                continue
            feats = self.compute_stock_features(df, symbol=symbol, benchmark_provider=bp)
            stock_feature_list.append(feats)

        if not stock_feature_list:
            return FeatureSet(
                data=pd.DataFrame(),
                config=self.config,
                feature_columns=[],
                symbols=list(stock_dfs.keys()),
            )

        # Combine into long-format cross-sectional panel
        panel = pd.concat(stock_feature_list, ignore_index=True)
        
        # Sort deterministically by timestamp then symbol
        panel = panel.sort_values(by=["timestamp", "symbol"]).reset_index(drop=True)

        # Identify feature columns (everything except identifiers & boolean status flags)
        meta_cols = {"timestamp", "symbol", "has_sufficient_history", "has_full_warmup"}
        feature_cols = [c for c in panel.columns if c not in meta_cols]

        # Optional cross-sectional normalization
        is_normalized = False
        if normalize and len(stock_dfs) > 1:
            panel = cross_sectional_zscore(panel, feature_cols=feature_cols, group_col="timestamp")
            is_normalized = True

        # Run quality validation
        val_result = FeatureValidator.validate_panel(
            panel,
            feature_cols=feature_cols,
            timestamp_col="timestamp",
            symbol_col="symbol",
            max_allowed_warmup_bars=self.config.full_warmup_bars,
        )

        return FeatureSet(
            data=panel,
            config=self.config,
            feature_columns=feature_cols,
            symbols=list(stock_dfs.keys()),
            validation_result=val_result,
            is_normalized=is_normalized,
        )

    def generate_panel_from_storage(
        self,
        storage: Any,
        symbols: Sequence[str],
        start_date: Optional[Union[str, pd.Timestamp]] = None,
        end_date: Optional[Union[str, pd.Timestamp]] = None,
        is_adjusted: bool = True,
        normalize: bool = False,
    ) -> FeatureSet:
        """
        Load market data from ParquetMarketDataStorage and extract features.

        Parameters:
            storage: ParquetMarketDataStorage instance.
            symbols: List of symbols to extract.
            start_date, end_date: Optional date boundaries.
            is_adjusted: True to read adjusted prices (recommended for returns/MAs).
            normalize: True to apply cross-sectional z-score per timestamp.
        """
        stock_dfs: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = storage.query_by_symbol(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                is_adjusted=is_adjusted,
            )
            if not df.empty:
                stock_dfs[sym] = df
            else:
                logger.warning(f"No stored market data found for symbol '{sym}'.")

        return self.generate_cross_sectional_panel(stock_dfs, normalize=normalize)
