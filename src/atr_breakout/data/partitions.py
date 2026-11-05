"""Read date-partitioned canonical minute files through the v1 window gate."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from atr_breakout.data.schema import MINUTE_COLUMNS, validate_minutes
from atr_breakout.data.windows import allowed_dates, claim_holdout, require_holdout_pass

MARKET_ZONES = {"US": "America/New_York", "NSE": "Asia/Kolkata", "CRYPTO": "UTC", "FX_GOLD": "UTC"}


@dataclass(frozen=True)
class Dataset:
    manifest: Path
    market: str
    synthetic: bool
    sha256: str
    partitions: dict[date, tuple[str, str]]

    def provenance(self, commit: str) -> dict:
        return {
            "contract": "v1", "market": self.market, "synthetic": self.synthetic,
            "manifest_sha256": self.sha256, "code_commit": commit,
        }


def open_dataset(manifest: Path, market: str) -> Dataset:
    """Read the manifest only. Price files are opened by the gated loader."""
    manifest = manifest.resolve(strict=True)
    payload = manifest.read_bytes()
    record = json.loads(payload)
    if record["market"] != market or type(record["synthetic"]) is not bool:
        raise ValueError("Dataset market or synthetic marker does not match")
    partitions = {}
    for item in record["partitions"]:
        day = date.fromisoformat(item["date"])
        if day in partitions:
            raise ValueError("Only one minute partition per market trading date is allowed")
        partitions[day] = (item["path"], item["sha256"])
    return Dataset(manifest, market, record["synthetic"], hashlib.sha256(payload).hexdigest(), partitions)


def _read_partition(path: Path, day: date, zone: str) -> tuple[pd.DataFrame, str]:
    with path.open("rb") as source:
        parquet = pq.ParquetFile(source)
        stamps = parquet.read(columns=["ts_utc"]).to_pandas()["ts_utc"]
        if (
            not isinstance(stamps.dtype, pd.DatetimeTZDtype)
            or str(stamps.dt.tz) != "UTC"
            or stamps.empty
            or not stamps.dt.tz_convert(zone).dt.date.eq(day).all()
        ):
            raise ValueError(f"Partition has timestamps outside its declared trading date: {day}")
        frame = parquet.read(columns=list(MINUTE_COLUMNS)).to_pandas()
        source.seek(0)
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    validate_minutes(frame)
    return frame, checksum


def load_minutes(
    dataset: Dataset, *, commit: str, holdout_run: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Read only selected dates. Supplying a holdout run always invokes the gate."""
    if dataset.market == "CRYPTO" and not dataset.synthetic:
        raise ValueError("Real crypto requires the approved completeness and gap-fill adapter")
    holdout = holdout_run is not None
    if holdout:
        provenance = dataset.provenance(commit)
        require_holdout_pass(holdout_run, provenance)
        reserved_start, reserved_end = allowed_dates(dataset.market, holdout=True)
        if not any(reserved_start <= day <= reserved_end for day in dataset.partitions):
            raise ValueError("No holdout partitions in the manifest")
        claim_holdout(dataset.manifest, dataset.market, provenance)
    start, end = allowed_dates(dataset.market, holdout=False)
    if holdout:
        _, end = allowed_dates(dataset.market, holdout=True)
    frames, checksums = [], {}
    root = dataset.manifest.parent
    for day, (relative, expected) in sorted(dataset.partitions.items()):
        if (start is not None and day < start) or day > end:
            continue
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("A selected partition is outside its dataset directory")
        frame, checksum = _read_partition(path, day, MARKET_ZONES[dataset.market])
        if checksum != expected:
            raise ValueError(f"Partition checksum differs from manifest: {day}")
        frames.append(frame)
        checksums[day.isoformat()] = checksum
    if not frames:
        raise ValueError("No minute partitions in the authorized window")
    return pd.concat(frames, ignore_index=True), checksums
