"""Indicators calculated in timestamp order for one symbol."""

from bisect import bisect_left, bisect_right, insort_right

import numpy as np
import pandas as pd

from atr_breakout.contract_v1 import ATR_PERIOD, ATR_RANK_DAYS

EMA_PERIODS = (9, 50, 200)
RSI_PERIOD = 14


def _wilder_average(values: pd.Series, period: int) -> pd.Series:
    if len(values) < period:
        return pd.Series(np.nan, index=values.index)
    seeded = values.iloc[period - 1:].astype(float).copy()
    seeded.iloc[0] = values.iloc[:period].mean()
    return seeded.ewm(alpha=1 / period, adjust=False).mean().reindex(values.index)


def _atr_rank(timestamps: pd.Series, atr_pct: pd.Series) -> np.ndarray:
    ranks = np.full(len(atr_pct), np.nan)
    if not len(atr_pct):
        return ranks
    history = []
    start = 0
    window = pd.Timedelta(days=ATR_RANK_DAYS)
    times = timestamps.array
    values = atr_pct.to_numpy()
    for index, (timestamp, value) in enumerate(zip(times, values)):
        cutoff = timestamp - window
        while start < index and times[start] <= cutoff:
            expired = values[start]
            if not np.isnan(expired):
                history.pop(bisect_left(history, expired))
            start += 1
        if not np.isnan(value):
            insort_right(history, value)
            if times[0] <= cutoff:
                ranks[index] = 100 * bisect_right(history, value) / len(history)
    return ranks


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with ATR, ATR/close, 30-day rank, EMAs and RSI.

    Input is a single symbol's bars. RSI is 50 on a flat series. EMAs use
    the first close as their seed and become visible after their period.
    """
    timestamps = bars["ts_utc"]
    if (
        bars["symbol"].nunique() > 1
        or not timestamps.is_monotonic_increasing
        or not timestamps.is_unique
    ):
        raise ValueError("Indicators require one symbol with increasing bar timestamps")

    result = bars.copy()
    close = bars["close"]
    previous_close = close.shift()
    true_range = (
        pd.concat([bars["high"], previous_close], axis=1).max(axis=1)
        - pd.concat([bars["low"], previous_close], axis=1).min(axis=1)
    )
    result["atr"] = _wilder_average(true_range, ATR_PERIOD)
    result["atr_pct"] = result["atr"] / close
    result["atr_rank_30d"] = _atr_rank(timestamps, result["atr_pct"])

    for period in EMA_PERIODS:
        result[f"ema{period}"] = close.ewm(span=period, adjust=False, min_periods=period).mean()

    changes = close.diff().iloc[1:]
    gains = _wilder_average(changes.clip(lower=0), RSI_PERIOD)
    losses = _wilder_average(-changes.clip(upper=0), RSI_PERIOD)
    total = gains + losses
    result["rsi14"] = (100 * gains / total).mask(total.eq(0), 50).reindex(bars.index)
    return result
