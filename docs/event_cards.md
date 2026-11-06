# Event cards from the historical run

Every v1 signal becomes one event card in the **`event_card_v2`** format used by the live
Trade555 cards, so a separate ML project can read historical and live cards the same way.
The cards are written to a private folder given at run time and are **never committed**.
Field names follow Trade555's schema (`schemas/event_card_v2.json`, sha256
`bdf76c7b21a55e057f2344a6e330659807c4059889a148f9efd1b1d641d8f7b3`, Trade555 commit `f4fe9a2`).
Publishing the field names is approved by the owner; definitions below are this repo's own.

## 1. Which signals get a card

Every signal that passes contract §4, in every market, in the **development and out-of-sample**
windows only:

| Case | `action` | `action_reason` | BOT_ACTUAL track |
|---|---|---|---|
| Traded | TAKEN | SIGNAL_ACCEPTED | the v1 trade (§5) |
| Skipped, symbol busy | BLOCKED | SKIPPED_BUSY | null |
| Skipped, gap at entry | BLOCKED | SKIPPED_GAP | null |

Holdout-window cards are not written in this run (holdout lock, AGENTS.md rule 3). Crypto 2025+
is never read.

## 2. Anonymity

No symbol, no calendar date, no price level, no currency amount on any card.

- `instrument_key`: a stable random id per symbol, e.g. `inst_` + 12 hex characters. The mapping
  is written only to a private `event_map.parquet` beside the cards, never to the cards.
- `day_key`: consecutive day number per market, starting at 1 on the first day of data. The
  calendar date lives only in `event_map`.
- `cluster_id`: same signal minute + same `asset_class`.
- `event_id`: random, unique.

## 3. Entry fields

All distances are in ATR(14) of that timeframe; `close` is the signal bar's close.

| Field | Value here |
|---|---|
| `card_version` | `event_card_v2` |
| `asset_class` | US `STOCK_US`; NSE `STOCK_IN`; crypto `CRYPTO_PERP` (spot used as a price proxy); FX `FX`; XAUUSD `COMMODITY_CFD` |
| `direction`, `timeframe` | LONG / SHORT; `15m` |
| `trigger` | `{"name": "atr_breakout_v1", "values": {"atr_rank_prev": …, "impulse_atr": …}}` |
| `atr_pct`, `atr_rank_30d` | as contract §3 (ATR % of price; rank 0–100 over 30 calendar days) |
| `cost_rt_pct_of_atr`, `cost_source_expected` | base cost (§6) ÷ 1 ATR × 100; `MODELLED_FIXED` |
| `plan` | `{"stop_atr": 1, "target_atr": 2, "max_bars": 20}` |
| `ema9_dist`, `ema50_dist`, `ema200_dist`, `ema_order` | (close − EMA) / ATR on 15m; order such as `9>50>200` |
| `h1_*`, `h4_*` | the same on 1h and 4h bars closed at signal time |
| `d_*` | the same from the **previous completed daily close**, in daily ATR(14) |
| `vwap_dist`, `vwap_method` | stocks: (close − session VWAP) / ATR, `SESSION`; crypto: `ROLLING_24H`; FX and gold: null |
| `range20_pos` | position of close in the last 20 bars' high–low range, 0–100 |
| `rsi14` | RSI(14) |
| `last4_moves` | close-to-close of the last 4 bars in ATR, **oldest first** (JSON list) |
| `vol_rel20` | bar volume / 20-bar average; FX and gold: null (tick volume is not used) |
| `liquidity_bucket` | LOW / MID / HIGH tercile of 20-day average traded value within the market; FX and gold: null |
| `funding_rate`, `oi_change_pct_1h`, `oi_change_pct_24h` | null (no history) |
| `event_flags` | null |
| `utc_time`, `session_phase`, `weekday` | HH:MM; OPEN / MID / LATE for cash markets, ASIA / EUROPE / US for 24-hour markets; MON–SUN |
| `mkt_ema50_dist` | index close vs its EMA50 in its own ATR (SPY, NIFTY 50, BTC) if the index data is available, else null |
| `spread_bp`, `spread_atr`, `spread_source` | null |
| `missing` | list of every null field with its reason |

## 4. Outcome tracks

| Track | Rule |
|---|---|
| `CARD_PLAN` | the live cards' ruler: entry at the signal bar's close, stop 1 ATR, target 2 ATR, 20 bars, stop wins a same-bar tie; cash markets exit at the session close (`SESSION_CLOSE`). Gross R and net R at the base cost. |
| `BOT_ACTUAL` | the v1 trade exactly as contract §5 (entry `Open[t+1]`, stop at the signal bar, bar-5 rule, 20-bar exit), gross and net R at the base cost. Null when the signal was skipped. |

Outcome table fields as in the schema: `status` (COMPLETE), `action`, `action_reason`,
`cost_model_version` (`atr_bo_v1_base`), `label_end_day_key`, `target_after_stop`,
`failure_type` may be left null. Exit rows carry `exit_track`, `exit_reason`, `bars_held`,
`move_since_entry_atr`.

## 5. Delivery format

Same as the live deliveries, so the ML project's loader reads both: parquet partitions
`entry/`, `exit/`, `outcome/` by `day_key`, one `manifest.json` (partitions with row counts and
sha256, `synthetic: false`, `card_version`, code commit) and a `manifest.json.sha256` sidecar.
Synthetic runs set `synthetic: true`.

## 6. Historical export and live compatibility

The writer takes a local copy of the pinned Trade555 schema and verifies its SHA-256.
The run directory contains a `public/` delivery and a sibling `event_map.parquet`.
Share only the public directory. It contains the three partitioned tables, the manifest,
and its checksum. The cards CLI builds higher-timeframe context from the same
authorized minutes. Benchmark and liquidity context remain optional caller
inputs. Missing context is marked explicitly on the card.

The historical signal uses the frozen calendar-day ATR rank. The exported ATR percentage
is multiplied by 100 for the live card's percentage unit. EMA uses Trade555's SMA seed
and partial warmup. RSI uses the same Wilder calculation and flat-series convention.

Public action reasons use the pinned schema's vocabulary. Busy maps to
`SYMBOL_ALREADY_OPEN` and entry gap to `ORDER_UNFILLED`. Study boundary and crypto
purity skips appear only in the private event map with their original statuses.
The private map also keeps the bot's gross and net 1R values. The public bot cost
fields use the schema's basis-point and ATR units. For blocked signals the
schema requires a bot outcome object, with its trade values null.

The [Trade555 range and move definitions](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/features.py#L371-L384)
use a 0–100 range position and the four oldest-first close differences divided by
the snapshot's ATR. The [continuous session function](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/features.py#L437-L441)
assigns crypto and FX to ASIA, EUROPE, or US using the snapshot's UTC time, with
transitions at 08:00 and 16:00.

## 7. Higher-timeframe context

Generate the US and NSE session schedule with `atr-bo sessions`. It follows the
Trade555 audit using XNYS for US and XBOM for NSE. NSE special sessions such as
Muhurat trading and budget Saturdays are absent from XBOM, so they receive no
H1, H4, or daily context. [Trade555 calendar audit](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/data_audit/checks.py#L19-L34)

Cash H1 and H4 start at the session
open and omit incomplete groups and session-end stubs. The daily bar ends at the
actual session close. [Trade555 session aggregation and minute coverage](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/preparation.py#L94-L147)

Crypto and FX use fixed UTC buckets. Crypto emits only buckets with all minute
rows. FX aggregates available minutes in closed buckets. The historical reader
uses the authorized archive and leaves gaps where a live crypto provider
fallback would have supplied data. [Trade555 UTC aggregation](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/sources.py#L414-L452), [Trade555 crypto archive coverage](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/sources.py#L685-L709)

H1 and H4 include a bar ending exactly at the snapshot time. Daily also requires
its end date to be strictly earlier in the live session timezone. FX daily
bars are cut at UTC midnight, while the prior-day rule uses New York midnight. Distances divide by
the selected timeframe's Wilder ATR. [Trade555 closed-bar cutoff](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/features.py#L80-L96), [Trade555 daily selection](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/features.py#L343-L351), [Trade555 session timezones](https://github.com/balasbrn/Trade555/blob/f4fe9a253dedadb297ea8be6522eba6d1bd6a62c/src/trade555/event_cards/host_config.py#L28-L30)
