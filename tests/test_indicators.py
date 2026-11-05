import pandas as pd
import pytest

from atr_breakout.core.bars import build_bars
from atr_breakout.core.indicators import add_indicators
from synthetic.generate import PLANTED_SIGNALS, generate_frame


def make_bars(close, timestamps=None):
    prices = pd.Series(close, dtype=float)
    if timestamps is None:
        timestamps = pd.date_range("2021-01-01", periods=len(prices), freq="15min", tz="UTC")
    return pd.DataFrame({
        "symbol": "SYNTHETIC",
        "ts_utc": timestamps,
        "high": prices + 1,
        "low": prices - 1,
        "close": prices,
    })


def test_wilder_atr_seed_and_gap_s3():
    result = add_indicators(make_bars([100] * 14 + [110, 110]))
    assert result["atr"].iloc[:13].isna().all()
    assert result["atr"].iloc[13] == 2
    assert result["atr"].iloc[14] == pytest.approx((13 * 2 + 11) / 14)
    assert result["atr"].iloc[15] == pytest.approx((13 * (37 / 14) + 2) / 14)
    assert result["atr_pct"].iloc[14] == pytest.approx((37 / 14) / 110)


def test_atr_rank_warmup_and_ties_s3():
    times = pd.date_range("2021-01-01", periods=31, freq="D", tz="UTC")
    result = add_indicators(make_bars([100] * len(times), times))
    assert result["atr_rank_30d"].iloc[:30].isna().all()
    assert result["atr_rank_30d"].iloc[30] == 100


def test_atr_rank_excludes_left_boundary_s3():
    start = pd.Timestamp("2021-01-01", tz="UTC")
    times = pd.date_range(start, periods=14, freq="15min")
    final_time = times[-1] + pd.Timedelta(days=30)
    bars = make_bars([100] * 16, times.append(pd.DatetimeIndex([
        final_time - pd.Timedelta(minutes=15), final_time,
    ])))
    bars.loc[14, ["high", "low"]] = [100.5, 99.5]
    bars.loc[15, ["high", "low"]] = [100.5, 99.5]
    result = add_indicators(bars)
    assert result["atr_rank_30d"].iloc[14] == pytest.approx(50)
    assert result["atr_rank_30d"].iloc[15] == pytest.approx(50)


def test_ema_and_rsi_trade555_parity_cards():
    prices = [100] * 8 + [110] + [110] * 191
    result = add_indicators(make_bars(prices))
    assert result["ema9"].iloc[:8].isna().all()
    assert result["ema9"].iloc[8] == pytest.approx(910 / 9)
    assert result["ema50"].first_valid_index() == 29
    assert result["ema200"].first_valid_index() == 29
    assert result["rsi14"].iloc[:14].isna().all()
    assert result["rsi14"].iloc[14] == 100
    assert add_indicators(make_bars([100] * 15))["rsi14"].iloc[-1] == 50
    assert add_indicators(make_bars([100] * 14 + [90]))["rsi14"].iloc[-1] == 0


def test_indicators_reject_out_of_order_bars_s3():
    with pytest.raises(ValueError, match="increasing bar timestamps"):
        add_indicators(make_bars([100, 101]).iloc[::-1])


def test_synthetic_rank_matches_direct_window_s3():
    bars = add_indicators(build_bars(generate_frame(), "CRYPTO"))
    for signal in PLANTED_SIGNALS:
        previous = bars.iloc[signal - 1]
        within_window = bars["ts_utc"].gt(previous.ts_utc - pd.Timedelta(days=30))
        within_window &= bars["ts_utc"].le(previous.ts_utc)
        values = bars.loc[within_window, "atr_pct"].dropna()
        expected = 100 * values.le(previous.atr_pct).mean()
        assert previous.atr_rank_30d == pytest.approx(expected)
        assert expected <= 20
