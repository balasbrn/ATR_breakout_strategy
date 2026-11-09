# v1 implementation decisions (answers to `questions.md`)

These fix how the code reads the frozen contract where its text leaves room. They do **not**
change any rule, parameter, cost or date in `v1/contract.md`, and they are fixed **before** any
real data is run. Status: **PROPOSED** by Claude; the owner confirms by merging. Items marked
**OWNER** are genuine choices.

## 1. ATR rank (§3)

Yes, as implemented:
- Window: the `ATR_pct` values of 15-minute bars in `(t − 30 calendar days, t]`, current bar included.
- Rank = 100 × (number of values ≤ `ATR_pct[t]`) / (number of values in the window).
- Warm-up: no rank, and so no signal, until a symbol has a full 30 calendar days of 15-minute bars
  (and ATR(14) is defined). For crypto, the 30 days start at the coin's first usable date.

## 2. Trade mechanics (§5–6)

- **Signal on an exit bar:** allowed. A position closed at a bar's close (bar-5 exit, max hold) or
  stopped inside that bar is no longer open at that bar's close, so a signal there is not busy.
- **Moved stop:** set at `Close[t+5]`, active from bar `t+6`.
- **Sign of R:** `R = direction × (exit − entry) / 1R`, with direction +1 long, −1 short. Cost is
  always subtracted: `R_net = R_gross − cost / 1R`.
- **Two paths:** Stage A and Stage B are separate simulations, because the bar-5 stop differs
  (Stage A: exactly `Open[t+1]`; Stage B: `Open[t+1] ± Roundtrip_Cost`). They can exit differently.
- **Gap-through of an open position's stop (OWNER):** the contract says "a hit exits at the stop
  level", so the primary result fills at the stop level, as written. Because that is optimistic
  when a later bar opens beyond the stop (overnight on cash markets), the report also counts these
  exits and shows their R if filled at that bar's open. That diagnostic is not part of the pass rule.

## 3. Random-entry benchmark (§9.1)

Contract: random bar per market, same direction mix, same 1R rule, same 20-bar hold, same costs.
- **Draw:** per market and window, uniform over eligible (symbol, 15-minute bar) pairs. Eligible =
  rank and ATR defined, the full 20-bar window inside the same window's data, crypto purity passed.
- **Count:** as many entries as the strategy's TAKEN trades in that market and window.
- **Direction:** drawn to match the strategy's long/short share in that market and window.
- **Rules applied:** entry `Open[t+1]`, stop at the bar's low/high (1R), gap rule (a gapped draw is
  replaced and counted), bar-5 rule, 20-bar max hold, same costs, crypto purity. The busy rule is
  **not** applied: draws are independent.
- **Repeats (OWNER):** 100 draws, seeds 1 to 100. The pass rule compares the strategy's mean R with
  the **average of the 100 draw means**; the report also shows their 5th–95th percentile.
  (This only stabilises the benchmark; the separate Monte Carlo project is unaffected.)

## 4. Data and boundaries (§2, §8, §12)

- **Data source and schemas:** Trade555 validated v1.1 stores one `bars.parquet` and
  `audit.json` per symbol. The converter reads the runtime GCS prefix and writes
  the canonical minute schema in `data/schema.py`.
- **Usable minutes (OWNER):** Treat Trade555 `usable=false` minutes as missing.
  Each symbol's eligible history starts on its audit's `usable_from` date.
- **Bars:** built in UTC, aligned to :00, :15, :30, :45.
  - US: regular hours 09:30–16:00 America/New_York.
  - NSE: 09:15–15:30 Asia/Kolkata.
  - Crypto: 24 hours, UTC.
  - FX and gold: as traded, UTC; the weekend close is a session break.
- **Clustering date (§10 rule 4):** the exchange's local trading date for US and NSE; the UTC date
  for crypto, FX and gold.
- **Split assignment:** by the signal bar `t`, using the clustering date.
- **Boundary trades:** a trade may run from development into out-of-sample and stays in the window
  of its signal. A signal whose trade window (`t+1 … t+20`) would need any bar in the **holdout**
  window, or crypto 2025+, is not taken and is counted as `skipped_boundary`. This keeps the
  holdout lock intact.
- **Isolated crypto gap:** a run of at most 3 consecutive missing minutes is filled (flat bar at
  the last close, zero volume, marked filled). Longer runs are left missing; a 15-minute bar that
  contains one is built from the minutes present and is normally excluded by the bar-purity rule.
- **Completeness screen years (OWNER):** the contract names the development and holdout years, as
  written. The screen counts minutes only and reads no prices. The out-of-sample years are also
  reported, but do not drop a coin.

## 5. Reporting (§7, §9–10)

- **Best symbol:** the symbol with the largest **total** R in that market and window (largest
  contribution to the result), removed for rule 3.
- **Buy-and-hold (context only):** equal-weighted mean of each symbol's percentage return over the
  window, from the first to the last available close. Reported in percent, not R.
