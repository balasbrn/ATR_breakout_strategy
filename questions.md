# v1 implementation handoff

The synthetic smoke test covers continuous 15-minute bars, Wilder ATR, compression and breakout
signals, and the trade simulator. The market data and research results are still pending.
Please record decisions below before the real-data runner uses them.

1. **ATR rank (§3).** The smoke test uses a full 30 calendar days of history and the percentage
   of observations less than or equal to the current value, including the current value. Is
   that the intended warmup and tie convention?
2. **Trade mechanics (§5–6).** The smoke test allows a signal at the close of an exit bar,
   activates a moved stop on the next bar, fills an existing stop at its level on a
   gap-through, and signs R by direction. Please confirm those interpretations, especially
   the existing-position gap treatment and the unsigned formula in §6.
3. **Random benchmark (§9).** How should random entries be drawn across symbols and dates?
   Please specify the seed and number of draws, whether to match trade or signal counts, and
   whether to apply bar-5, busy, gap and crypto purity rules to the benchmark.
4. **Data and partition boundaries (§2, §8, §12).** Where are the canonical symbol manifests
   and validated data schemas? Which session timezone defines the bars and clustered dates,
   which timestamp assigns a trade to a split, and how should trades at the split boundary
   be handled? What is the maximum length of an isolated crypto gap, and should OOS years
   enter the annual completeness screen?
5. **Reporting (§7, §9–10).** Please confirm whether to identify the best symbol by mean R or
   total R, and how to weight the spoke's buy-and-hold benchmark.
