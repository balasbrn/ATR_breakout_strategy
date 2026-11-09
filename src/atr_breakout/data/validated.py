"""Convert Trade555 validated symbol files to canonical daily partitions."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow.dataset as ds
import pyarrow.fs as fs
import pyarrow.parquet as pq

from atr_breakout.contract_v1 import CRYPTO_MIN_ANNUAL_COMPLETENESS, STUDY_WINDOWS
from atr_breakout.data.partitions import MARKET_ZONES, VALIDATED_LAYOUT
from atr_breakout.data.schema import MINUTE_COLUMNS, PRICE_COLUMNS, validate_minutes
from atr_breakout.data.validated_parquet import price_batches, straddling_groups
from atr_breakout.data.windows import allowed_dates

DATASETS = {"US": "us_stocks", "NSE": "nse", "FX_GOLD": "fx_gold", "CRYPTO": "crypto"}
CRYPTO_SEAL = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _midnight(day, zone="UTC"):
    return pd.Timestamp(day, tz=zone).tz_convert("UTC").to_pydatetime()


def _inventory(filesystem, root, market):
    directory = f"{root.rstrip('/')}/{DATASETS[market]}"
    symbols = {}
    for entry in filesystem.get_file_info(fs.FileSelector(directory)):
        name = PurePosixPath(entry.path).name
        if entry.type != fs.FileType.Directory or not name.startswith("symbol="):
            continue
        symbol = name.removeprefix("symbol=")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", symbol):
            raise ValueError("Invalid symbol partition name")
        with filesystem.open_input_file(f"{entry.path}/audit.json") as source:
            audit = source.read()
        record = json.loads(audit)
        if record["symbol"] != symbol:
            raise ValueError("Audit symbol differs from the partition name")
        usable = record["completeness"]["usable_from"]
        price = filesystem.get_file_info(f"{entry.path}/bars.parquet")
        if price.type != fs.FileType.File:
            raise ValueError(f"Missing validated price file for {symbol}")
        symbols[symbol] = {
            "path": price.path, "size": price.size, "mtime_ns": price.mtime_ns,
            "audit_sha256": hashlib.sha256(audit).hexdigest(),
            "usable_from": date.fromisoformat(usable).isoformat() if usable else None,
        }
    if not symbols:
        raise ValueError("No validated symbol files found for this market")
    if market == "FX_GOLD" and len(symbols) != 8:
        raise ValueError("The frozen FX and gold spoke requires eight validated symbols")
    return dict(sorted(symbols.items()))


def _eligible(start):
    return (ds.field("ts") >= start) & ds.field("valid") & ds.field("usable")


def _crypto_coverage(fragment, start):
    """Screen calendar years using timestamps and flags, with no price projection."""
    first = date.fromisoformat(start)
    observed = Counter()
    for batch in price_batches(fragment, columns=["ts"], predicate=_eligible(_midnight(first)), cutoff=CRYPTO_SEAL):
        observed.update(pd.DatetimeIndex(batch["ts"].to_pandas()).year)
    dev, _, holdout = STUDY_WINDOWS["CRYPTO"]
    last = holdout[1]
    coverage = {}
    for year in range(first.year, last.year + 1):
        lower = max(first, date(year, 1, 1))
        upper = min(last, date(year, 12, 31))
        expected = ((upper - lower).days + 1) * 1440
        coverage[str(year)] = {
            "observed": observed[year], "expected": expected,
            "required": year <= dev[1].year or year >= holdout[0].year,
        }
    passed = any(row["required"] for row in coverage.values()) and all(
        row["observed"] >= row["expected"] * CRYPTO_MIN_ANNUAL_COMPLETENESS
        for row in coverage.values() if row["required"]
    )
    return {"years": coverage, "passed": passed}


def _canonical(batch, symbol, market):
    frame = batch.to_pandas().rename(columns={"ts": "ts_utc"})
    frame["symbol"] = symbol
    frame["filled"] = False
    if market == "FX_GOLD":
        frame["volume"] = float("nan")
    return frame.loc[:, list(MINUTE_COLUMNS)]


def _write_partitions(staging, out):
    partitions = []
    for month in sorted(staging.iterdir()):
        frame = pq.read_table(month).to_pandas()
        frame = frame.sort_values(["symbol", "ts_utc"], kind="stable")
        for day, rows in frame.groupby("trading_date", sort=True):
            rows = rows.loc[:, list(MINUTE_COLUMNS)]
            validate_minutes(rows)
            path = out / f"{day}.parquet"
            rows.to_parquet(path, index=False)
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            partitions.append({"date": day, "path": path.name, "sha256": digest})
    return partitions


def convert_validated(
    filesystem, root: str, out: Path, *, market: str, study=None,
    authorize_holdout=None, synthetic=False,
) -> Path:
    """Write the authorized window to local Parquet. Publish the manifest last."""
    holdout = study is not None
    if holdout and authorize_holdout is None:
        raise ValueError("Holdout conversion requires authorization")
    if out.exists():
        raise FileExistsError(out)
    if holdout:
        if not study.conversion or study.conversion.get("phase") != "study":
            raise ValueError("Holdout conversion requires a validated-layer study manifest")
        if study.market != market or study.synthetic != synthetic:
            raise ValueError("Holdout conversion does not match the study dataset")

    inventory = _inventory(filesystem, root, market)
    fingerprints = {
        symbol: {key: value for key, value in info.items() if key != "path"}
        for symbol, info in inventory.items()
    }
    if holdout and fingerprints != study.conversion["sources"]:
        raise ValueError("Validated source files or audits changed after study conversion")
    if holdout:
        authorize_holdout()

    zone = MARKET_ZONES[market]
    first, last = allowed_dates(market, holdout=holdout)
    # Keep the UTC seal as well as the local trading-date cutoff.
    cutoff = min(_midnight(last + timedelta(days=1), zone), _midnight(last + timedelta(days=1)))
    if market == "CRYPTO":
        cutoff = min(cutoff, CRYPTO_SEAL)
    sources = {
        symbol: ds.ParquetFileFormat().make_fragment(info["path"], filesystem=filesystem)
        for symbol, info in inventory.items() if info["usable_from"] is not None
    }
    coverage = {}
    if market == "CRYPTO":
        coverage = study.conversion["crypto_coverage"] if holdout else {
            symbol: _crypto_coverage(fragment, inventory[symbol]["usable_from"])
            for symbol, fragment in sources.items()
        }
    straddled = 0
    out.mkdir(mode=0o700)
    with TemporaryDirectory(dir=out) as temporary:
        staging = Path(temporary)
        for symbol_index, (symbol, fragment) in enumerate(sources.items()):
            if market == "CRYPTO" and not coverage[symbol]["passed"]:
                continue
            usable = date.fromisoformat(inventory[symbol]["usable_from"])
            start = _midnight(max(first, usable) if first is not None else usable, zone)
            if start >= cutoff:
                continue
            predicate = _eligible(start)
            if market == "US":
                predicate &= ds.field("in_session")
            columns = ["ts", *PRICE_COLUMNS]
            if market != "FX_GOLD":
                columns.append("volume")
            straddled += straddling_groups(fragment, cutoff)
            for batch_index, batch in enumerate(price_batches(
                fragment, columns=columns, predicate=predicate, cutoff=cutoff,
            )):
                frame = _canonical(batch, symbol, market)
                dates = frame["ts_utc"].dt.tz_convert(zone).dt.strftime("%Y-%m-%d")
                frame["trading_date"] = dates
                for month, rows in frame.groupby(dates.str[:7], sort=False):
                    directory = staging / month
                    directory.mkdir(exist_ok=True)
                    rows.to_parquet(directory / f"{symbol_index:05d}-{batch_index:05d}.parquet", index=False)
        partitions = _write_partitions(staging, out)
    if not partitions:
        raise ValueError("No eligible validated minutes in the selected window")

    conversion = {
        "layout": VALIDATED_LAYOUT, "phase": "holdout" if holdout else "study",
        "cutoff_utc": cutoff.isoformat(), "straddling_row_groups": straddled,
        "sources": fingerprints, "crypto_coverage": coverage,
    }
    if holdout:
        conversion["study_manifest_sha256"] = study.sha256
    manifest = out / "minutes.json"
    with manifest.open("x") as output:
        json.dump({
            "market": market, "synthetic": synthetic,
            "partitions": partitions, "conversion": conversion,
        }, output, indent=2)
        output.write("\n")
    return manifest
