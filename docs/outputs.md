# Run outputs

What a run writes, besides the event cards ([event_cards.md](event_cards.md)). Real outputs go
to a folder outside the repository; only the small summaries in `runs/` are committed.

## 1. Per-trade file (`trades.parquet`, private)

One row per signal, including skipped ones. The Monte Carlo project reads this file and nothing
else, so its columns are fixed here.

| Column | Meaning |
|---|---|
| `trade_id` | unique id |
| `market` | US, NSE, CRYPTO, FXGOLD |
| `symbol` | real symbol (private file only) |
| `window` | DEV or OOS |
| `signal_ts_utc`, `entry_ts_utc`, `exit_ts_utc` | times; entry/exit null when skipped |
| `direction` | LONG / SHORT |
| `status` | TAKEN, SKIPPED_BUSY, SKIPPED_GAP |
| `exit_reason` | STOP, BAR5_EXIT, BREAKEVEN_STOP, MAX_HOLD |
| `one_r_price` | 1R in price units |
| `r_gross` | gross R (Stage A) |
| `r_net_base`, `r_net_stress` | net R at base and stress cost (Stage B) |
| `crosses_overnight` | cash markets: trade spans a session close |
| `atr_rank_prev`, `impulse_atr` | the signal's own values |
| `benchmark` | null for the strategy; `RANDOM` or `NO_COMPRESSION` for benchmark rows |
| `seed` | random-entry seed, else null |

## 2. Run summary (`runs/<run_id>/summary.json`, committed)

Per market and window: trade count, mean gross R, mean net R (base, stress), hit rate, average
win and loss R, skipped counts, overnight share, mean R without the best symbol, benchmark means,
t (clustered by date), and the pass verdict per stage. Plus: contract version, code commit,
command, sha256 of every input file and of `trades.parquet`.

## 3. Stage files

`stage_a.json` is written and hashed before Stage B starts. `pass.json` is written only by the
pass rule; the holdout lock reads it.
