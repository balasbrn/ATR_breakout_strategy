"""Parity checks for daily partition streaming on synthetic bars."""

from datetime import date
import weakref

import pandas as pd
import pytest

from atr_breakout.cards.context import higher_timeframes
from atr_breakout.data.partitions import Dataset, iter_minute_partitions
from atr_breakout.runner import prepare_bars, prepare_partitioned_bars
from synthetic.generate import generate_frame


@pytest.mark.parametrize("market", ["CRYPTO", "FX_GOLD", "US", "NSE"])
def test_streaming_matches_eager_bars_and_context_s3_s8(market):
    minutes = generate_frame().iloc[:4 * 1440].copy()
    zone, open_time, close_time = {
        "US": ("America/New_York", "09:30", "16:00"),
        "NSE": ("Asia/Kolkata", "09:15", "15:30"),
    }.get(market, ("UTC", None, None))
    # A sparse bucket before a later day and a partial bucket at the final cutoff.
    minutes = minutes.drop(index=range(900, 1440)).iloc[:-91]
    second = minutes.assign(symbol="OTHER")
    minutes = pd.concat([minutes, second], ignore_index=True)
    days = minutes["ts_utc"].dt.tz_convert(zone).dt.date
    sessions = [
        {
            "open": pd.Timestamp(f"{day} {open_time}", tz=zone).isoformat(),
            "close": pd.Timestamp(f"{day} {close_time}", tz=zone).isoformat(),
        }
        for day in sorted(days.unique())
    ] if open_time else None

    partitions = ((day, rows, day.isoformat()) for day, rows in minutes.groupby(days))
    actual, actual_context, checksums = prepare_partitioned_bars(
        partitions, market, cards=True, sessions=sessions,
    )
    expected = prepare_bars(minutes, market)
    expected_context = higher_timeframes(minutes, market, sessions=sessions)
    assert checksums == {day.isoformat(): day.isoformat() for day in sorted(days.unique())}
    assert actual.keys() == expected.keys()
    assert actual_context.keys() == expected_context.keys()
    for symbol, frame in expected.items():
        pd.testing.assert_frame_equal(actual[symbol], frame)
    for symbol, frames in expected_context.items():
        assert actual_context[symbol].keys() == frames.keys()
        for prefix, frame in frames.items():
            pd.testing.assert_frame_equal(actual_context[symbol][prefix], frame)


@pytest.mark.parametrize("cards", [False, True])
def test_streaming_releases_minutes_before_loading_the_next_date_s8(tmp_path, monkeypatch, cards):
    first, second = date(2022, 1, 1), date(2022, 1, 2)
    for day in (first, second):
        (tmp_path / f"{day}.parquet").touch()
    dataset = Dataset(tmp_path / "minutes.json", "CRYPTO", True, "test", {
        first: (f"{first}.parquet", "first"),
        second: (f"{second}.parquet", "second"),
    })
    observed = []

    def read_partition(_path, day, _zone):
        assert all(reference() is None for reference in observed)
        frame = generate_frame().head(15).copy()
        frame["ts_utc"] = pd.date_range(day, periods=15, freq="min", tz="UTC")
        observed.append(weakref.ref(frame))
        return frame, dataset.partitions[day][1]

    monkeypatch.setattr("atr_breakout.data.partitions._read_partition", read_partition)
    frames, _, checksums = prepare_partitioned_bars(
        iter_minute_partitions(dataset, commit="test"), dataset.market, cards=cards,
    )
    assert len(frames["SYNTHETIC"]) == 2
    assert checksums == {first.isoformat(): "first", second.isoformat(): "second"}
    assert all(reference() is None for reference in observed)


def test_crypto_stream_fills_an_isolated_gap_across_midnight_s12():
    start = pd.Timestamp("2022-01-01T00:00Z")
    midnight = start + pd.Timedelta(days=1)
    complete = generate_frame().head(2 * 1440).copy()
    complete["ts_utc"] = pd.date_range(start, periods=len(complete), freq="min")
    missing = [1438, 1439, 1440]
    close = complete.loc[1437, "close"]
    complete.loc[missing, ["open", "high", "low", "close", "volume"]] = [close, close, close, close, 0]
    complete.loc[missing, "filled"] = True
    # A four-minute gap on another symbol must remain missing.
    long_gap = complete.assign(symbol="OTHER").drop(index=[1438, 1439, 1440, 1441])
    expected_minutes = pd.concat([complete, long_gap], ignore_index=True)
    raw = pd.concat([complete.drop(index=missing), long_gap], ignore_index=True)
    grouped = raw.groupby(raw["ts_utc"].dt.date)
    frames, context, _ = prepare_partitioned_bars(
        ((day, part, "sha") for day, part in grouped), "CRYPTO", cards=True,
    )
    expected = prepare_bars(expected_minutes, "CRYPTO")
    for symbol in expected:
        pd.testing.assert_frame_equal(frames[symbol], expected[symbol])
    previous, current = frames["SYNTHETIC"].loc[
        frames["SYNTHETIC"]["ts_utc"].isin([midnight - pd.Timedelta(minutes=15), midnight]),
        "filled_minutes",
    ]
    assert (previous, current) == (2, 1)
    assert context["SYNTHETIC"]["d"]["minute_count"].tolist() == [1440, 1440]
    assert "d" not in context.get("OTHER", {})


def test_streaming_matches_eager_stage_files_metrics_and_card_bytes_s3_s6_s8(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from itertools import count
    import hashlib
    import json
    from types import SimpleNamespace
    from uuid import UUID

    from atr_breakout import cli
    from atr_breakout.cards import writer
    from atr_breakout.data.partitions import load_minutes, open_dataset
    from synthetic.generate import write_study_fixture

    market = "CRYPTO"
    manifest = write_study_fixture(tmp_path / "fixture", symbols=("SYNTHETIC", "OTHER"))
    dataset = open_dataset(manifest, market)
    commit = "a" * 40
    monkeypatch.setattr(cli, "_code_commit", lambda **_: commit)
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(
        now=lambda _: datetime(2026, 1, 1, tzinfo=timezone.utc),
    ))

    schema = tmp_path / "synthetic-schema.json"

    def field_specs(rows):
        types = {str: "string", dict: "object", list: "array", bool: "boolean", int: "integer", float: "number"}
        specs = {}
        for row in rows:
            for key, value in row.items():
                if value is not None:
                    specs[key] = {"type": types[type(value)]}
                else:
                    specs.setdefault(key, {"type": "string"})
        return specs

    def serialize_cards(directory, cards, **kwargs):
        if not schema.exists():
            entry = field_specs(cards["entry"] + cards["exit"])
            exit_only = {"exit_track", "exit_reason", "bot_exit_reason", "bars_held", "move_since_entry_atr"}
            schema.write_text(json.dumps({"enums": {}, "tables": {
                "entry": {"fields": {key: value for key, value in entry.items() if key not in exit_only}},
                "exit": {"additional_fields": {key: entry[key] for key in sorted(exit_only)}},
                "outcome": {"fields": field_specs(cards["outcome"])},
            }}))
            monkeypatch.setattr(writer, "SCHEMA_SHA256", hashlib.sha256(schema.read_bytes()).hexdigest())
        writer.write_cards(directory, cards, **{**kwargs, "schema_path": schema})
        (directory / "cards.json").write_text(json.dumps(cards, sort_keys=True, allow_nan=False))

    monkeypatch.setattr(cli, "write_cards", serialize_cards)

    def run(label):
        ids = count(1)
        monkeypatch.setattr("atr_breakout.cards.anonymise.uuid4", lambda: UUID(int=next(ids), version=4))
        monkeypatch.setattr("atr_breakout.cards.anonymise.secrets.token_hex", lambda _: f"{next(ids):012x}")
        options = dict(data=manifest, market=market, archive=None, sessions=None, schema=None)
        run_dir = tmp_path / label
        card_dir = tmp_path / f"{label}-cards"
        for action in ("stage-a", "stage-b"):
            cli._run(SimpleNamespace(action=action, out=run_dir, **options), action)
        cli._run(SimpleNamespace(action="cards", out=card_dir, **options), "cards")
        files = {path.name: path.read_bytes() for path in run_dir.glob("*.json")}
        files.update({
            path.relative_to(card_dir).as_posix(): path.read_bytes()
            for path in card_dir.rglob("*") if path.is_file()
        })
        return files

    streamed = run("streamed")

    def eager(_partitions, _market, *, cards, sessions):
        minutes, checksums = load_minutes(dataset, commit=commit)
        context = higher_timeframes(minutes, market, sessions=sessions) if cards else {}
        return prepare_bars(minutes, market), context, checksums

    monkeypatch.setattr(cli, "prepare_partitioned_bars", eager)
    assert streamed == run("eager")
    assert json.loads(streamed["cards.json"])["entry"]
