"""Causal, scale-free snapshots for historical event cards."""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from atr_breakout.core.bars import BAR_SIZE, CASH_SESSIONS
from atr_breakout.core.costs import round_trip_cost
from atr_breakout.core.indicators import EMA_PERIODS

CARD_VERSION = "event_card_v2"
PLAN = {"stop_atr": 1, "target_atr": 2, "max_bars": 20}
MARKET_CLASS = {"US": "STOCK_US", "NSE": "STOCK_IN", "CRYPTO": "CRYPTO_PERP", "FX_GOLD": "FX"}


@dataclass(frozen=True)
class CardContext:
    """Optional annotated context with explicit UTC bar ends.

    Higher timeframe and benchmark frames carry atr and ema columns from
    add_indicators. Liquidity buckets are keyed by completed session date.
    """

    higher: dict[str, pd.DataFrame] = field(default_factory=dict)
    benchmark: pd.DataFrame | None = None
    liquidity: dict[date, str] = field(default_factory=dict)


def _ema_fields(row, close: float, prefix: str = "") -> dict:
    atr = row["atr"] if row is not None else None
    emas = {p: row[f"ema{p}"] for p in EMA_PERIODS} if row is not None else {}
    fields = {
        f"{prefix}ema{period}_dist": (
            float((close - emas[period]) / atr)
            if pd.notna(atr) and atr > 0 and pd.notna(emas[period]) else None
        )
        for period in EMA_PERIODS
    }
    fields[f"{prefix}ema_order"] = (
        ">".join(str(period) for _, period in sorted(
            ((value, period) for period, value in emas.items()), reverse=True
        ))
        if emas and all(pd.notna(value) for value in emas.values()) else None
    )
    return fields


def _last_completed(frame, cutoff, prior_date=None):
    if frame is None:
        return None
    eligible = frame.loc[frame["bar_end"].le(cutoff)]
    if prior_date is not None:
        eligible = eligible.loc[eligible["trading_date"].lt(prior_date)]
    return eligible.iloc[-1] if not eligible.empty else None


def _phase(market, opened, at):
    if market not in CASH_SESSIONS:
        # Trade555 event_cards/features.py:437–441 at f4fe9a2 uses UTC signal time.
        return ("ASIA", "EUROPE", "US")[at.hour // 8]
    zone, opening, closing = CASH_SESSIONS[market]
    local = opened.tz_convert(zone)
    minute = local.hour * 60 + local.minute
    return "OPEN" if minute - opening < 60 else "LATE" if closing - minute <= 60 else "MID"


def snapshot(
    bars: pd.DataFrame, index: int, market: str, context: CardContext,
    *, cost_bp: float,
) -> dict:
    """Return feature fields known at the indexed bar's close."""
    bar = bars.iloc[index]
    atr = float(bar.atr)
    close = float(bar.close)
    at = bar.ts_utc + BAR_SIZE
    past = bars.iloc[max(0, index - 96):index + 1]
    volume = bar.volume
    local_window = past.iloc[-20:]
    low, high = local_window["low"].min(), local_window["high"].max()
    previous_volume = past["volume"].iloc[-21:-1]
    vol_mean = previous_volume.mean() if len(previous_volume) == 20 and previous_volume.notna().all() else 0

    values = {
        "atr_pct": float(bar.atr_pct * 100) if pd.notna(bar.atr_pct) else None,
        "atr_rank_30d": float(bar.atr_rank_30d) if pd.notna(bar.atr_rank_30d) else None,
        "cost_rt_pct_of_atr": 100 * round_trip_cost(close, cost_bp) / atr if atr > 0 else None,
        "cost_source_expected": "MODELLED_FIXED",
        "rsi14": float(bar.rsi14) if pd.notna(bar.rsi14) else None,
        # Trade555 event_cards/features.py:371–379 at f4fe9a2 uses percent.
        "range20_pos": float(100 * (close - low) / (high - low)) if len(local_window) == 20 and high > low else None,
        # Trade555 event_cards/features.py:380–384 at f4fe9a2 uses snapshot ATR.
        "last4_moves": (past["close"].iloc[-5:].diff().iloc[1:] / atr).tolist() if len(past) >= 5 and atr > 0 else None,
        "vol_rel20": float(volume / vol_mean) if market != "FX_GOLD" and pd.notna(volume) and vol_mean > 0 else None,
        "liquidity_bucket": context.liquidity.get(bar.trading_date) if market != "FX_GOLD" else None,
        "funding_rate": None,
        "oi_change_pct_1h": None,
        "oi_change_pct_24h": None,
        "event_flags": None,
        "utc_time": at.strftime("%H:%M"),
        "session_phase": _phase(market, bar.ts_utc, at),
        "weekday": at.strftime("%a").upper(),
        "spread_bp": None,
        "spread_atr": None,
        "spread_source": None,
    }
    values.update(_ema_fields(bar, close))
    for prefix in ("h1", "h4", "d"):
        prior_date = bar.trading_date if prefix == "d" else None
        completed = _last_completed(context.higher.get(prefix), at, prior_date)
        values.update(_ema_fields(completed, close, prefix + "_"))

    benchmark = _last_completed(context.benchmark, at)
    values["mkt_ema50_dist"] = (
        _ema_fields(benchmark, float(benchmark.close))["ema50_dist"]
        if benchmark is not None and at - benchmark.bar_end <= pd.Timedelta(minutes=30) else None
    )

    values["vwap_dist"] = values["vwap_method"] = None
    if market in CASH_SESSIONS:
        vwap_bars = past.loc[past["trading_date"].eq(bar.trading_date)]
        zone, opening, _ = CASH_SESSIONS[market]
        first = vwap_bars["ts_utc"].iloc[0].tz_convert(zone)
        complete = first.hour * 60 + first.minute == opening
        method = "SESSION"
    elif market == "CRYPTO":
        vwap_bars = past.loc[past["ts_utc"].ge(at - pd.Timedelta(hours=24))]
        complete = len(vwap_bars) == 96
        method = "ROLLING_24H"
    else:
        vwap_bars = past.iloc[:0]
        complete = False
        method = None
    if (
        complete and atr > 0
        and vwap_bars["ts_utc"].diff().iloc[1:].eq(BAR_SIZE).all()
        and vwap_bars["missing_minutes"].eq(0).all()
        and vwap_bars["volume"].notna().all()
        and vwap_bars["volume"].sum() > 0
    ):
        typical = vwap_bars[["high", "low", "close"]].mean(axis=1)
        vwap = (typical * vwap_bars["volume"]).sum() / vwap_bars["volume"].sum()
        values["vwap_dist"] = float((close - vwap) / atr)
        values["vwap_method"] = method
    values["missing"] = {key: "unavailable_or_insufficient_history" for key, value in values.items() if value is None}
    return values
