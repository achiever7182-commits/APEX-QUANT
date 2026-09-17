"""
backtesting/benchmarks.py — Comparative baseline benchmark calculations.

Constructs Buy-and-Hold, Rebalanced Equal-Weight, and Cash benchmark equity curves.
Explicitly distinguishes synthetic empirical benchmarks from official index feeds.
"""
from __future__ import annotations

from typing import Dict, List, Optional
import pandas as pd
import numpy as np


class BenchmarkEngine:
    """
    Computes baseline benchmark equity curves over the exact backtest timeline.
    """

    BENCHMARK_DISCLAIMER = (
        "Synthetic benchmark constructed from available empirical dataset assets; "
        "NOT an official NIFTY 500 index feed."
    )

    @staticmethod
    def calculate_cash_benchmark(
        timestamps: List[pd.Timestamp],
        initial_capital: float = 1_000_000.0,
    ) -> pd.Series:
        """Returns constant initial capital representing an uninvested cash baseline."""
        return pd.Series(index=pd.to_datetime(timestamps), data=initial_capital, name="Cash_Benchmark")

    @staticmethod
    def calculate_buy_and_hold_benchmark(
        market_bars: Dict[str, pd.DataFrame],
        timestamps: List[pd.Timestamp],
        initial_capital: float = 1_000_000.0,
    ) -> pd.Series:
        """
        Equal-dollar buy-and-hold benchmark across available universe stocks.
        Purchased at t_0 and held with zero subsequent rebalancing.
        """
        if not market_bars or len(timestamps) == 0:
            return pd.Series(index=pd.to_datetime(timestamps), data=initial_capital, name="BuyAndHold_Benchmark")

        ts_list = sorted(list(timestamps))
        t0 = ts_list[0]
        symbols = sorted(market_bars.keys())
        n = len(symbols)
        if n == 0:
            return pd.Series(index=pd.to_datetime(ts_list), data=initial_capital, name="BuyAndHold_Benchmark")

        capital_per_stock = initial_capital / n

        # Initial prices at t0
        init_prices = {}
        for s in symbols:
            df = market_bars[s]
            df_slice = df[pd.to_datetime(df["timestamp"]) <= t0]
            if not df_slice.empty:
                init_prices[s] = float(df_slice.iloc[-1]["close"])
            else:
                init_prices[s] = float(df.iloc[0]["close"])

        shares = {s: (capital_per_stock / init_prices[s]) if init_prices[s] > 0 else 0.0 for s in symbols}

        equity_values = []
        for t in ts_list:
            t_val = 0.0
            for s in symbols:
                df = market_bars[s]
                match = df[pd.to_datetime(df["timestamp"]) <= t]
                if not match.empty:
                    px = float(match.iloc[-1]["close"])
                else:
                    px = init_prices[s]
                t_val += shares[s] * px
            equity_values.append(t_val)

        return pd.Series(index=pd.to_datetime(ts_list), data=equity_values, name="BuyAndHold_Benchmark")

    @staticmethod
    def calculate_equal_weight_rebalanced_benchmark(
        market_bars: Dict[str, pd.DataFrame],
        timestamps: List[pd.Timestamp],
        rebalance_dates: List[pd.Timestamp],
        initial_capital: float = 1_000_000.0,
    ) -> pd.Series:
        """
        Equal-weighted benchmark periodically rebalanced across universe stocks.
        """
        if not market_bars or len(timestamps) == 0:
            return pd.Series(index=pd.to_datetime(timestamps), data=initial_capital, name="EqualWeight_Benchmark")

        ts_list = sorted(list(timestamps))
        symbols = sorted(market_bars.keys())
        n = len(symbols)
        if n == 0:
            return pd.Series(index=pd.to_datetime(ts_list), data=initial_capital, name="EqualWeight_Benchmark")

        # Build price table
        price_table = pd.DataFrame(index=pd.to_datetime(ts_list), columns=symbols, dtype=float)
        for s in symbols:
            df = market_bars[s].copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            s_series = df.set_index("timestamp")["close"]
            vals = [s_series.asof(t) for t in price_table.index]
            price_table[s] = pd.Series(vals, index=price_table.index).bfill().ffill()

        # Compute daily asset returns
        asset_rets = price_table.pct_change().fillna(0.0)
        # Average return across assets
        eq_ret = asset_rets.mean(axis=1)

        # Compound equity curve
        cum_ret = (1.0 + eq_ret).cumprod()
        equity_series = initial_capital * cum_ret
        equity_series.name = "EqualWeight_Rebalanced_Benchmark"
        return equity_series
