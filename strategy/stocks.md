# Stock strategy

Version 1 · November 11, 2026

## Objective

Outperform SPY after simulated trading costs over a sustained forward period. Review drawdown, time invested, and turnover alongside returns. Evaluate ordinary allocation choices over weeks, with daily reviews for new evidence or a broken thesis.

## Decision process

- Start with the choice between cash and broad U.S. equity exposure. A modest initial allocation of roughly 10–20% to a broad fund is a reasonable candidate in a stable or improving market. Check the recent trend, breadth, and any near-term event that could materially change the trade. A broad-market allocation needs a coherent exposure thesis. An individual stock or a sector tilt needs a stronger case for taking concentrated risk.
- Research across broad, sector, and defensive exposures. Use the tracked SPY, RSP and IWM for breadth, XLE and XLV for contrasting sector exposures, and SGOV as a short-duration Treasury research reference. Treat it as a rate and risk reference until the engine explicitly accounts for distributions. Compare at least one plausible alternative to the lead candidate. Check recent dollar volume, fresh dated pricing and reliable data coverage before using an untracked ticker. Avoid OTC and thin names.
- If staying entirely in cash, give the concrete reason, one observable condition that would justify entering, and a point to revisit the call. Where prior-session closes are the expected input, assess whether they are current for that session. Consider price gaps as an execution risk.
- For a buy, give the planned size, thesis horizon, and what would invalidate it. For a sell, distinguish a broken thesis from ordinary price movement. Review positions and pending orders every run.

## Revision log

- Version 1: Introduce a broad-market starting point, a broader research list, and specific conditions for reconsidering cash. The first ten combined decisions were all HOLD.
