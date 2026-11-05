"""Run-scoped opaque identifiers with a separate private crosswalk."""

from datetime import date
import secrets
from uuid import uuid4

import pandas as pd


class CardKeys:
    def __init__(self, first_dates: dict[str, date]):
        self._first_dates = first_dates.copy()
        self._instruments: dict[tuple[str, str], str] = {}
        self._clusters: dict[tuple[str, pd.Timestamp], str] = {}

    def day_key(self, market: str, day: date) -> int:
        key = (day - self._first_dates[market]).days + 1
        if key < 1:
            raise ValueError("Card day precedes the market's first data date")
        return key

    def identify(
        self, market: str, symbol: str, asset_class: str, at: pd.Timestamp, day: date,
    ) -> dict:
        instrument = (market, symbol)
        cluster = (asset_class, at.floor("min"))
        if instrument not in self._instruments:
            self._instruments[instrument] = "inst_" + secrets.token_hex(6)
        if cluster not in self._clusters:
            self._clusters[cluster] = "clu_" + secrets.token_hex(6)
        return {
            "event_id": str(uuid4()),
            "day_key": self.day_key(market, day),
            "instrument_key": self._instruments[instrument],
            "cluster_id": self._clusters[cluster],
        }
