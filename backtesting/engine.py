"""
backtesting/engine.py — Event-driven historical simulation engine for APEX-QUANT.

Simulates the entire APEX-QUANT equity pipeline sequentially through time:
Point-in-Time Data -> Step 6 Ranking -> Step 7 Portfolio Construction ->
Execution Simulation -> Double-Entry Accounting -> Quantitative Diagnostics.
"""
from __future__ import annotations

from typing import Dict, List, Optional
import pandas as pd

from backtesting.config import BacktestConfig
from backtesting.data_feed import PointInTimeDataFeed
from backtesting.timeline import BacktestTimeline
from backtesting.signal_runner import SignalRunner
from backtesting.portfolio_runner import PortfolioRunner
from backtesting.execution_simulator import ExecutionSimulator
from backtesting.accounting import PortfolioAccounting
from backtesting.benchmarks import BenchmarkEngine
from backtesting.performance import PerformanceAnalyzer
from backtesting.walk_forward import WalkForwardAnalyzer, WalkForwardMLTrainer
from backtesting.models import BacktestResult, PortfolioSnapshot, SimulatedFill
from data.corporate_actions.loader import CorporateActionsLoader
from data.corporate_actions.models import CorporateAction


class BacktestEngine:
    """
    Master coordinator for historical portfolio simulation.
    """

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        data_feed: Optional[PointInTimeDataFeed] = None,
        signal_runner: Optional[SignalRunner] = None,
        portfolio_runner: Optional[PortfolioRunner] = None,
    ) -> None:
        self.config = config or BacktestConfig()
        self.data_feed = data_feed
        self.signal_runner = signal_runner or SignalRunner(config=self.config.ranking_config)
        self.portfolio_runner = portfolio_runner or PortfolioRunner(config=self.config.portfolio_config)

    def run(
        self,
        candidate_panel: pd.DataFrame,
        market_bars: Optional[Dict[str, pd.DataFrame]] = None,
        allocation_method: Optional[str] = None,
        corporate_actions: Optional[Dict[str, List[CorporateAction]]] = None,
    ) -> BacktestResult:
        """
        Execute full historical backtest simulation with zero look-ahead bias.

        Parameters:
            candidate_panel: Pre-computed cross-sectional panel containing features,
                             market data across symbols and timestamps.
            market_bars: Map of symbol -> historical bar DataFrame. If None, extracts
                         from self.data_feed.
            allocation_method: Override allocation method ('constrained', 'equal_weight',
                               'score_weighted', 'inverse_volatility').
            corporate_actions: Optional mapping of symbol -> CorporateActions list.
                               If None, attempts loading from local cache.

        Returns:
            Strongly typed BacktestResult.
        """
        method = allocation_method or self.config.default_allocation_method

        if market_bars is not None:
            self.data_feed = PointInTimeDataFeed(market_bars)
        elif self.data_feed is None:
            raise ValueError("BacktestEngine requires market_bars or an initialized PointInTimeDataFeed.")

        # 1. Initialize Timeline
        all_dates = self.data_feed.get_all_trading_dates()
        timeline = BacktestTimeline(
            trading_dates=all_dates,
            rebalance_frequency=self.config.rebalance_frequency,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            warmup_bars=self.config.warmup_bars,
        )

        # 2. Initialize Accounting Ledger and Simulator
        accounting = PortfolioAccounting(initial_capital=self.config.initial_capital)
        simulator = ExecutionSimulator(
            execution_convention=self.config.execution_convention,
            transaction_cost_bps=self.config.transaction_cost_bps,
            slippage_bps=self.config.slippage_bps,
            liquidity_participation_limit=self.config.liquidity_participation_limit,
        )

        snapshots: List[PortfolioSnapshot] = []
        all_fills: List[SimulatedFill] = []
        rebalances: List[Dict] = []

        # Extract sector lookup if available
        sector_lookup = {}
        if "sector" in candidate_panel.columns:
            for _, row in candidate_panel.drop_duplicates(subset=["symbol"]).iterrows():
                if pd.notna(row.get("sector")):
                    sector_lookup[row["symbol"]] = row["sector"]

        # 3. Load Point-in-Time Corporate Actions
        actions_by_date: Dict[Any, List[CorporateAction]] = {}
        if corporate_actions is not None:
            for act_list in corporate_actions.values():
                for act in act_list:
                    d = act.ex_date_obj
                    actions_by_date.setdefault(d, []).append(act)
        else:
            loader = CorporateActionsLoader()
            for sym in self.data_feed.symbols:
                for act in loader.load_actions(sym):
                    d = act.ex_date_obj
                    actions_by_date.setdefault(d, []).append(act)

        # 4. Initialize Walk-Forward ML Trainer if configured
        wf_trainer = None
        if self.config.use_walk_forward_ml:
            wf_trainer = WalkForwardMLTrainer(
                model_type=self.config.ml_model_type,
                target_horizon=self.config.ml_target_horizon,
                min_train_samples=self.config.ml_min_train_samples,
            )

        pending_rebalance: Optional[Dict] = None

        # 5. Main Historical Simulation Loop
        for t in timeline:
            # 5a. Apply point-in-time corporate actions on ex-date
            t_date = t.date()
            if t_date in actions_by_date:
                accounting.apply_corporate_actions(actions_by_date[t_date])

            # Current close prices at timestamp t
            current_prices = {}
            for sym in self.data_feed.symbols:
                bar = self.data_feed.get_current_bar(sym, t)
                if bar is not None and pd.notna(bar["close"]):
                    current_prices[sym] = float(bar["close"])

            # 5b. Execute any pending rebalance orders scheduled for open of t (T+1 open)
            turnover_fraction = 0.0
            rebalanced_this_bar = False

            if pending_rebalance is not None:
                total_eq_before = accounting.cash + sum(
                    p.shares * current_prices.get(p.symbol, p.current_price)
                    for p in accounting.positions.values()
                )
                fills, updated_cash = simulator.simulate_rebalance(
                    signal_timestamp=pending_rebalance["signal_timestamp"],
                    target_result=pending_rebalance["target_result"],
                    current_holdings=accounting.positions,
                    current_cash=accounting.cash,
                    data_feed=self.data_feed,
                    total_equity=total_eq_before,
                    max_single_stock_weight=self.config.max_single_stock_weight,
                    max_sector_weight=self.config.max_sector_weight,
                    sector_lookup=sector_lookup,
                )
                accounting.apply_fills(fills)
                all_fills.extend(fills)
                turnover_fraction = pending_rebalance["target_result"].diagnostics.turnover
                rebalanced_this_bar = True

                rebalances.append({
                    "timestamp": pending_rebalance["signal_timestamp"],
                    "execution_timestamp": t,
                    "target_result": pending_rebalance["target_result"],
                    "fills_count": len(fills),
                    "allocation_method": pending_rebalance["target_result"].allocation_method,
                    "fallback_reason": pending_rebalance["target_result"].fallback_reason,
                })
                pending_rebalance = None

            # 5c. Check if t triggers a rebalance signal at market close
            is_rebal_date = timeline.is_rebalance_date(t)
            if is_rebal_date:
                # Signal Generation (using point-in-time walk-forward ML if enabled)
                if wf_trainer is not None:
                    # Dynamically train on strictly historical data <= t and predict cross-section at t
                    pit_slice = wf_trainer.train_and_predict(
                        candidate_panel=candidate_panel,
                        as_of_time=t,
                    )
                    ranked_uni = self.signal_runner.generate_ranking(
                        candidate_panel=pit_slice,
                        as_of_time=t,
                    )
                else:
                    ranked_uni = self.signal_runner.generate_ranking(
                        candidate_panel=candidate_panel,
                        as_of_time=t,
                    )

                # Portfolio Construction at close of t
                bars_hist = self.data_feed.get_bars_up_to(t)
                current_total_equity = accounting.cash + sum(
                    p.shares * current_prices.get(p.symbol, p.current_price)
                    for p in accounting.positions.values()
                )
                target_result = self.portfolio_runner.build_target_portfolio(
                    ranked_universe=ranked_uni,
                    market_bars_history=bars_hist,
                    total_capital=current_total_equity,
                    current_holdings=accounting.positions,
                    method=method,
                )

                # Execution scheduling based on convention
                if self.config.execution_convention in ("next_open", "next_close"):
                    # Stage orders to execute on next session
                    pending_rebalance = {
                        "signal_timestamp": t,
                        "target_result": target_result,
                    }
                else:
                    # 'close_t': Immediate execution on current close bar
                    fills, updated_cash = simulator.simulate_rebalance(
                        signal_timestamp=t,
                        target_result=target_result,
                        current_holdings=accounting.positions,
                        current_cash=accounting.cash,
                        data_feed=self.data_feed,
                        total_equity=current_total_equity,
                        max_single_stock_weight=self.config.max_single_stock_weight,
                        max_sector_weight=self.config.max_sector_weight,
                        sector_lookup=sector_lookup,
                    )
                    accounting.apply_fills(fills)
                    all_fills.extend(fills)
                    turnover_fraction = target_result.diagnostics.turnover
                    rebalanced_this_bar = True

                    rebalances.append({
                        "timestamp": t,
                        "execution_timestamp": t,
                        "target_result": target_result,
                        "fills_count": len(fills),
                        "allocation_method": target_result.allocation_method,
                        "fallback_reason": target_result.fallback_reason,
                    })

            # 5d. Mark to Market at Close of Bar t
            snapshot = accounting.mark_to_market(
                timestamp=t,
                current_prices=current_prices,
                sector_map=sector_lookup,
                is_rebalance_bar=rebalanced_this_bar,
                rebalance_turnover=turnover_fraction,
            )
            snapshots.append(snapshot)

        # 6. Performance & Metrics Analysis
        metrics = PerformanceAnalyzer.evaluate_performance(
            snapshots=snapshots,
            fills=all_fills,
            initial_capital=self.config.initial_capital,
            risk_free_rate=self.config.risk_free_rate,
            cagr_convention=self.config.cagr_convention,
        )

        equity_df = PerformanceAnalyzer.build_equity_curve_dataframe(snapshots)

        # 7. Baseline Benchmark Equity Curves
        sim_timestamps = [s.timestamp for s in snapshots]
        bench_bars = {
            s: self.data_feed.get_bars_up_to(sim_timestamps[-1])[s]
            for s in self.data_feed.symbols
            if s in self.data_feed.get_bars_up_to(sim_timestamps[-1])
        } if sim_timestamps else {}

        benchmarks = {
            "Cash": BenchmarkEngine.calculate_cash_benchmark(sim_timestamps, self.config.initial_capital),
            "BuyAndHold": BenchmarkEngine.calculate_buy_and_hold_benchmark(bench_bars, sim_timestamps, self.config.initial_capital),
            "EqualWeightRebalanced": BenchmarkEngine.calculate_equal_weight_rebalanced_benchmark(
                bench_bars, sim_timestamps, timeline.rebalance_dates, self.config.initial_capital
            ),
        }

        # 8. Walk-Forward Period Analysis
        wf_periods = WalkForwardAnalyzer.partition_snapshots_by_period(snapshots, period_freq="QE")

        return BacktestResult(
            config=self.config,
            equity_curve=equity_df,
            snapshots=snapshots,
            fills=all_fills,
            rebalances=rebalances,
            metrics=metrics,
            benchmark_curves=benchmarks,
            walk_forward_periods=wf_periods,
            walk_forward_audit_logs=wf_trainer.audit_logs if wf_trainer is not None else [],
        )

