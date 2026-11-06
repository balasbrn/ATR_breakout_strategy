from importlib.metadata import version
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from atr_breakout.cli import main
from atr_breakout.data import sessions


@pytest.mark.parametrize(("market", "calendar", "first", "last", "zone", "open_utc", "close_utc"), [
    ("US", "XNYS", "2019-10-01", "2022-12-31", "America/New_York", "14:30", "18:00"),
    ("NSE", "XBOM", "2015-01-01", "2022-12-31", "Asia/Kolkata", "04:00", "07:30"),
])
def test_sessions_cli_uses_frozen_dev_oos_dates_and_utc_cards(
    tmp_path, monkeypatch, market, calendar, first, last, zone, open_utc, close_utc,
):
    index = pd.to_datetime(["2022-11-25", "2023-01-03"])
    schedule = pd.DataFrame({
        "open": (index + pd.Timedelta(hours=9, minutes=30)).tz_localize(zone),
        "close": (index + pd.Timedelta(hours=13)).tz_localize(zone),
    }, index=index)

    def get_calendar(name, *, start, end):
        assert (name, start, end) == (calendar, first, last)
        return SimpleNamespace(schedule=schedule)

    def unexpected_dataset(*_):
        pytest.fail("Calendar generation must not open market data")

    monkeypatch.setattr(sessions.xc, "get_calendar", get_calendar)
    monkeypatch.setattr("atr_breakout.cli.open_dataset", unexpected_dataset)
    path = tmp_path / "sessions.json"
    args = ["sessions", "--market", market, "--out", str(path)]
    assert main(args) == 0
    assert json.loads(path.read_text()) == {
        "market": market,
        "calendar": calendar,
        "exchange_calendars_version": version("exchange_calendars"),
        "start_date": first,
        "end_date": last,
        "sessions": [{
            "open": f"2022-11-25T{open_utc}:00+00:00",
            "close": f"2022-11-25T{close_utc}:00+00:00",
        }],
    }
    with pytest.raises(SystemExit, match="2"):
        main(args)
