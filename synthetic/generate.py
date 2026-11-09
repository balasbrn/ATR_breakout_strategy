"""Seeded, synthetic 1-minute OHLC data for the v1 mechanics smoke test."""

import random
from datetime import datetime, timedelta, timezone

MINUTES_PER_BAR = 15
WARMUP_BARS = 31 * 24 * 4
PLANTED_SIGNALS = {WARMUP_BARS + 24: 1, WARMUP_BARS + 100: -1}


def generate_minutes(seed=17):
    rng = random.Random(seed)
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    for bar_index in range(max(PLANTED_SIGNALS) + 21):
        quiet = any(1 <= signal - bar_index <= 24 for signal in PLANTED_SIGNALS)
        impulse = PLANTED_SIGNALS.get(bar_index, 0)
        follow_through = sum(
            side for signal, side in PLANTED_SIGNALS.items()
            if 1 <= bar_index - signal <= 20
        )
        for minute in range(MINUTES_PER_BAR):
            opened = price
            if impulse:
                price += impulse * 0.05
            elif follow_through:
                price += follow_through * 0.004
            else:
                price += rng.uniform(-0.001 if quiet else -0.025,
                                     0.001 if quiet else 0.025)
            wick = 0.002 if quiet else 0.015
            timestamp = start + timedelta(minutes=bar_index * MINUTES_PER_BAR + minute)
            yield timestamp, opened, max(opened, price) + wick, min(opened, price) - wick, price


def generate_frame(seed=17):
    """Build the standard minute frame for the fictional SYNTHETIC symbol."""
    import pandas as pd

    from atr_breakout.data.schema import MINUTE_COLUMNS

    rows = (
        (*minute, 1.0, "SYNTHETIC", False)
        for minute in generate_minutes(seed)
    )
    return pd.DataFrame.from_records(rows, columns=MINUTE_COLUMNS)


def write_study_fixture(directory, *, symbols=("SYNTHETIC",)):
    """Write a small canonical CRYPTO dataset for the M4 dry run."""
    import hashlib
    import json

    import pandas as pd

    directory.mkdir(mode=0o700)
    frame = pd.concat(
        [generate_frame(seed=17 + index).assign(symbol=symbol) for index, symbol in enumerate(symbols)],
        ignore_index=True,
    )
    partitions = []
    for offset in (0, 365):
        shifted = frame.assign(ts_utc=frame["ts_utc"] + pd.Timedelta(days=offset))
        for day, rows in shifted.groupby(shifted["ts_utc"].dt.date):
            path = directory / f"{day}.parquet"
            rows.to_parquet(path, index=False)
            partitions.append({
                "date": day.isoformat(), "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest = directory / "minutes.json"
    manifest.write_text(json.dumps({
        "market": "CRYPTO", "synthetic": True, "partitions": partitions,
    }, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Write the seeded v1 study fixture")
    parser.add_argument("--out", type=Path, required=True)
    print(write_study_fixture(parser.parse_args().out))
