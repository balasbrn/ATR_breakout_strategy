"""Standard minute frame shared by vendor adapters and synthetic fixtures.

Timestamps label minute opens. Missing minutes are allowed. Volume may be
missing when unavailable, and filled rows represent flat, zero-volume bars.
"""

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_float_dtype, is_integer_dtype

PRICE_COLUMNS = ("open", "high", "low", "close")
MINUTE_COLUMNS = ("ts_utc", *PRICE_COLUMNS, "volume", "symbol", "filled")


def validate_minutes(frame: pd.DataFrame) -> None:
    """Raise ValueError if a frame violates the standard minute schema."""
    if not frame.columns.is_unique:
        raise ValueError("Minute columns must be unique")
    missing = set(MINUTE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing minute columns: {sorted(missing)}")

    timestamps = frame["ts_utc"]
    if (
        not isinstance(timestamps.dtype, pd.DatetimeTZDtype)
        or str(timestamps.dt.tz) != "UTC"
        or timestamps.isna().any()
        or not timestamps.eq(timestamps.dt.floor("min")).all()
    ):
        raise ValueError("ts_utc must contain minute-aligned UTC timestamps")

    symbols = frame["symbol"]
    if not symbols.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("symbol must contain nonblank strings")
    if frame.duplicated(["symbol", "ts_utc"]).any():
        raise ValueError("Minute timestamps must be unique per symbol")

    for name in (*PRICE_COLUMNS, "volume"):
        dtype = frame[name].dtype
        if not (is_float_dtype(dtype) or is_integer_dtype(dtype)):
            raise ValueError(f"{name} must be numeric")

    prices = frame.loc[:, list(PRICE_COLUMNS)].to_numpy(dtype=float, na_value=np.nan)
    opened, high, low, close = prices.T
    if (
        not np.isfinite(prices).all()
        or (low <= 0).any()
        or (low > np.minimum(opened, close)).any()
        or (high < np.maximum(opened, close)).any()
    ):
        raise ValueError("Prices must be finite, positive, and satisfy OHLC bounds")

    volume = frame["volume"].dropna().to_numpy(dtype=float)
    if not np.isfinite(volume).all() or (volume < 0).any():
        raise ValueError("Present volume must be finite and nonnegative")

    filled = frame["filled"]
    if not is_bool_dtype(filled.dtype) or filled.isna().any():
        raise ValueError("filled must contain booleans")
    filled_rows = filled.to_numpy(dtype=bool)
    filled_volume = frame.loc[filled_rows, "volume"]
    if (high[filled_rows] != low[filled_rows]).any() or not filled_volume.eq(0).fillna(False).all():
        raise ValueError("Filled minutes must have flat prices and zero volume")
