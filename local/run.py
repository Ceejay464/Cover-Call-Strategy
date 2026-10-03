"""Run the unchanged covered-call/wheel engine against the supplied CSVs."""
from pathlib import Path
import argparse
import sys
import numpy as np
import pandas as pd
from .common import (require_columns, positive_prices, daily_dates, prepare_output,
                     run_log, export_run)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "中证500备兑策略"


def run(args):
    sys.path.insert(0, str(SOURCE))
    from data.loader import load_underlying_data, load_option_data
    from option_builder.option_process import OptionDatabase
    from engine.engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from strategy.cover_call_strategy import CoverCallStrategy
    from strategy.option_wheel_strategy import OptionWheelStrategy
    from strategy.template_underlying_strategy import TemplateUnderlyingStrategy
    u_path = Path(args.underlying).expanduser().resolve()
    o_path = Path(args.options).expanduser().resolve()
    u, o = load_underlying_data(u_path), load_option_data(o_path)
    require_columns(u, ["date", "close"], "underlying")
    require_columns(o, ["date", "order_book_id", "option_type", "strike_price",
                        "close", "expire_date"], "options")
    # The original engine uses YYYY-MM-DD strings as chain lookup keys.
    for df, name in [(u, "underlying"), (o, "options")]:
        dates = daily_dates(df["date"])
        if not dates.dt.strftime("%Y-%m-%d").eq(df["date"]).all():
            raise ValueError(f"{name}: dates must be YYYY-MM-DD strings")
    daily_dates(o["expire_date"])
    positive_prices(u, ["close"], "underlying")
    positive_prices(o, ["strike_price"], "options")
    prices = pd.to_numeric(o["close"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices < 0).any():
        raise ValueError("Option close prices must be finite and nonnegative")
    if u.duplicated("date").any() or o.duplicated(["date", "order_book_id"]).any():
        raise ValueError("Duplicate underlying date or option date/contract")
    if not o["option_type"].isin(["Call", "Put"]).all():
        raise ValueError("option_type must be Call or Put")
    # The untouched original get_second_expiry_chain indexes the second expiry.
    relevant = o[(o["date"] >= args.start) & (o["date"] <= args.end)]
    if relevant.empty or u[(u["date"] >= args.start) & (u["date"] <= args.end)].empty:
        raise ValueError("No data in selected date range")
    if relevant.groupby("date")["expire_date"].nunique().min() < 2:
        raise ValueError("Original strategy requires at least two expiries in each chain")
    output = prepare_output(args.output)
    db = OptionDatabase(u, o)
    portfolio = Portfolio(cash=args.cash, multiplier=10000, option_cost=0.8,
                          etf_cost_rate=0.0001, etf_min_cost=0,
                          option_slippage=0.001, etf_slippage=0)
    option_strategy = (CoverCallStrategy(args.quantity, etf_quantity=args.quantity, level=args.level)
                       if args.strategy == "cover_call" else
                       OptionWheelStrategy(quantity=args.quantity, level=args.level))
    engine = BacktestEngine(db, option_strategy, TemplateUnderlyingStrategy(), portfolio)
    engine.prepare_timeline(args.start, args.end)
    with run_log(output):
        results = engine.run()
    positions = portfolio.get_positions()
    positions["options"] = {str(k): v for k, v in positions["options"].items()}
    # This original Portfolio stores separate option/underlying logs.
    # Keep both raw logs; the merged view cannot reconstruct within-day order.
    trades = sorted(portfolio.option_trade_history + portfolio.underlying_trade_history,
                    key=lambda row: pd.Timestamp(row["timestamp"]))
    pd.DataFrame(portfolio.option_trade_history).to_csv(
        output / "option_trades_raw.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(portfolio.underlying_trade_history).to_csv(
        output / "underlying_trades_raw.csv", index=False, encoding="utf-8-sig")
    export_run(ROOT, output, results, trades, args.cash, {
        "project": "Covered Call / CSI 500 ETF", "accent": "#b98b36",
        "data_kind": "Bundled CSV data (source/provenance not independently verified)",
        "demo": False, "engine": "Original custom BacktestEngine",
        "strategy": args.strategy, "parameters": vars(args),
        "costs": {"option_per_contract": 0.8, "etf_rate": 0.0001,
                  "option_slippage_fraction": 0.001, "etf_slippage_fraction": 0},
        "terminal_positions": positions,
        "trade_log_note": "Combined view of two original logs, date-sorted. "
                          "Do not infer same-day cross-instrument execution order from it.",
        "execution_note": "Original engine: same-day snapshot signals and immediate close-price "
                          "processing. Original exercise and roll behavior retained.",
    }, [u_path, o_path])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strategy", choices=["cover_call", "wheel"], default="cover_call")
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--quantity", type=int, default=1)
    p.add_argument("--cash", type=float, default=1_000_000)
    p.add_argument("--start", default="2022-10-01")
    p.add_argument("--end", default="2026-04-01")
    p.add_argument("--underlying", default=str(SOURCE / "500ETF/510500_underlying.csv"))
    p.add_argument("--options", default=str(SOURCE / "500ETF/510500_option_prices.csv"))
    p.add_argument("--output", default="runs/cover_call")
    args = p.parse_args()
    try:
        if not np.isfinite(args.cash) or args.cash <= 0 or args.quantity <= 0:
            raise ValueError("cash and quantity must be positive")
        if pd.Timestamp(args.start) > pd.Timestamp(args.end):
            raise ValueError("start must not be after end")
        run(args)
    except (ValueError, FileNotFoundError) as e:
        p.error(str(e))


if __name__ == "__main__":
    main()
