# Local reproduction

## 1. Environment

Extract the archive and work from the directory containing README.md. Base entry points require Python 3.10+. The verified environment used Python 3.13, NumPy 2.4.4, pandas 3.0.2, and openpyxl 3.1.5.

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt` lists base dependency ranges. `requirements-tested.txt` records actual verified versions, without claiming coverage of all Python versions. Optional original-notebook dependencies are listed in `requirements-notebooks.txt`; base entry points need no SciPy, Matplotlib, Plotly, or Jupyter installation.

## 2. Input data

The supplied CSVs are located relative to the script's project directory, so no edits to the old notebook's working directory are required.

| Input | Required fields |
| :--- | :--- |
| Underlying CSV | `date,close` |
| Option CSV | `date,order_book_id,option_type,strike_price,close,expire_date` |

Dates must be `YYYY-MM-DD`, and option types must be `Call` or `Put`. Contract IDs are loaded by the original loader without an additional conversion.
Every option chain needs at least two expiries. Option prices can be zero; underlying and strike prices must be positive.
For external files, pass `--underlying /path/to/u.csv --options /path/to/o.csv`.

## 3. Run

```bash
python -m local.run --strategy cover_call --level 1 --output runs/cc
python -m local.run --strategy wheel --level 1 --output runs/wheel
python -m local.run --level -1 --start 2023-01-01 --end 2024-12-31 --output runs/itm
```

Use `python -m local.run --help` for all options.

## 4. Read outputs

Open your run's `report.html` directly in a browser. Reports use tables and do not generate additional unapproved images.

- `equity.csv`: daily engine equity plus presentation-only `normalized_equity` and `drawdown` fields.
- `trades.csv`: original-engine or adapter transaction records, labeled accordingly.
- `summary.json`: configuration, data kind, dependency versions, and input/source SHA-256 hashes.
- `run.log`: original strategy logs.
- `option_trades_raw.csv` and `underlying_trades_raw.csv`: the two separate original transaction logs. Their merged view cannot establish within-day cross-instrument order.

Terminal positions are retained, without an added forced liquidation. Select a fresh output directory for another run.

## 5. Verify retained sources and entry-point boundaries

```bash
python -m local.verify_originals
python -m unittest discover -s tests -v
```
