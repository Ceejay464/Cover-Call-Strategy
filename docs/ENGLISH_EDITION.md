# English edition

All reader-facing prose is translated, including the original research reports, source comments/docstrings/logs, notebook descriptions, and saved output labels. Programmatic data fields, contract markers, numerical settings, symbols, paths, and trading calculations are preserved. English display names do not rename the underlying market-data columns.

Exact original files are in `archive/originals/`. Their original language is retained solely as a historical and verification record. `python -m local.verify_originals` checks original hashes and translated executable structure. Source comparison excludes docstrings and reader-facing logging/formatting text; it preserves evaluated expressions, branch structure, and data-field references.

English-versus-original behavioral comparisons passed across 15 covered-call/rotation/synthetic-futures cases and both portfolio daily-adapter demos, matching equity and trades exactly. The portfolio comparisons also match saved strategy states and pending orders. Native vn.py backtests remain unverified because vn.py is not installed; daily-adapter results do not establish equivalence with native execution.
