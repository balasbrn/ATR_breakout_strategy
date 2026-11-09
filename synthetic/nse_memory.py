"""Generate NSE-shaped canonical partitions for a synthetic memory check."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from atr_breakout.data.sessions import session_schedule

DEFAULT_SYMBOLS = 233
MAX_YEARS = 8


def write_nse_memory_fixture(directory: Path, *, years: int = 1, symbols: int = DEFAULT_SYMBOLS) -> Path:
    """Write one scheduled cash session at a time and return the manifest path."""
    if not 1 <= years <= MAX_YEARS or symbols < 1:
        raise ValueError("NSE memory fixtures require 1–8 years and at least one symbol")

    schedule = session_schedule("NSE")
    start_year = int(schedule["start_date"][:4])
    end_year = start_year + years
    schedule["end_date"] = f"{end_year - 1}-12-31"
    schedule["sessions"] = [
        session for session in schedule["sessions"] if int(session["open"][:4]) < end_year
    ]
    directory.mkdir(mode=0o700)
    (directory / "sessions.json").write_text(json.dumps(schedule, indent=2) + "\n")

    rng = np.random.default_rng(17)
    indices = np.arange(symbols)
    names = [f"FAKE_NSE_{index:03d}" for index in indices]
    price_ticks = 10_000 + indices * 10
    partitions = []
    for index, session in enumerate(schedule["sessions"]):
        stamps = pd.date_range(session["open"], session["close"], freq="min", inclusive="left")
        count = len(stamps)
        breakout = (index - indices) % 20 == 0
        quiet = breakout | ((index + 1 - indices) % 20 == 0)
        changes = rng.integers(-4, 5, size=(symbols, count))
        changes[quiet] = rng.integers(-1, 2, size=(quiet.sum(), count))
        # Stagger impulses by symbol so the cards path also has work to do.
        direction = 1 - 2 * ((index // 20 + indices[breakout]) % 2)
        changes[breakout, 150:165] = 5 * direction[:, None]
        closes = price_ticks[:, None] + changes.cumsum(axis=1)
        opens = closes - changes
        price_ticks = closes[:, -1].copy()

        frame = pd.DataFrame({
            "ts_utc": stamps.take(np.tile(np.arange(count), symbols)),
            "open": opens.ravel() / 100,
            "high": (np.maximum(opens, closes).ravel() + 1) / 100,
            "low": (np.minimum(opens, closes).ravel() - 1) / 100,
            "close": closes.ravel() / 100,
            "volume": 1.0,
            "symbol": np.repeat(names, count),
            "filled": False,
        })
        day = stamps[0].tz_convert("Asia/Kolkata").date().isoformat()
        path = directory / f"{day}.parquet"
        frame.to_parquet(path, index=False)
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        partitions.append({"date": day, "path": path.name, "sha256": checksum})

    manifest = directory / "minutes.json"
    manifest.write_text(json.dumps({
        "market": "NSE", "synthetic": True, "partitions": partitions,
    }, indent=2) + "\n")
    return manifest
