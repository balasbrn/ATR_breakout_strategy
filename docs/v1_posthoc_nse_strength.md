# v1 post-hoc check: NSE results by breakout strength (2026-11-12)

**Post-hoc, not part of the v1 verdict.** This check was run after Stage A and Stage B had
failed and after the out-of-sample results had been seen. It does not change
[v1/report.md](../v1/report.md). Its only purpose was to decide whether a v2 contract on NSE was
worth writing. **It was not.** The 2023+ holdout was not read and stays unspent.

## Source

- Input: the private NSE run file `trades.parquet` (run `nse-v1`, code `1cd4dd5`, study manifest
  SHA-256 `f557f91f31bf80482d819722ae4b7a84465d173e1efe397aee1697d37591739f`). Strategy rows only
  (`benchmark` null, `status` TAKEN), windows dev (2015-01-09 → 2020-12-31) and OOS
  (2021-01-01 → 2022-12-30). 265,196 rows, no missing entry prices or `impulse_atr`.
- Read-only, ad hoc script on the VM; no new simulation, nothing written to the bucket.
- Groups: quintiles of `impulse_atr` (breakout bar body in ATR, ≥ 1.2 by the contract), cut points
  set on **dev gross stock trades only** (n = 58,363): 1.4581, 1.7897, 2.2580, 3.1266. The same cut
  points are applied to every window, case and to indices.
- Net R per group comes from each case's own rows (`r_net_base`, `r_net_stress`).
- Median 1R = `one_r_price` / entry price, in bp.
- 20 symbols are indices: INDIA_VIX, NIFTY_100, NIFTY_50, NIFTY_500, NIFTY_AUTO, NIFTY_BANK,
  NIFTY_ENERGY, NIFTY_FIN_SERVICE, NIFTY_FMCG, NIFTY_IT, NIFTY_METAL, NIFTY_MIDCAP_100,
  NIFTY_MID_SELECT, NIFTY_NEXT_50, NIFTY_PHARMA, NIFTY_PSU_BANK, NIFTY_PVT_BANK, NIFTY_REALTY,
  NIFTY_SMLCAP_100, SENSEX. The other 200 traded symbols are stocks.

## Decision rule, fixed before the results were seen

A v2 contract is worth writing only if all three hold, on **stocks only**:

1. The strongest group's mean stress net R is > 0 in dev **and** OOS.
2. Results rise from weakest to strongest: stress net R goes up on 4 of 4 steps in both windows.
3. The strongest group has at least 1,000 dev trades.

| Rule | Result | Values |
|---|---|---|
| 1 | **fail** | dev −0.143, OOS −0.135 |
| 2 | **fail** | dev 4 of 4 steps, OOS 3 of 4 |
| 3 | pass | 11,696 dev trades |
| **All three** | **fail** | NSE stays dropped; no v2 |

## Stocks (200 symbols)

| Window | Group | `impulse_atr` | Trades (gross) | Gross R | Base R | Stress R | Hit rate | Avg win / loss R | Median 1R (bp) | Share at exactly 0 R |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| dev | 1 | 1.20–1.46 | 11,673 | 0.0268 | −0.1875 | −0.2874 | 15.9% | 3.45 / −0.85 | 59.2 | 22.9% |
| dev | 2 | 1.46–1.79 | 11,672 | 0.0212 | −0.1508 | −0.2309 | 16.6% | 2.98 / −0.81 | 70.0 | 24.6% |
| dev | 3 | 1.79–2.26 | 11,673 | 0.0119 | −0.1312 | −0.1990 | 17.7% | 2.51 / −0.75 | 83.7 | 24.8% |
| dev | 4 | 2.26–3.13 | 11,672 | −0.0177 | −0.1335 | −0.1897 | 18.8% | 1.91 / −0.67 | 105.7 | 25.2% |
| dev | 5 | 3.13–555.5 | 11,673 | −0.0381 | −0.1093 | −0.1430 | 18.9% | 1.42 / −0.54 | 163.0 | 25.0% |
| OOS | 1 | 1.20–1.46 | 4,660 | 0.0627 | −0.1321 | −0.2277 | 16.9% | 3.27 / −0.84 | 58.5 | 24.7% |
| OOS | 2 | 1.46–1.79 | 4,323 | 0.0708 | −0.0866 | −0.1635 | 17.1% | 3.03 / −0.79 | 70.6 | 26.1% |
| OOS | 3 | 1.79–2.26 | 4,097 | 0.0531 | −0.0839 | −0.1491 | 18.0% | 2.55 / −0.73 | 86.9 | 26.0% |
| OOS | 4 | 2.26–3.13 | 4,266 | 0.0219 | −0.0810 | −0.1266 | 20.8% | 1.78 / −0.65 | 111.3 | 25.3% |
| OOS | 5 | 3.13–136.1 | 4,906 | −0.0446 | −0.1046 | −0.1348 | 19.0% | 1.15 / −0.47 | 177.5 | 24.9% |

## Indices (20 symbols)

| Window | Group | `impulse_atr` | Trades (gross) | Gross R | Base R | Stress R | Hit rate | Avg win / loss R | Median 1R (bp) | Share at exactly 0 R |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| dev | 1 | 1.20–1.46 | 1,421 | 0.4777 | 0.1208 | −0.0583 | 24.4% | 3.72 / −0.84 | 30.1 | 24.7% |
| dev | 2 | 1.46–1.79 | 1,201 | 0.3115 | −0.0229 | −0.1804 | 25.2% | 2.75 / −0.78 | 34.6 | 26.0% |
| dev | 3 | 1.79–2.26 | 961 | 0.2227 | −0.0297 | −0.1377 | 24.3% | 2.43 / −0.70 | 43.3 | 23.5% |
| dev | 4 | 2.26–3.13 | 974 | 0.2205 | 0.0286 | −0.0598 | 26.8% | 1.87 / −0.62 | 55.6 | 27.7% |
| dev | 5 | 3.13–26.6 | 716 | 0.1293 | 0.0087 | −0.0444 | 29.9% | 1.06 / −0.41 | 90.0 | 24.4% |
| OOS | 1 | 1.20–1.46 | 535 | 0.5371 | 0.2021 | −0.0174 | 24.9% | 3.95 / −0.84 | 30.5 | 21.9% |
| OOS | 2 | 1.46–1.79 | 476 | 0.2926 | −0.0754 | −0.2415 | 23.5% | 2.98 / −0.76 | 35.2 | 22.5% |
| OOS | 3 | 1.79–2.26 | 412 | 0.3658 | 0.1058 | 0.0284 | 28.6% | 2.47 / −0.74 | 43.6 | 25.5% |
| OOS | 4 | 2.26–3.12 | 394 | 0.2543 | 0.0743 | −0.0212 | 26.1% | 2.11 / −0.63 | 56.8 | 26.9% |
| OOS | 5 | 3.13–15.6 | 392 | 0.1261 | −0.0044 | −0.0486 | 24.2% | 1.27 / −0.42 | 91.9 | 31.9% |

## What it shows

1. **Stocks have no edge.** Gross R averages about 0.001 R in dev and *falls* as the breakout
   gets stronger. Net R improves with strength only because a bigger bar means a bigger 1R, so
   the same cost in bp is smaller in R. Every stock group loses after costs.
2. **The 20 indices carry almost all of NSE's gross result.** In dev they average about +0.30 R
   gross against about +0.001 R for stocks: roughly 97% of the NSE total gross R.
3. **This index result is not evidence.** It was found after looking, on 20 symbols, outside the
   rule above. INDIA_VIX is not tradable and its share of the result is unknown. Indices trade
   through futures, whose costs differ from the 10.6 bp stock formula used here, and index 1R is
   small (about 30 bp in group 1), so the result is very sensitive to cost.
4. About a quarter of trades end at exactly 0 R gross (the bar-5 stop to entry). In Stage B the
   moved stop is entry ± the round-trip cost (see [v1_decisions.md](v1_decisions.md) §2), so these
   exits land near zero net rather than paying the full cost.

The index observation is recorded here only. It is not a hypothesis and no code follows from it.
