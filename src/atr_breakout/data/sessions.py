"""Generate cash session schedules for the frozen development and OOS windows."""

from datetime import date
from importlib.metadata import version

import exchange_calendars as xc

from atr_breakout.contract_v1 import STUDY_WINDOWS

CALENDARS = {"US": "XNYS", "NSE": "XBOM"}


def session_schedule(market: str) -> dict:
    """Return the dated calendar metadata and UTC sessions for card context."""
    dev, oos, _ = STUDY_WINDOWS[market]
    first, last = dev[0], oos[1]
    calendar_name = CALENDARS[market]

    # Trade555 data_audit/checks.py:19–34 at f4fe9a2.
    calendar = xc.get_calendar(
        calendar_name, start=max(first, date(2005, 1, 3)).isoformat(), end=last.isoformat(),
    )
    schedule = calendar.schedule.loc[first.isoformat():last.isoformat()]
    return {
        "market": market,
        "calendar": calendar_name,
        "exchange_calendars_version": version("exchange_calendars"),
        "start_date": first.isoformat(),
        "end_date": last.isoformat(),
        "sessions": [
            {"open": opening.isoformat(), "close": closing.isoformat()}
            for opening, closing in schedule[["open", "close"]].apply(
                lambda column: column.dt.tz_convert("UTC")
            ).itertuples(index=False, name=None)
        ],
    }
