import pandas as pd
import pytest

from atr_breakout.cards.context import higher_timeframes
from atr_breakout.cli import main
from synthetic.generate import write_study_fixture


def minutes(start, count):
    close = pd.Series(range(100, 100 + count), dtype=float)
    return pd.DataFrame({
        "ts_utc": pd.date_range(start, periods=count, freq="min", tz="UTC"),
        "symbol": "SYNTHETIC", "open": close, "high": close + 1,
        "low": close - 1, "close": close, "volume": 1.0,
    })


@pytest.mark.parametrize("market", ["CRYPTO", "FX_GOLD"])
def test_utc_buckets_and_exclude_unfinished_tail_cards(market):
    data = minutes("2022-01-01 00:00", 24 * 60 + 125)
    result = higher_timeframes(data, market)["SYNTHETIC"]
    assert {key: len(frame) for key, frame in result.items()} == {"h1": 26, "h4": 6, "d": 1}
    first = result["h4"].iloc[0]
    assert first.ts_utc == pd.Timestamp("2022-01-01 00:00Z")
    assert first.bar_end == pd.Timestamp("2022-01-01 04:00Z")
    assert first[["open", "high", "low", "close"]].tolist() == [100, 340, 99, 339]
    assert result["d"].iloc[0].bar_end == pd.Timestamp("2022-01-02 00:00Z")


def test_crypto_requires_full_minutes_and_ig_preserves_closed_sparse_bucket_cards():
    data = minutes("2022-01-01 00:00", 120).drop(index=5)
    crypto = higher_timeframes(data, "CRYPTO")["SYNTHETIC"]["h1"]
    fx = higher_timeframes(data, "FX_GOLD")["SYNTHETIC"]["h1"]
    assert crypto["minute_count"].tolist() == [60]
    assert fx["minute_count"].tolist() == [59, 60]


@pytest.mark.parametrize(("market", "opening", "closing"), [
    ("US", "2022-11-25 14:30Z", "2022-11-25 18:00Z"),
    ("NSE", "2022-11-25 03:45Z", "2022-11-25 10:00Z"),
])
def test_cash_schedule_anchors_hours_and_daily_uses_actual_close_cards(market, opening, closing):
    start, end = pd.Timestamp(opening), pd.Timestamp(closing)
    duration = int((end - start) / pd.Timedelta(minutes=1))
    data = minutes(start - pd.Timedelta(minutes=15), duration + 30)
    schedule = [{"open": opening, "close": closing}]
    result = higher_timeframes(data, market, sessions=schedule)["SYNTHETIC"]
    assert len(result["h1"]) == duration // 60
    assert len(result.get("h4", [])) == duration // 240
    assert result["h1"].iloc[0].ts_utc == start
    assert result["d"].iloc[0].bar_end == end
    assert result["d"].iloc[0].minute_count == duration

    with_hole = higher_timeframes(data.drop(index=20), market, sessions=schedule)["SYNTHETIC"]
    assert with_hole["h1"].iloc[0].ts_utc == start + pd.Timedelta(hours=1)
    assert "d" not in with_hole


def test_cli_passes_all_three_completed_timeframes_to_cards(tmp_path, monkeypatch):
    manifest = write_study_fixture(tmp_path / "fixture")
    captured = {}

    def capture(_directory, cards, **_kwargs):
        captured.update(cards)

    monkeypatch.setattr("atr_breakout.cli.write_cards", capture)
    assert main([
        "cards", "--data", str(manifest), "--market", "CRYPTO",
        "--out", str(tmp_path / "cards"), "--schema", "unused.json",
    ]) == 0
    assert captured["entry"]
    for prefix in ("h1", "h4", "d"):
        for period in (9, 50, 200):
            assert captured["entry"][0][f"{prefix}_ema{period}_dist"] is not None
        assert captured["entry"][0][f"{prefix}_ema_order"] is not None
