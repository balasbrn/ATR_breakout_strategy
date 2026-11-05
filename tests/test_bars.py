import pandas as pd
import pytest

from atr_breakout.core.bars import build_bars
from atr_breakout.data.schema import validate_minutes


def make_minutes(timestamps, symbol="SYNTHETIC"):
    prices = list(range(100, 100 + len(timestamps)))
    frame = pd.DataFrame({
        "ts_utc": pd.to_datetime(timestamps, utc=True),
        "open": prices,
        "high": [price + 2 for price in prices],
        "low": [price - 1 for price in prices],
        "close": [price + 1 for price in prices],
        "volume": 10.0,
        "symbol": symbol,
        "filled": False,
    })
    validate_minutes(frame)
    return frame


def test_aggregate_utc_ohlcv_and_coverage_s3():
    minutes = make_minutes([
        "2021-01-01 00:01", "2021-01-01 00:02", "2021-01-01 00:15",
    ])
    minutes.loc[1, ["open", "high", "low", "close", "volume", "filled"]] = [
        101, 101, 101, 101, 0, True,
    ]
    bars = build_bars(minutes, "CRYPTO")
    assert bars["ts_utc"].tolist() == list(pd.to_datetime([
        "2021-01-01 00:00", "2021-01-01 00:15",
    ], utc=True))
    assert bars.loc[0, ["open", "high", "low", "close", "volume"]].tolist() == [
        100, 102, 99, 101, 10,
    ]
    assert bars["filled_minutes"].tolist() == [1, 0]
    assert bars["missing_minutes"].tolist() == [13, 14]


@pytest.mark.parametrize(("market", "timestamps", "expected"), [
    ("US", [
        "2021-03-12 14:29", "2021-03-12 14:30", "2021-03-12 21:00",
        "2021-03-15 13:30", "2021-03-15 19:59", "2021-03-15 20:00",
    ], ["2021-03-12 14:30", "2021-03-15 13:30", "2021-03-15 19:45"]),
    ("NSE", [
        "2021-03-12 03:44", "2021-03-12 03:45", "2021-03-12 10:00",
        "2021-03-15 03:45", "2021-03-15 09:59", "2021-03-15 10:00",
    ], ["2021-03-12 03:45", "2021-03-15 03:45", "2021-03-15 09:45"]),
])
def test_cash_sessions_and_overnight_s2(market, timestamps, expected):
    bars = build_bars(make_minutes(timestamps), market)
    assert bars["ts_utc"].tolist() == list(pd.to_datetime(expected, utc=True))
    assert bars["overnight"].tolist() == [False, True, False]


def test_fx_weekend_break_and_unused_tick_volume_s2():
    bars = build_bars(make_minutes([
        "2021-03-12 21:45", "2021-03-14 21:00", "2021-03-15 00:00",
    ]), "FX_GOLD")
    assert bars["overnight"].tolist() == [False, True, False]
    assert bars["volume"].isna().all()


def test_symbols_aggregate_separately_s3():
    first = make_minutes(["2021-01-01 00:00", "2021-01-01 00:15"])
    second = first.assign(symbol="OTHER")
    bars = build_bars(pd.concat([first, second]).iloc[[0, 2, 1, 3]], "CRYPTO")
    assert bars["symbol"].tolist() == ["SYNTHETIC", "OTHER"] * 2
    assert bars["minute_count"].tolist() == [1] * 4


def test_empty_session_returns_empty_bars_s2():
    bars = build_bars(make_minutes(["2021-01-01 00:00"]), "US")
    assert bars.empty
    assert {"ts_utc", "trading_date", "overnight"} <= set(bars.columns)
