# INDEX.md — map of the repository

Where everything lives, and the order to build it. Keep this file current: a new module gets a
line here in the same pull request.

## 1. Folders

| Path | What it holds | Committed |
|---|---|---|
| `v1/` | Frozen contract, report (only "pending" cells get filled) | yes |
| `docs/` | Event-card format, output formats, data notes | yes |
| `src/atr_breakout/` | The code (layout below) | yes |
| `synthetic/generate.py` | Seeded generator of fake 1-minute data with planted patterns | yes |
| `tests/` | pytest, synthetic data only | yes |
| `pyproject.toml` | Package metadata and pytest configuration | yes |
| `runs/` | Small run summaries: counts, metrics, checksums (no data) | yes |
| real data, cards, trade files | Outside the repository, path given at run time | **never** |

## 2. Code layout (`src/atr_breakout/`)

Each module does one job. Arrows show the only allowed direction of imports.

```
contract_v1.py        constants from the contract, each with its § (no logic)
data/                 one adapter per vendor -> one standard 1-minute frame
  schema.py           the standard frame: ts_utc, open, high, low, close, volume, symbol, filled
  alpaca_us.py        US stocks, regular hours only (§2)
  kite_nse.py         NSE stocks (§2)
  kraken.py           crypto spot, plus the completeness and gap-fill rules (§12 O5)
  ctrader_fx.py       FX and XAUUSD; tick volume dropped (§2, §3)
  windows.py          dev / OOS / holdout dates per market, and the holdout lock (§8)
  partitions.py       manifest-backed daily minute iterator
  crypto_gaps.py      isolated crypto minute fills across partition boundaries
  sessions.py         generate DEV/OOS cash session schedules
core/                 pure functions on one symbol's bars
  bars.py             1-minute -> 15-minute bars, sessions, overnight marks (§3)
  indicators.py       Wilder ATR(14), ATR % of price, ATR_Rank_30d, EMA, RSI (§3)
  signal.py           compression + breakout, long and short (§4)
  trade.py            entry, stop, gap rule, bar-5 rule, 20-bar exit, busy rule (§5)
  costs.py            base and stress cost per market, R net (§6)
study/                across symbols, per market
  benchmarks.py       random entry, breakout without compression, buy-and-hold (§9)
  stats.py            mean R, t with SE clustered by date, without-best-symbol (§10)
  passrule.py         Stage A, Stage B, the pass file that unlocks the holdout (§10)
cards/                event cards for the ML project (docs/event_cards.md)
  context.py          completed higher-timeframe bars from authorized minutes
  entry.py            entry snapshot fields
  outcome.py          CARD_PLAN and BOT_ACTUAL outcomes
  anonymise.py        instrument_key, day_key, cluster_id; private event map
  writer.py           parquet by day_key + manifest + sha256 sidecar
report/
  fill_report.py      fills v1/report.md "pending" cells from a run summary
archive.py            immutable bucket upload and byte verification
runner.py             connect permitted bars, simulations, and study metrics
cli.py                one command per step (see §4)
```

Data flow: `data` -> `core` -> `study` and `cards` -> `report`. `core` never imports `data`;
`cards` never imports `study`.

## 3. Build order (one pull request each, roughly)

1. `contract_v1.py`, `data/schema.py`, `synthetic/` generator, test scaffolding.
2. `core/bars.py`, `core/indicators.py` (+ tests against hand-computed values).
3. `core/signal.py` (+ tests: planted breakouts are found, near-misses are not).
4. `core/trade.py`, `core/costs.py` (+ one test per rule in §5 and §6).
5. `study/` (+ clustered-t test on a known case).
6. `data/windows.py` with the holdout lock (+ a test that holdout dates are refused).
7. `cards/` (+ tests that every field in docs/event_cards.md is present and anonymous).
8. Data adapters, one per vendor, each tested on a tiny synthetic file in that vendor's format.
9. `cli.py`, `report/fill_report.py`, and a full synthetic end-to-end run.

## 4. Commands

See the [v1 run plan](docs/run_plan.md) for the review sequence, input manifest,
and a synthetic dry run.

```
python -m synthetic.generate --out <dir>
atr-bo stage-a --data <manifest> --market US --out <run-dir>
atr-bo stage-b --data <manifest> --market US --out <run-dir>
atr-bo holdout --data <manifest> --market US --out <run-dir>
atr-bo sessions --market US --out <schedule>
atr-bo cards --data <manifest> --market US --out <private-dir> --schema <schema> --sessions <schedule>
```

## 5. Documents

- [AGENTS.md](AGENTS.md): rules for agents.
- [v1/contract.md](v1/contract.md): the frozen rules.
- [docs/event_cards.md](docs/event_cards.md): card fields and how each is computed here.
- [docs/outputs.md](docs/outputs.md): per-trade file and run summary columns.
- [REFERENCES.md](REFERENCES.md): research behind the idea.
