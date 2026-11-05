import pandas as pd
import pytest

from atr_breakout.contract_v1 import BAR_MINUTES, MAX_HOLD_BARS
from atr_breakout.data.schema import MINUTE_COLUMNS, validate_minutes
from synthetic.generate import PLANTED_SIGNALS, generate_frame


def test_synthetic_minutes_s3():
    frame = generate_frame()
    validate_minutes(frame)
    assert tuple(frame.columns) == MINUTE_COLUMNS
    pd.testing.assert_frame_equal(frame, generate_frame())
    assert frame["symbol"].unique().tolist() == ["SYNTHETIC"]
    assert frame["ts_utc"].diff().dropna().eq(pd.Timedelta(minutes=1)).all()
    assert len(frame) == (max(PLANTED_SIGNALS) + MAX_HOLD_BARS + 1) * BAR_MINUTES
    for index, side in PLANTED_SIGNALS.items():
        bar = frame.iloc[index * BAR_MINUTES:(index + 1) * BAR_MINUTES]
        assert side * (bar["close"].iloc[-1] - bar["open"].iloc[0]) > 0.5


@pytest.fixture
def minutes():
    return generate_frame().head(2).copy()


def test_schema_rejects_naive_timestamps_s3(minutes):
    minutes["ts_utc"] = minutes["ts_utc"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="UTC"):
        validate_minutes(minutes)


def test_schema_rejects_duplicate_minutes_s3(minutes):
    with pytest.raises(ValueError, match="unique per symbol"):
        validate_minutes(pd.concat([minutes, minutes]))


def test_schema_rejects_invalid_ohlc_s3(minutes):
    minutes.loc[0, "high"] = minutes.loc[0, "low"]
    with pytest.raises(ValueError, match="OHLC"):
        validate_minutes(minutes)


def test_schema_allows_missing_volume_s2(minutes):
    minutes["volume"] = pd.NA
    minutes["volume"] = minutes["volume"].astype("Float64")
    validate_minutes(minutes)


def test_schema_requires_flat_zero_volume_fills_s12(minutes):
    minutes.loc[0, "filled"] = True
    with pytest.raises(ValueError, match="flat prices and zero volume"):
        validate_minutes(minutes)
    minutes.loc[0, ["open", "high", "low", "close"]] = minutes.loc[0, "close"]
    minutes.loc[0, "volume"] = 0.0
    validate_minutes(minutes)
