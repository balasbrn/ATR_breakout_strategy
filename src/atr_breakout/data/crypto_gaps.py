"""Fill isolated crypto gaps using at most one observed minute per prior symbol."""

import pandas as pd

from atr_breakout.contract_v1 import CRYPTO_MAX_FILL_GAP_MINUTES

MINUTE = pd.Timedelta(minutes=1)


def fill_crypto_day(minutes, previous):
    """Return filled current minutes, prior-day fill counts, and new carry."""
    by_symbol = minutes.groupby("symbol", sort=False)
    carry = by_symbol.tail(1).set_index("symbol")[["ts_utc", "close"]]
    timestamps = by_symbol["ts_utc"].shift()
    closes = by_symbol["close"].shift()
    if previous is not None:
        timestamps = timestamps.fillna(minutes["symbol"].map(previous["ts_utc"]))
        closes = closes.fillna(minutes["symbol"].map(previous["close"]))

    gaps = (minutes["ts_utc"] - timestamps) // MINUTE - 1
    isolated = gaps.between(1, CRYPTO_MAX_FILL_GAP_MINUTES)
    if not isolated.any():
        return minutes, pd.Series(dtype=int), carry

    fills = []
    for offset in range(1, CRYPTO_MAX_FILL_GAP_MINUTES + 1):
        selected = isolated & gaps.ge(offset)
        fills.append(pd.DataFrame({
            "ts_utc": timestamps.loc[selected] + offset * MINUTE,
            "symbol": minutes.loc[selected, "symbol"],
            "open": closes.loc[selected], "high": closes.loc[selected],
            "low": closes.loc[selected], "close": closes.loc[selected],
            "volume": 0, "filled": True,
        }))
    filled = pd.concat(fills, ignore_index=True)
    midnight = minutes["ts_utc"].iloc[0].normalize()
    current = filled["ts_utc"].ge(midnight)
    prior_counts = filled.loc[~current].groupby("symbol").size()
    output = pd.concat([minutes, filled.loc[current]], ignore_index=True).sort_values("ts_utc", kind="stable")
    return output, prior_counts, carry
