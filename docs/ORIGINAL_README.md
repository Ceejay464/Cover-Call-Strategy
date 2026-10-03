# CSI 500 Covered Call Backtest System

> English translation of the original README. Reported results and research statements below are retained from the original project. For the current runnable entry point and implementation details, use the top-level README.

## Project overview

A covered-call backtest system for the CSI 500 ETF, including a backtest framework, performance analysis, and exploration of possible strategy improvements. The stated research period runs from the second half of 2022 through the first half of 2026, evaluating return enhancement and risk controls in the domestic market.

## Project structure

The original README included this heading without a directory listing. The current project structure is described in the top-level README.

## Strategy logic

1. Buy 10,000 units of the CSI 500 ETF and sell the corresponding number of front-month Call contracts.
2. On each monthly option expiry date, check exercise. If S < K, the option expires worthless; retain the premium and sell the next month's Call. If S > K, assignment sells the underlying at the strike, realizing the strike-minus-entry-price difference plus premium. Buy the ETF again and sell the next month's Call.

### Sources of profit

| Perspective | Original explanation |
| --- | --- |
| Trades | Premium when unexercised; strike minus entry price plus premium when assigned |
| Greeks | A small residual positive Delta; the original text calls the sold Call exposure “negative Theta” and attributes profit to rapid front-month time-value decay |

### Sources of risk

- Short Gamma from sold Calls: large underlying moves can cause losses.
- Short Vega from sold Calls: a spike in implied volatility can cause losses.
- Limited liquidity in deeply OTM, near-expiry, or less actively traded contract months.

## Reported backtest results

| Parameter | Original stated value |
| --- | --- |
| Initial capital | CNY 1,000,000 |
| Option price | CNY 0.8 per contract |
| ETF commission | 0.03% |
| Option slippage | 0.1% |
| Period | Second half of 2022 to first half of 2026 |
| Frequency | Daily |

### One-strike OTM covered call versus a long-only position

| Strategy | Annualized return | Maximum drawdown |
| --- | --- | --- |
| Covered Call, one strike OTM | 0.82% | 3.33% |
| Long-only benchmark | 0.71% | 4.24% |

The original report concludes that return improved by about 0.11 percentage points annually and maximum drawdown narrowed by almost one percentage point, meeting the goal of enhancing return and smoothing the equity curve.

### Comparison across strike levels

| Strike level | Reported relative return | Explanation |
| --- | --- | --- |
| Deep OTM (OTM2 / OTM3) | Lower | Thin premiums provide limited protection |
| One strike OTM (OTM1) | Intermediate | Balance between return and protection |
| ATM | Better | Further return improvement |
| ITM | Highest | Larger premiums provide the greatest protection |

The original study reports progressively better results as the sold Call strike moves lower into the money. It attributes this to a larger intrinsic-value cushion and the lower Delta of ITM positions in a range-bound or mildly trending period.

This finding depends on the market regime: the original report favors OTM positions in a strong upward trend and ITM positions in range-bound or falling markets.

## Proposed improvements

### Dynamic strike selection

Choose OTM Calls when expecting a sustained rally, retaining upside participation. Choose ITM Calls when expecting sideways or declining prices, seeking more premium protection.

### Wheel strategy

Alternate between cash and ETF holdings: first sell cash-secured Puts to collect premiums while waiting to enter at a lower price; after acquiring the ETF, sell covered Calls for continued premium income.

| Strategy | Annualized return | Maximum drawdown |
| --- | --- | --- |
| Covered Call | 0.82% | 3.33% |
| Wheel | 0.76% | 3.57% |

The original study reports that the covered-call structure performed slightly better during its mild upward market, while describing the wheel as better suited to sideways or declining conditions.

## Live execution considerations from the original report

1. Prefer actively traded contract months and avoid deeply OTM or obscure contracts.
2. Account for liquidity discounts in execution.
3. Prepare for position adjustment when liquidity dries up under extreme conditions.
4. Adapt strike selection to the expected market regime rather than fixing one strike level.

## Original run instructions

```bash
# The original README specified Python 3.8+.
pip install -r requirements.txt
# Legacy command copied from the original README:
python backtest_system.py
```

The supplied archive does not contain `backtest_system.py`. The supported local entry point in this edition is `python -m local.run`; see the top-level README for exact steps. Research descriptions and implementation defaults can differ; see `docs/IMPLEMENTATION_NOTES.md`.
