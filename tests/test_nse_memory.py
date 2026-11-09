import json

import pytest

from atr_breakout.data.partitions import iter_minute_partitions, open_dataset
from synthetic.nse_memory import write_nse_memory_fixture


@pytest.mark.parametrize(("years", "symbols", "dates"), [
    (1, 233, ["2015-01-02"]),
    (8, 2, ["2015-01-02", "2022-12-30"]),
])
def test_nse_memory_fixture_uses_canonical_regular_sessions_s2_s8(tmp_path, monkeypatch, years, symbols, dates):
    all_dates = ["2015-01-02", "2022-12-30"]
    monkeypatch.setattr("synthetic.nse_memory.session_schedule", lambda market: {
        "market": market, "start_date": "2015-01-01", "end_date": "2022-12-31",
        "sessions": [
            {"open": f"{day}T03:45:00+00:00", "close": f"{day}T10:00:00+00:00"}
            for day in all_dates
        ],
    })

    root = tmp_path / "fixture"
    manifest = write_nse_memory_fixture(root, years=years, symbols=symbols)
    dataset = open_dataset(manifest, "NSE")
    assert dataset.synthetic
    assert [day.isoformat() for day in dataset.partitions] == dates
    schedule = json.loads((root / "sessions.json").read_text())
    assert len(schedule["sessions"]) == len(dates)
    assert schedule["end_date"] == f"{2014 + years}-12-31"

    for _, frame, _ in iter_minute_partitions(dataset, commit="synthetic"):
        assert len(frame) == symbols * 375
        assert frame.groupby("symbol").size().eq(375).all()
        local = frame["ts_utc"].dt.tz_convert("Asia/Kolkata")
        assert local.min().strftime("%H:%M") == "09:15"
        assert local.max().strftime("%H:%M") == "15:29"
        assert not frame["filled"].any()
