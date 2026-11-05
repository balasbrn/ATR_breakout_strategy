# ATR_breakout_strategy v1 — Results

**Status: PENDING.** No result has been computed. Every "pending" cell is filled once, by the run
that implements [contract.md](contract.md). The designed version of this report is
[report.html](report.html).

## Provenance

| Item | Value |
|---|---|
| Contract | `v1/contract.md`, frozen 2026-11-05, commit: pending |
| Code | repository and commit: pending |
| Script and command | pending |
| Data checksums | per market: pending (data itself is not in this repository) |
| Run date (UTC) | pending |
| Costs | §6 of the contract: base and stress, per market |

## 1. Stage A — gross (no costs)

Written down before Stage B is computed.

| Rule | US dev | US OOS | NSE dev | NSE OOS | Crypto dev | Crypto OOS | FX/gold dev | FX/gold OOS |
|---|---|---|---|---|---|---|---|---|
| 1 · Mean R > 0 | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 · Mean R > random entry | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 · Mean R > 0 without best symbol | pending | pending | pending | pending | pending | pending | pending | pending |
| 4 · t ≥ 2 (dev + OOS, clustered by date) | pending | | pending | | pending | | pending | |
| **Verdict** | pending | | pending | | pending | | pending | |

## 2. Stage B — net (base costs; stress reported)

| Rule | US dev | US OOS | NSE dev | NSE OOS | Crypto dev | Crypto OOS | FX/gold dev | FX/gold OOS |
|---|---|---|---|---|---|---|---|---|
| 1 · Mean R > 0 | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 · Mean R > random entry | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 · Mean R > 0 without best symbol | pending | pending | pending | pending | pending | pending | pending | pending |
| 4 · t ≥ 2 (dev + OOS, clustered by date) | pending | | pending | | pending | | pending | |
| **Verdict** | pending | | pending | | pending | | pending | |

## 3. Metrics per market

One table per market (US stocks, NSE, crypto, FX and gold), columns development, out-of-sample and
holdout (holdout stays **locked** unless both stages pass):

| Metric | Development | Out-of-sample | Holdout |
|---|---|---|---|
| Trades | pending | pending | locked |
| Mean gross R | pending | pending | locked |
| Mean net R, base | pending | pending | locked |
| Mean net R, stress | pending | pending | locked |
| Hit rate | pending | pending | locked |
| Average win R / average loss R | pending | pending | locked |
| `skipped_gap` / `skipped_busy` | pending | pending | locked |
| Share crossing overnight (cash markets) | pending | pending | locked |
| Mean R without best symbol | pending | pending | locked |
| Random entry, mean R | pending | pending | locked |
| Breakout without compression, mean R | pending | pending | locked |
| Buy-and-hold (context only) | pending | pending | locked |
| Filled 1-min bars (crypto only) | pending | pending | locked |

Also reported: mean R by calendar year per market, and for crypto a secondary row with development
from 2019-01-01 (not used for pass/fail).

## 4. Caveats carried on every result

- US list chosen by 2026 popularity; crypto list omits coins that died (survivorship).
- NSE point-in-time index membership not applied.
- Crypto prices are spot; costs model perpetuals; basis and funding not modelled.
- Crypto may keep only 1–3 coins after the completeness rule: low power, never pooled.
- t ≥ 2 is a first bar, not proof (see REFERENCES.md, Harvey, Liu and Zhu 2016).

## 5. Verdict

pending
