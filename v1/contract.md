# S1 — ATR-Compressed 20-Bar High/Low Breakout — Pre-registration

Status: **FROZEN** on 2026-11-05. Any change after freezing = new version (S1.1, …) with its own contract.

---

## 1. Hypothesis (Pass 1: bare signal, no filters)

After volatility compression, a close beyond the prior 20-bar extreme with a strong impulse
produces positive net R over the next 20 bars. Measured per spoke, never pooled.

Prediction, not assumed: positive post-breakout drift. Also measured: share of trades that
cross an overnight boundary on cash spokes.

## 2. Universe (spokes, reported separately)

| Spoke | Data | Period | Notes |
|---|---|---|---|
| US stocks (50) | Alpaca SIP 1-min, raw (unadjusted), regular hours via `in_session` | 2019-10-01 → 2026-09-30 | Selection by 2026 popularity, no written rule (§11). GOOG and GOOGL treated as one company. Late starters: PLTR 2020-09-30, COIN 2021-04-14, NU 2021-12-09 |
| NSE (233) | Kite, adjusted, real volume | 2015-01-01 → 2026-09-30 | Point-in-time membership not applied in Pass 1 |
| Crypto (Kraken spot, price proxy for perpetuals) | Kraken spot 1-min OHLCVT | first usable date → 2024-12-31 | Coins kept by the completeness rule in §12 O5. Candidates (BTC, ETH, SOL, …) are **not** assumed to pass |
| FX and gold | cTrader, tick-count volume (not used) | 2011-01-01 → 2026-09-30 | Major FX pairs and XAUUSD |

Excluded from crypto: BNB (first usable 2025-04-22) and HYPE (2026-01-28). No pre-2025 data.
Crypto 2025+ is reserved for H16 (H13 rule) and not used here.

## 3. Bars and indicators

- Bars: 15-minute, built from validated 1-minute data.
- **ATR(14): Wilder smoothing.**
- **ATR is expressed as a percentage of price** (`ATR_pct = ATR / Close`) for ranking, so splits
  do not create jumps (US data is not split-adjusted).
- **`ATR_Rank_30d[t]`:** percentile rank of `ATR_pct[t]` among the `ATR_pct` values of the last
  30 calendar days.
- The impulse filter `(Close − Open) >= 1.2 × ATR[t-1]` uses ATR in price units, as in §4.
- No volume, funding, spread or order-book inputs.

## 4. Signal (frozen text)

- **Compression (at t−1):** `ATR_Rank_30d[t-1] <= 20`
- **Breakout (at t):**
  - Long: `Close[t] > max(High[t-20 : t-1])` and `(Close[t] − Open[t]) >= 1.2 × ATR[t-1]`
  - Short: `Close[t] < min(Low[t-20 : t-1])` and `(Open[t] − Close[t]) >= 1.2 × ATR[t-1]`

## 5. Trade mechanics (frozen)

- **Position limit:** one open position **per symbol** at a time. A signal on a symbol that already
  has an open trade is skipped and counted as `skipped_busy`. Several symbols may hold positions
  at the same time.
- **Entry:** `Open[t+1]`.
- **Initial stop and 1R:**
  - Long: stop `Low[t]`, `1R = Open[t+1] − Low[t]`
  - Short: stop `High[t]`, `1R = High[t] − Open[t+1]`
- **Gap rule (cancel and count):** if `Open[t+1] <= Low[t]` (long) or `Open[t+1] >= High[t]`
  (short), cancel before entry, exclude from R, count as `skipped_gap`.
- **Bar-5 rule:** at `Close[t+5]`, if still open:
  - If `Close[t+5] <= Open[t+1]` (long) or `Close[t+5] >= Open[t+1]` (short): exit at `Close[t+5]`.
  - Otherwise: move stop to `Open[t+1] + Roundtrip_Cost` (long) or `Open[t+1] − Roundtrip_Cost`
    (short), where `Roundtrip_Cost = cost_bp × Open[t+1]` (§6).
- **Maximum hold:** exit any remaining position at `Close[t+20]`.
- **Stops:** checked intrabar; a hit exits at the stop level. Gap-through at the open is handled
  by the gap rule above.

## 6. Costs

Two measurement stages, run in this order:

- **Stage A (gross):** cost = 0. Gross R = (exit − entry) / 1R. In the bar-5 rule the stop moves to
  exactly `Open[t+1]` (breakeven). This stage tells whether a pre-cost edge exists at all.
- **Stage B (net):** cost = `cost_bp × Open[t+1]`, deducted as a round trip. Net R = (exit − entry) / 1R,
  minus cost / 1R. Base and stress cases.

Stage A results are written down before Stage B is computed.

| Spoke | Base (bp) | Stress (bp) | Basis |
|---|---|---|---|
| US stocks | 4.9 | +5 → 9.9 | Commission and slippage, `contracts/live_journal_costs_v1.json` (commit `38f2b23`) |
| NSE equities | 10.6 | +5 → 15.6 | Zerodha intraday formula (commit `0b2d4d3`) |
| Crypto (perpetuals model) | 12.0 | 23.0 | Base: 10 bp taker round trip + 2 bp baseline slippage. Stress: 10 bp taker + 13 bp live-measured slippage (12 trades) |
| FX majors | 1.5 | 3.0 | Cross-spoke cost card (FX 1.5 bp). Spread-based; see note |
| XAUUSD | 1.5 | 3.0 | Same table, uniform across the FX and gold spoke. Gold spreads may be wider; the stress case covers part of that |

Notes:
- **Source caveat:** the FX 1.5 bp figure comes from the cross-spoke cost card, which lists US at 2 bp. The journal config gives US 4.9 bp. The card is not fully reliable, so the table is pre-registered with both a base and a stress case.
- **Known mismatch:** crypto prices are spot; costs model perpetuals. Spot-to-perp basis is not modelled.
- **Base below measured slippage (crypto):** the 2 bp baseline is below the 13 bp measured on 12 trades. The base result is the optimistic case, the stress result the realistic one. Both are reported. The pass rule (§10) uses the base case.
- **Funding not modelled.** On the Prop account, ~3.3 bp/day. A 20-bar hold is about 5 hours, so the effect is roughly 0.7 bp per trade. Reported as a caveat.

## 7. Metrics reported (per spoke, dev and OOS)

Trade count; mean gross R; mean net R (base and stress); hit rate; average win R and average loss R;
`skipped_gap`; `skipped_busy`; share of trades crossing an overnight boundary (cash spokes);
result by year; result with the best single symbol removed; count of filled 1-minute bars (crypto).

## 8. Data split

| Spoke | Development | Out-of-sample | Holdout (run once) |
|---|---|---|---|
| US stocks | 2019-10-01 → 2021-12-31 | 2022-01-01 → 2022-12-31 | 2023-01-01 → 2026-09-30 |
| NSE | 2015-01-01 → 2020-12-31 | 2021-01-01 → 2022-12-31 | 2023-01-01 → 2026-09-30 |
| Crypto | first usable date → 2021-12-31 | 2022-01-01 → 2022-12-31 | 2023-01-01 → 2024-12-31 |
| FX and gold | 2011-01-01 → 2020-12-31 | 2021-01-01 → 2022-12-31 | 2023-01-01 → 2026-09-30 |

- Crypto dev starts at each coin's first usable date, fixed now. No later start is used.

## 9. Benchmarks (same spoke, same period)

1. **Random entry:** random bar per spoke, same direction mix, same 1R rule, same 20-bar hold,
   same costs. The signal must beat it.
2. **Signal without the compression filter** (breakout only). Shows what compression adds.
3. Buy-and-hold per spoke, for context only.

## 10. Pass rule (two stages, per spoke)

A strategy survives only if it passes **both** stages on development and OOS.

- **Stage A (gross):** rules 1–4 on gross R.
- **Stage B (net, base case):** rules 1–4 on net R.

Rules, applied on development **and** OOS:
1. Mean R > 0.
2. Mean R > random-entry benchmark (§9.1), computed on the same R definition.
3. Mean R still > 0 with the best symbol removed.
4. t ≥ 2 on dev + OOS combined, **with standard errors clustered by calendar date** (per spoke).
   Clustering is used because breakouts cluster on high-volatility days across symbols.
   Newey-West on a concatenated trade list is not used.

Holdout (run once, only if both stages pass): mean gross R > 0 and mean net R > 0.
The stress case is reported in Stage B and is not part of the pass rule.
If Stage A fails, Stage B is still computed and reported for completeness, but the strategy is
recorded as having no gross edge.

## 11. What kills it / known risks

- Fails 1–3 → no edge at these costs in this period. Reported as failed; no re-tuning under S1.
- Passes dev and OOS, fails holdout → "did not survive the holdout".
- **Parameter count:** 20, 30, 20, 1.2, 14, 5 and 20 bars are fixed here, chosen by reasoning, not
  by looking at data. Any later change is a new version.
- **Survivorship and look-ahead:** the US list was chosen for 2026 popularity; the crypto list omits
  coins that died. Positive results may be inflated. Reported as a caveat on every result.
- **Costs dominate:** the 3× cost-to-ATR constraint is **not** part of Pass 1. It is a Pass 2 filter
  if the bare test shows a gross edge.
- **Spot vs perpetual:** crypto historical data is spot; costs model perpetuals (§6).
- **Crypto sample size:** after the completeness rule, crypto may have 1–3 coins. Reported as
  low-power and not pooled.

## 12. Open items

**Resolved:**
- **O1 ATR:** Wilder smoothing.
- **O2 ATR rank:** 30 calendar days, ranked on ATR as a percentage of price.
- **O3 Costs:** §6 table (US 4.9, NSE 10.6, crypto 12 base / 23 stress, FX and XAUUSD 1.5 / 3.0).
- **O4 Dates:** §8 table.
- **O6 FX and gold:** included, uniform costs, no volume inputs.
- **O5 Missing minutes (crypto), the four rules:**
  1. **Completeness:** keep a coin only if at least 90% of its minutes are present in **every
     calendar year** of its dev and holdout windows, from its first usable date. A partial first year
     (e.g. SOL 2021) is checked over the span it has. Coins failing any year are dropped from the
     primary pass.
  2. **Gap fill:** fill isolated missing minutes in kept coins with a flat bar at the last close and
     zero volume, marked as filled. Count filled minutes per coin per year and report them.
  3. **Bar purity:** no entry if the 15-minute signal bar `t`, any 15-minute bar in `[t+1 : t+5]`, or
     more than two 15-minute bars in `[t-20 : t-1]` contain more than 3 filled 1-minute bars.
  4. **Reporting:** crypto reported as a separate, low-power result, not pooled with US and NSE.
- **Secondary row (declared now, not used for pass/fail):** crypto coins with dev from 2019-01-01,
  to show sensitivity to early data. Reported beside the primary row.

**Note on the crypto coin list:** earlier figures give BTC 97%, SOL 92%, ETH 90% as overall medians
only. Per-year figures for 2013–2016 (BTC, ETH) have not been checked. Whether BTC or ETH pass the
strict rule is decided by the data, not assumed here.
