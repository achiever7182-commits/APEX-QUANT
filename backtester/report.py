"""
backtester/report.py — Rich terminal report for backtest results.
"""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backtester.engine import BacktestResult
from backtester.metrics import Metrics


console = Console()


def _pct_color(value: float, good_above: float = 0.0) -> str:
    return "green" if value >= good_above else "red"


def print_report(result: BacktestResult, metrics: Metrics, data_source: str = "Binance Testnet") -> None:
    """Print a formatted backtest summary table to the terminal."""

    # Header
    header = Text(
        f"  BACKTEST REPORT  |  {result.strategy_name}  |  {result.symbol}  |  {result.timeframe}  |  {data_source}  ",
        style="bold white on dark_blue",
    )
    console.print()
    console.print(header)
    console.print()

    # Main metrics table
    table = Table(box=box.ROUNDED, border_style="bright_blue", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bright_black", min_width=28)
    table.add_column("Value", justify="right", min_width=20)
    table.add_column("Rating", justify="center", min_width=12)

    def row(label: str, value: str, rating: str = "", rating_style: str = "white") -> None:
        table.add_row(label, value, Text(rating, style=rating_style))

    row("Data Source",         data_source, "REAL" if "REAL" in data_source.upper() else "TESTNET", "bold green" if "REAL" in data_source.upper() else "yellow")
    row("Starting Balance",    f"${result.starting_balance:,.2f}")
    row("Final Balance",       f"${result.final_balance:,.2f}")


    pct = metrics.total_return_pct
    row("Total Return",
        f"{pct:+.2f}%",
        "PROFIT" if pct > 0 else "LOSS",
        _pct_color(pct))

    row("Total P&L",           f"${metrics.total_pnl:+,.2f}")
    row("Total Fees Paid",     f"${metrics.total_fees:,.4f}", "HIGH" if metrics.total_fees > 50 else "OK", "yellow" if metrics.total_fees > 50 else "green")


    table.add_section()

    row("Candles Processed",   f"{metrics.candle_count:,}")
    row("Total Trades",        f"{metrics.trade_count}")
    row("Wins / Losses",       f"{metrics.win_count} / {metrics.loss_count}")

    wr = metrics.win_rate_pct
    row("Win Rate",
        f"{wr:.1f}%",
        "GOOD" if wr >= 50 else "LOW",
        "green" if wr >= 50 else "red")

    row("Avg Win",             f"${metrics.avg_win:+,.4f}")
    row("Avg Loss",            f"${metrics.avg_loss:+,.4f}")
    row("Expectancy / Trade",  f"${metrics.expectancy:+,.4f}")

    table.add_section()

    pf = metrics.profit_factor
    row("Profit Factor",
        f"{pf:.4f}" if pf != float("inf") else "inf",
        "GOOD" if pf >= 1.5 else ("OK" if pf >= 1.0 else "POOR"),
        "green" if pf >= 1.5 else ("yellow" if pf >= 1.0 else "red"))

    sr = metrics.sharpe_ratio
    row("Sharpe Ratio",
        f"{sr:.4f}",
        "GREAT" if sr >= 2.0 else ("GOOD" if sr >= 1.0 else ("WEAK" if sr >= 0 else "BAD")),
        "green" if sr >= 1.0 else ("yellow" if sr >= 0 else "red"))

    dd = metrics.max_drawdown_pct
    row("Max Drawdown",
        f"{dd:.2f}%",
        "LOW" if dd < 10 else ("MED" if dd < 25 else "HIGH"),
        "green" if dd < 10 else ("yellow" if dd < 25 else "red"))

    cagr = metrics.cagr_pct
    row("CAGR (annualised)",
        f"{cagr:+.2f}%",
        "GOOD" if cagr > 20 else ("OK" if cagr > 0 else "BAD"),
        "green" if cagr > 0 else "red")

    console.print(table)

    # Quick verdict
    if metrics.sharpe_ratio >= 1.0 and metrics.profit_factor >= 1.2 and metrics.max_drawdown_pct < 25:
        verdict = Panel("[bold green]VERDICT: Strategy shows a viable edge. Worth testing live on testnet.[/]",
                        border_style="green")
    elif metrics.total_return_pct > 0:
        verdict = Panel("[bold yellow]VERDICT: Marginally profitable but risk-adjusted metrics are weak. Needs tuning.[/]",
                        border_style="yellow")
    else:
        verdict = Panel("[bold red]VERDICT: Strategy loses money over this period. Do NOT run live.[/]",
                        border_style="red")
    console.print(verdict)
    console.print()
