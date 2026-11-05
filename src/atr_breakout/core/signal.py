"""Breakout signals and crypto entry eligibility for one symbol's bars."""

import pandas as pd

from atr_breakout.contract_v1 import (
    BAR_MINUTES,
    BREAKOUT_LOOKBACK,
    CRYPTO_MAX_FILLED_MINUTES_PER_BAR,
    CRYPTO_MAX_IMPURE_LOOKBACK_BARS,
    MAX_COMPRESSION_RANK,
    MIN_IMPULSE_ATR,
    STOP_REVIEW_BAR,
)


def signal_directions(bars: pd.DataFrame, *, require_compression: bool = True) -> pd.Series:
    """Return +1 for long, -1 for short, and 0 otherwise, in bar order.

    Input is one symbol's chronological bars with indicators. Crypto entry
    eligibility is evaluated separately from the §4 signal.
    """
    previous_high = bars["high"].shift().rolling(BREAKOUT_LOOKBACK).max()
    previous_low = bars["low"].shift().rolling(BREAKOUT_LOOKBACK).min()
    minimum_body = MIN_IMPULSE_ATR * bars["atr"].shift()
    body = bars["close"] - bars["open"]
    long = (bars["close"] > previous_high) & (body >= minimum_body)
    short = (bars["close"] < previous_low) & (-body >= minimum_body)
    directions = long.astype("int8") - short.astype("int8")
    if require_compression:
        compressed = bars["atr_rank_30d"].shift().le(MAX_COMPRESSION_RANK)
        directions = directions.where(compressed, 0)
    return directions.rename("direction")


def crypto_entry_eligible(bars: pd.DataFrame) -> pd.Series:
    """Apply §12 O5 to the UTC slots around each crypto signal or benchmark entry.

    An omitted slot is impure, like a bar with all 15 minutes missing. Require
    observable history and follow-up through t+5 before certifying an entry.
    """
    bar_size = pd.Timedelta(minutes=BAR_MINUTES)
    lookback = BREAKOUT_LOOKBACK * bar_size
    timestamps = bars["ts_utc"]
    pure = (
        bars["filled_minutes"] + bars["missing_minutes"]
    ).le(CRYPTO_MAX_FILLED_MINUTES_PER_BAR)
    pure_by_time = pd.Series(pure.to_numpy(dtype=bool), index=pd.DatetimeIndex(timestamps))
    pure_history = pure_by_time.rolling(lookback, closed="left").sum().to_numpy()
    enough_history = timestamps.ge(timestamps.min() + lookback)
    history_passes = pure_history >= BREAKOUT_LOOKBACK - CRYPTO_MAX_IMPURE_LOOKBACK_BARS

    # Five pure observed bars spanning exactly five slots excludes omitted slots.
    future_pure = pure.rolling(STOP_REVIEW_BAR).sum().shift(-STOP_REVIEW_BAR)
    future_span = timestamps.shift(-STOP_REVIEW_BAR) - timestamps
    future_passes = future_pure.eq(STOP_REVIEW_BAR) & future_span.eq(STOP_REVIEW_BAR * bar_size)
    return (pure & enough_history & history_passes & future_passes).rename("crypto_entry_eligible")
