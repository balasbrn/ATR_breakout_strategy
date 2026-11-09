# Run outputs

What a run writes, besides the event cards ([event_cards.md](event_cards.md)). Real outputs go
to a folder outside the repository; only the small summaries in `runs/` are committed.

## 1. Per-trade file (`trades.parquet`, private)

One row per signal and simulated cost case, including skipped signals and
benchmark attempts. The local file is cumulative. Stage A publishes gross
rows, Stage B adds base and stress rows, and holdout adds gross and base rows
for the reserved window. The Monte Carlo project uses the anonymised export below.

| Column | Meaning |
|---|---|
| `trade_id` | unique id |
| `market` | US, NSE, CRYPTO, FXGOLD |
| `symbol` | real symbol (private file only) |
| `window` | `dev`, `oos`, or `holdout`, assigned from the signal bar |
| `case` | `gross`, `base`, or `stress` |
| `signal_ts_utc`, `entry_ts_utc`, `exit_ts_utc` | Signal bar close, entry bar open, and exit bar close. Entry and exit are null when skipped |
| `direction` | LONG / SHORT |
| `status` | TAKEN, SKIPPED_BUSY, SKIPPED_GAP, SKIPPED_BOUNDARY, or SKIPPED_PURITY |
| `exit_reason` | STOP, BAR5_EXIT, BREAKEVEN_STOP, MAX_HOLD |
| `one_r_price` | 1R in price units |
| `r_gross` | Gross R on taken gross-case rows |
| `r_net_base`, `r_net_stress` | Net R on taken rows of the corresponding cost case |
| `crosses_overnight` | cash markets: trade spans a session close |
| `atr_rank_prev`, `impulse_atr` | the signal's own values |
| `benchmark` | null for the strategy; `RANDOM` or `NO_COMPRESSION` for benchmark rows |
| `seed` | random-entry seed, else null |

Each taken row populates one return column. Skipped rows leave entry, exit,
risk, and return fields null. Stop exits use the timestamp of the bar that
observed the fill. Strategy metrics reconcile against rows with a null
`benchmark`. Random rows preserve the seed and every draw, including repeated
selections and rejected entry gaps. Buy-and-hold has no signal rows.

The CLI writes the local artifact with owner-only permissions. Metrics JSON
records the SHA-256 of the snapshot for that phase. With `--archive`, the file
is verified under `trades/<phase>/trades.parquet` within the run archive so
immutable uploads can coexist. Restore the latest applicable snapshot as
`trades.parquet` in the run directory before resuming.

## 2. Run summary (`runs/<run_id>/summary.json`, committed)

Per market and window: trade count, mean gross R, mean net R (base, stress), hit rate, average
win and loss R, skipped counts, overnight share, mean R without the best symbol, benchmark means,
t (clustered by date), and the pass verdict per stage. Plus: contract version, code commit,
command, sha256 of every input file and of `trades.parquet`.

## 3. Stage files

`stage_a.json` is written and hashed before Stage B starts. `pass.json` is written only by the
pass rule; the holdout lock reads it.

## 4. Anonymised Monte Carlo input

Run `atr-bo export-anon --run <run-dir> --out <new-file.parquet>` on the
DEV/OOS trade snapshot. The output contains only `market`, `window`, `case`,
`benchmark`, `seed`, `status`, `day_index`, and `r`. The export rejects an
input containing any holdout row, including a skipped row.

`day_index` is zero-based and dense within each market, in chronological order
over the trading dates represented in the input. All cases and benchmarks use
the same index for a market's trading day. The index uses the signal bar's open
and the market trading timezone. `r` is the selected case's return for taken
rows and null for skipped rows.
