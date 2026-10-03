# Implementation notes and reproduction boundaries

These notes compare the supplied code with its original documentation. Important behavior is retained; discrepancies are documented rather than silently repaired.

- The original README references missing `requirements.txt` and `backtest_system.py` files. The added entry point is `python -m local.run`.
- The original portfolio-class ETF fee default is 0.0003; the notebook passes 0.0001. The local runner retains the notebook value.
- The original "negative Theta" wording is not used to explain the seller's time-decay exposure. The new overview describes the actual position structure and premium receipt; analytics functions remain unchanged.
- Default ETF exposure is 10,000 shares with residual cash. The original buy-and-hold benchmark also holds cash and is not an all-capital ETF benchmark.
- `get_second_expiry_chain` assumes at least two expiries. The new entry point checks the input rather than changing the original selection function.
- `level` shifts the strike index relative to the current ATM strike; it is not a fixed-Delta rule. Missing boundary contracts retain the original skip behavior.
- Exercise, expiry, cash, and fill behavior follow the supplied implementation. Data provenance and expiry accuracy were not independently verified.
- Option and underlying transactions are recorded in separate original logs. Both raw logs are exported; the merged date-sorted table cannot reconstruct cross-instrument order within the same day.
- The original closed-trade PnL calculation also uses the option multiplier for underlying trades. New summaries use daily equity instead.
