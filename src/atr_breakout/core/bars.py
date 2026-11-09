"""Aggregate validated minute bars on UTC quarter-hour boundaries."""

import pandas as pd

from atr_breakout.contract_v1 import BAR_MINUTES

CASH_SESSIONS = {
    "US": ("America/New_York", 9 * 60 + 30, 16 * 60),
    "NSE": ("Asia/Kolkata", 9 * 60 + 15, 15 * 60 + 30),
}
BAR_SIZE = pd.Timedelta(minutes=BAR_MINUTES)


def build_bars(minutes: pd.DataFrame, market: str) -> pd.DataFrame:
    """Build 15-minute bars per symbol from a validated minute frame.

    Timestamps label bar opens. Missing buckets are omitted. Partial buckets
    retain their observed OHLC and expose missing and filled minute counts.
    """
    if market in CASH_SESSIONS:
        timezone, start, end = CASH_SESSIONS[market]
        local = minutes["ts_utc"].dt.tz_convert(timezone)
        clock = local.dt.hour * 60 + local.dt.minute
        minutes = minutes.loc[(start <= clock) & (clock < end)]
    elif market in ("CRYPTO", "FX_GOLD"):
        timezone = "UTC"
    else:
        raise ValueError(f"Unknown market: {market}")

    buckets = minutes["ts_utc"].dt.floor(BAR_SIZE)
    grouped = minutes.groupby(["symbol", buckets], sort=False, observed=True)
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        minute_count=("open", "size"),
        filled_minutes=("filled", "sum"),
    )
    bars["volume"] = grouped["volume"].sum(min_count=1)
    if market == "FX_GOLD":
        bars["volume"] = float("nan")
    bars = bars.reset_index()
    bars["missing_minutes"] = BAR_MINUTES - bars["minute_count"]
    bars["trading_date"] = bars["ts_utc"].dt.tz_convert(timezone).dt.date
    return mark_overnight(bars, market)


def mark_overnight(bars: pd.DataFrame, market: str) -> pd.DataFrame:
    """Mark transitions on chronologically ordered bars, including across partitions."""
    bars["overnight"] = False
    if market in CASH_SESSIONS:
        previous_date = bars.groupby("symbol", sort=False)["trading_date"].shift()
        bars["overnight"] = previous_date.notna() & previous_date.ne(bars["trading_date"])
    elif market == "FX_GOLD":
        timestamps = bars["ts_utc"]
        previous = bars.groupby("symbol", sort=False)["ts_utc"].shift()
        week = timestamps.dt.tz_localize(None).dt.to_period("W-SAT")
        previous_week = previous.dt.tz_localize(None).dt.to_period("W-SAT")
        bars["overnight"] = (timestamps - previous > BAR_SIZE) & week.ne(previous_week)
    return bars
