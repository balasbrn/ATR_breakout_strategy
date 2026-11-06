"""Derive card context from the same authorized canonical minutes."""

import pandas as pd

from atr_breakout.core.bars import CASH_SESSIONS
from atr_breakout.core.indicators import add_indicators

WIDTHS = {"h1": pd.Timedelta(hours=1), "h4": pd.Timedelta(hours=4), "d": pd.Timedelta(days=1)}
MINUTE = pd.Timedelta(minutes=1)
QUARTER_HOUR = 15 * MINUTE


def _cash_schedule(sessions, zone):
    if not sessions:
        raise ValueError("Cash cards require an authoritative session schedule")
    opens = [pd.Timestamp(session["open"]) for session in sessions]
    closes = [pd.Timestamp(session["close"]) for session in sessions]
    if any(pd.isna(stamp) or stamp.tzinfo is None for stamp in (*opens, *closes)):
        raise ValueError("Session open and close must be timezone-aware")
    schedule = pd.DataFrame({
        "session_open": pd.to_datetime(opens, utc=True),
        "session_close": pd.to_datetime(closes, utc=True),
    })
    start, end = schedule["session_open"], schedule["session_close"]
    schedule["trading_date"] = start.dt.tz_convert(zone).dt.date
    if (
        schedule["trading_date"].duplicated().any()
        or not end.dt.tz_convert(zone).dt.date.eq(schedule["trading_date"]).all()
        or not start.eq(start.dt.floor(QUARTER_HOUR)).all()
        or not end.eq(end.dt.floor(QUARTER_HOUR)).all()
        or not start.lt(end).all()
    ):
        raise ValueError("Expected one positive, quarter-hour-aligned session per local date")
    return schedule


def higher_timeframes(minutes: pd.DataFrame, market: str, *, sessions=None) -> dict[str, dict[str, pd.DataFrame]]:
    """Return indicator-enriched h1/h4/d frames keyed by symbol, then prefix."""
    cutoff = minutes["ts_utc"].max() + MINUTE
    cash = market in CASH_SESSIONS
    if cash:
        zone = CASH_SESSIONS[market][0]
        trading_date = minutes["ts_utc"].dt.tz_convert(zone).dt.date
        source = minutes.assign(trading_date=trading_date).merge(
            _cash_schedule(sessions, zone), on="trading_date", how="inner", sort=False,
        )
        source = source.loc[
            source["ts_utc"].ge(source["session_open"]) & source["ts_utc"].lt(source["session_close"])
        ]
    else:
        source = minutes

    contexts = {}
    for prefix, width in WIDTHS.items():
        stamp = source["ts_utc"]
        if cash:
            # Trade555 preparation.py:41–50,94–104,135–147 at f4fe9a2.
            opening, closing = source["session_open"], source["session_close"]
            start = opening if prefix == "d" else opening + (stamp - opening).dt.floor(width)
            end = closing if prefix == "d" else start + width
            eligible = end.le(closing) & end.le(cutoff)
        else:
            # Trade555 sources.py:414–452 (IG) and :685–709 (Kraken archive).
            start = stamp.dt.floor(width)
            end = start + width
            eligible = end.le(cutoff)

        grouped = source.loc[eligible].groupby(
            ["symbol", start.loc[eligible].rename("bar_start"), end.loc[eligible].rename("bar_end")],
            sort=False, observed=True,
        )
        bars = grouped.agg(
            open=("open", "first"), high=("high", "max"),
            low=("low", "min"), close=("close", "last"),
            minute_count=("close", "size"), volume_count=("volume", "count"),
        )
        bars["volume"] = grouped["volume"].sum(min_count=1).where(bars["volume_count"].eq(bars["minute_count"]))
        bars = bars.reset_index().rename(columns={"bar_start": "ts_utc"})
        if cash or market == "CRYPTO":
            complete = bars["minute_count"].eq((bars["bar_end"] - bars["ts_utc"]) // MINUTE)
            bars = bars.loc[complete]
        if market == "FX_GOLD":
            bars["volume"] = float("nan")
        for symbol, frame in bars.groupby("symbol", sort=False):
            ordered = frame.sort_values("ts_utc").reset_index(drop=True)
            contexts.setdefault(symbol, {})[prefix] = add_indicators(ordered)
    return contexts
