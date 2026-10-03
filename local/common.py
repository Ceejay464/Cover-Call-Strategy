"""Local I/O and presentation helpers. No strategy calculations live here."""
from contextlib import contextmanager, redirect_stdout
from hashlib import sha256
from html import escape
from pathlib import Path
import json
import platform
import numpy as np
import pandas as pd


def require_columns(df, columns, label):
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"{label}: missing columns {sorted(missing)}")
    if df.empty:
        raise ValueError(f"{label}: input is empty")


def positive_prices(df, columns, label):
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="raise")
        values = df[col].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"{label}: {col} must contain finite positive prices")


def daily_dates(values):
    dates = pd.to_datetime(values, errors="raise")
    if dates.dt.tz is not None:
        raise ValueError("Use timezone-naive daily dates; no implicit timezone conversion")
    if (dates != dates.dt.normalize()).any():
        raise ValueError("Use daily YYYY-MM-DD dates, without intraday timestamps")
    return dates


def load_table(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Data file not found: {path}")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path), path
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path), path
    raise ValueError("Supported data formats: .csv and .xlsx")


def load_panel(path):
    df, path = load_table(path)
    require_columns(df, ["date", "symbol", "open", "high", "low", "close"], "prices")
    df["date"] = daily_dates(df["date"])
    if df["symbol"].isna().any() or df["symbol"].astype(str).str.strip().eq("").any():
        raise ValueError("symbol cannot be blank")
    df["symbol"] = df["symbol"].astype(str)
    positive_prices(df, ["open", "high", "low", "close"], "prices")
    if df.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate date/symbol rows")
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
            (df["low"] > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC range")
    symbols = sorted(df["symbol"].unique())
    counts = df.groupby("date")["symbol"].nunique()
    if not counts.eq(len(symbols)).all():
        raise ValueError("Each daily slice must contain all symbols; no forward fill is applied")
    return df.sort_values(["date", "symbol"]).reset_index(drop=True), path


def select_dates(df, start, end):
    lo = pd.Timestamp(start) if start else df["date"].min()
    hi = pd.Timestamp(end) if end else df["date"].max()
    if lo > hi:
        raise ValueError("start must not be after end")
    result = df[(df["date"] >= lo) & (df["date"] <= hi)].copy()
    if result.empty:
        raise ValueError("No data in selected date range")
    return result


def source_hashes(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.py"))
            if not set(p.relative_to(root).parts) & {"local", "tests", ".venv", "runs", "archive"}}


def prepare_output(path):
    path = Path(path).expanduser().resolve()
    # Preserve earlier runs instead of silently overwriting research outputs.
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"Output directory is not empty: {path}. Choose another --output")
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def run_log(output):
    with (Path(output) / "run.log").open("w", encoding="utf-8") as f:
        with redirect_stdout(f):
            yield


def export_run(root, output, equity, trades, capital, metadata, inputs=(), extra=None):
    if equity.empty or not {"timestamp", "equity"}.issubset(equity.columns):
        raise ValueError("Engine returned no usable daily equity records; see run.log")
    equity = equity.copy()
    equity["timestamp"] = pd.to_datetime(equity["timestamp"])
    if equity["timestamp"].duplicated().any():
        raise ValueError("Duplicate daily records in engine results")
    values = equity["equity"].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Non-finite equity values")
    # Presentation-only fields. No mutation of engine/strategy objects.
    peaks = np.maximum.accumulate(np.r_[float(capital), values])[1:]
    equity["normalized_equity"] = values / float(capital)
    equity["drawdown"] = np.where(peaks > 0, values / peaks - 1, np.nan)
    equity.to_csv(output / "equity.csv", index=False, encoding="utf-8-sig")
    trade_frame = pd.DataFrame(trades)
    if not len(trade_frame):
        trade_frame = pd.DataFrame(columns=["timestamp", "instrument", "quantity", "price"])
    trade_frame.to_csv(output / "trades.csv", index=False, encoding="utf-8-sig")
    metadata = dict(metadata)
    metadata.update({
        "initial_capital": float(capital),
        "observed_start": str(equity["timestamp"].iloc[0].date()),
        "observed_end": str(equity["timestamp"].iloc[-1].date()),
        "daily_records": len(equity), "trade_records": len(trades),
        "final_equity": float(values[-1]),
        "total_return_from_initial_capital": float(values[-1] / capital - 1),
        "max_drawdown_including_initial_capital": float(equity["drawdown"].min()),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__, "pandas_version": pd.__version__,
        "original_source_sha256": source_hashes(root),
        "inputs_sha256": {str(Path(p).resolve()): sha256(Path(p).read_bytes()).hexdigest()
                          for p in inputs},
        "terminal_positions": metadata.get("terminal_positions", {}),
        "presentation_metrics_note": "Summary uses initial capital and recorded daily equity. "
                                     "No annualized returns or original notebook statistics replaced.",
    })
    if extra:
        metadata.update(extra)
    (output / "summary.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str, allow_nan=False),
        encoding="utf-8")
    title = escape(str(metadata["project"]))
    accent = metadata.get("accent", "#146c94")
    rows = [
        ("Data provenance", metadata["data_kind"]),
        ("Engine", metadata["engine"]),
        ("Observed dates", f'{metadata["observed_start"]} → {metadata["observed_end"]}'),
        ("Daily records", str(len(equity))),
        ("Initial capital", f"{capital:,.2f}"),
        ("Final equity", f"{values[-1]:,.2f}"),
        ("Total return", f'{metadata["total_return_from_initial_capital"]:.2%}'),
        ("Maximum drawdown", f'{metadata["max_drawdown_including_initial_capital"]:.2%}'),
        ("Trade records", str(len(trades))),
    ]
    table = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in rows)
    demo_note = ("<p class='notice'>SYNTHETIC DEMO DATA — "
                 "Runtime verification only; not historical investment performance.</p>" if metadata.get("demo") else
                 "<p class='notice'>Data supplied with the project or by the user. Market-data provenance and adjustment conventions were not independently verified.</p>")
    # A table-only report deliberately avoids adding unapproved charts.
    report = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{background:#f7f8fa;color:#18232f;font:16px/1.65 system-ui,sans-serif;margin:0}}
main{{max-width:960px;margin:48px auto;padding:32px;background:white;border-radius:18px}}
.eyebrow{{color:{accent};letter-spacing:.15em;font-size:12px;font-weight:700}}
h1{{font-size:32px;margin:8px 0}}.notice{{padding:16px;border-left:4px solid {accent};background:#f3f6fa}}
table{{border-collapse:collapse;width:100%;margin:24px 0}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #e5eaf0}}
th{{width:46%;font-weight:500;color:#506171}}a{{color:{accent}}}code{{overflow-wrap:anywhere}}
@media(max-width:700px){{main{{margin:12px;padding:20px}}h1{{font-size:25px}}}}</style>
<main><div class="eyebrow">LOCAL RESEARCH RUN</div><h1>{title}</h1>{demo_note}<table>{table}</table>
<p>{escape(str(metadata.get("execution_note", "")))}</p>
<p>Terminal positions follow the original engine behavior, without added forced liquidation. Summary metrics start from initial capital and include it in peak equity; 
only observed daily records are summarized. Original notebook annual-return and Sharpe calculations are not replaced.</p>
<p><a href="equity.csv">Daily equity</a> · <a href="trades.csv">Transactions</a> ·
<a href="summary.json">Parameters and data hashes</a> · <a href="run.log">Run log</a></p></main></html>"""
    (output / "report.html").write_text(report, encoding="utf-8")
    print(f"Completed: {output}")
    print(f"Data: {metadata['data_kind']} | Engine: {metadata['engine']}")
    print(f"Daily records: {len(equity)} | Trade records: {len(trades)}")
    print("Open report.html for the table-only report; see summary.json for provenance.")
