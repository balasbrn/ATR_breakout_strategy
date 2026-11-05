from datetime import date
import hashlib
import json
import stat

import pandas as pd
import pyarrow.parquet as pq
import pytest

from atr_breakout.cards import writer
from atr_breakout.cards.anonymise import CardKeys
from atr_breakout.cards.entry import CardContext, snapshot
from atr_breakout.cards.outcome import build_cards
from atr_breakout.core.bars import build_bars
from atr_breakout.core.indicators import add_indicators
from atr_breakout.core.signal import crypto_entry_eligible, signal_directions
from atr_breakout.core.trade import SignalResult, simulate_trades
from synthetic.generate import generate_frame


@pytest.fixture(scope="module")
def bars():
    return add_indicators(build_bars(generate_frame(), "CRYPTO"))


def test_entry_outcome_and_private_mapping_cards(bars):
    directions = signal_directions(bars)
    purity = crypto_entry_eligible(bars)
    actual = simulate_trades(bars, directions.where(purity, 0), cost_bp=12)
    cards = build_cards(
        bars, directions, actual, market="CRYPTO", purity=purity,
        keys=CardKeys({"CRYPTO": date(2021, 1, 1)}),
    )
    assert {name: len(rows) for name, rows in cards.items()} == {
        "entry": 2, "exit": 4, "outcome": 2, "event_map": 2,
    }
    entry = cards["entry"][0]
    assert entry["atr_pct"] == pytest.approx(bars.iloc[3000].atr_pct * 100)
    assert entry["vwap_method"] == "ROLLING_24H"
    assert entry["direction"] == "LONG"
    assert set(entry["missing"]) == {name for name, value in entry.items() if value is None}
    assert cards["entry"][1]["instrument_key"] == entry["instrument_key"]
    assert cards["entry"][1]["event_id"] != entry["event_id"]
    assert cards["event_map"][0]["symbol"] == "SYNTHETIC"
    assert cards["event_map"][0]["bot_net_r"] == actual[0].trade.r_net
    assert {row["exit_track"] for row in cards["exit"] if row["event_id"] == entry["event_id"]} == {
        "CARD_PLAN", "BOT_ACTUAL",
    }
    for name in ("entry", "exit", "outcome"):
        public = json.dumps(cards[name], allow_nan=False)
        assert "SYNTHETIC" not in public
        assert "2021-" not in public
        assert "signal_time" not in public
        assert "entry_price" not in public


@pytest.mark.parametrize(("status", "public_reason"), [
    ("SKIPPED_BUSY", "SYMBOL_ALREADY_OPEN"),
    ("SKIPPED_GAP", "ORDER_UNFILLED"),
    ("SKIPPED_BOUNDARY", "TIME_FILTER_VETO"),
    ("SKIPPED_PURITY", "ATR_VETO"),
])
def test_blocked_signals_have_no_actual_track_cards(bars, status, public_reason):
    directions = pd.Series(0, index=bars.index)
    directions.iloc[3000] = 1
    purity = pd.Series(status != "SKIPPED_PURITY", index=bars.index)
    actual = [] if status == "SKIPPED_PURITY" else [SignalResult(3000, 1, status)]
    cards = build_cards(
        bars, directions, actual, market="CRYPTO", purity=purity,
        keys=CardKeys({"CRYPTO": date(2021, 1, 1)}),
    )
    outcome, = cards["outcome"]
    assert outcome["action"] == "BLOCKED"
    assert outcome["action_reason"] == public_reason
    assert outcome["bot_actual"]["net_bp"] is None
    assert [row["exit_track"] for row in cards["exit"]] == ["CARD_PLAN"]


def test_plan_same_bar_collision_stops_first_cards(bars):
    bars = bars.copy()
    bar = bars.iloc[3000]
    bars.loc[3001, ["open", "high", "low"]] = [bar.close, bar.close + 3 * bar.atr, bar.close - 2 * bar.atr]
    directions = pd.Series(0, index=bars.index)
    directions.iloc[3000] = 1
    cards = build_cards(
        bars, directions, [SignalResult(3000, 1, "SKIPPED_GAP")], market="CRYPTO",
        keys=CardKeys({"CRYPTO": date(2021, 1, 1)}),
    )
    result, = cards["outcome"]
    assert result["card_plan"]["exit_reason"] == "SAME_BAR_COLLISION_STOP_FIRST"
    assert result["card_plan"]["plan_r"] == pytest.approx(-1)
    assert result["target_after_stop"] is True


def test_snapshot_uses_only_closed_context_and_prior_daily_cards(bars):
    bar = bars.iloc[3000]
    at = bar.ts_utc + pd.Timedelta(minutes=15)
    context = pd.DataFrame({
        "bar_end": [at - pd.Timedelta(hours=1), at, at + pd.Timedelta(minutes=1)],
        "trading_date": [bar.trading_date - pd.Timedelta(days=1), bar.trading_date, bar.trading_date],
        "atr": 2.0, "ema9": [90.0, 95.0, 500.0], "ema50": 80.0, "ema200": 70.0,
    })
    fields = snapshot(bars, 3000, "CRYPTO", CardContext(higher={"h1": context, "d": context}), cost_bp=12)
    assert fields["h1_ema9_dist"] == pytest.approx((bar.close - 95) / 2)
    assert fields["d_ema9_dist"] == pytest.approx((bar.close - 90) / 2)
    assert fields == snapshot(bars.iloc[:3001], 3000, "CRYPTO", CardContext(higher={"h1": context, "d": context}), cost_bp=12)


def test_cards_refuse_holdout_bars_s8(bars):
    prohibited = bars.iloc[:1].assign(trading_date=date(2023, 1, 1))
    with pytest.raises(ValueError, match="OOS cutoff"):
        build_cards(
            prohibited, pd.Series(0, index=prohibited.index), [], market="CRYPTO",
            keys=CardKeys({"CRYPTO": date(2021, 1, 1)}),
        )


def test_keys_group_same_minute_by_asset_class_cards():
    keys = CardKeys({"US": date(2021, 1, 1), "CRYPTO": date(2021, 1, 1)})
    at = pd.Timestamp("2021-01-02T14:45:00Z")
    first = keys.identify("US", "A", "STOCK_US", at, at.date())
    second = keys.identify("US", "B", "STOCK_US", at + pd.Timedelta(seconds=3), at.date())
    crypto = keys.identify("CRYPTO", "A", "CRYPTO_PERP", at, at.date())
    assert first["day_key"] == second["day_key"] == crypto["day_key"] == 2
    assert first["cluster_id"] == second["cluster_id"] != crypto["cluster_id"]
    assert first["instrument_key"] != second["instrument_key"]


def test_writer_partitions_and_private_map_cards(tmp_path, monkeypatch):
    fields = {
        "event_id": {"type": "string", "nullable": False},
        "day_key": {"type": "integer", "nullable": False, "min": 1},
    }
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({
        "tables": {"entry": {"fields": fields}, "outcome": {"fields": fields},
                   "exit": {"additional_fields": {"exit_track": {"type": "string"}}}},
        "enums": {},
    }))
    monkeypatch.setattr(writer, "SCHEMA_SHA256", hashlib.sha256(schema.read_bytes()).hexdigest())
    cards = {
        "entry": [{"event_id": "synthetic", "day_key": 2}],
        "exit": [], "outcome": [],
        "event_map": [{"event_id": "synthetic", "symbol": "PRIVATE_TEST_SYMBOL"}],
    }
    directory = tmp_path / "export"
    manifest_path = writer.write_cards(directory, cards, schema_path=schema, code_commit="a" * 40, synthetic=True)
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["synthetic"] is True
    assert "PRIVATE_TEST_SYMBOL" not in manifest_path.read_text()
    partition, = manifest["partitions"]
    parquet = manifest_path.parent / partition["relative_path"]
    assert partition["sha256"] == hashlib.sha256(parquet.read_bytes()).hexdigest()
    assert pq.ParquetFile(parquet).read().column_names == ["event_id", "day_key"]
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert (manifest_path.parent / "manifest.json.sha256").read_text().split()[0] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert not (manifest_path.parent / "event_map.parquet").exists()
    assert pq.ParquetFile(directory / "event_map.parquet").read()["symbol"].to_pylist() == ["PRIVATE_TEST_SYMBOL"]
    cards["entry"][0]["symbol"] = "PRIVATE_TEST_SYMBOL"
    with pytest.raises(ValueError, match="Unknown or private"):
        writer.write_cards(tmp_path / "rejected", cards, schema_path=schema, code_commit="a" * 40, synthetic=True)
    schema.write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        writer.write_cards(tmp_path / "wrong-schema", cards, schema_path=schema, code_commit="a" * 40, synthetic=True)


def test_cash_plan_exits_at_signal_session_close_cards(bars):
    frame = bars.iloc[2999:3002].copy()
    frame["ts_utc"] = pd.to_datetime([
        "2021-02-01 20:30", "2021-02-01 20:45", "2021-02-02 14:30",
    ], utc=True)
    frame["trading_date"] = frame["ts_utc"].dt.date
    directions = pd.Series([0, 1, 0], index=frame.index)
    cards = build_cards(
        frame, directions, [SignalResult(1, 1, "SKIPPED_BOUNDARY")], market="US",
        keys=CardKeys({"US": date(2021, 1, 1)}),
    )
    outcome, = cards["outcome"]
    assert outcome["card_plan"]["plan_result"] == "SESSION_CLOSE"
    assert outcome["card_plan"]["bars_held"] == 0
    assert outcome["card_plan"]["plan_r"] == 0
