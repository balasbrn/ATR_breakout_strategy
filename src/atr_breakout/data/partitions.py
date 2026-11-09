"""Read date-partitioned canonical minute files through the v1 window gate."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from atr_breakout.data.schema import MINUTE_COLUMNS, validate_minutes
from atr_breakout.data.windows import allowed_dates, claim_holdout, require_holdout_pass

VALIDATED_LAYOUT = "trade555_validated_v1.1"

MARKET_ZONES = {"US": "America/New_York", "NSE": "Asia/Kolkata", "CRYPTO": "UTC", "FX_GOLD": "UTC"}


@dataclass(frozen=True)
class Dataset:
    manifest: Path
    market: str
    synthetic: bool
    sha256: str
    partitions: dict[date, tuple[str, str]]
    conversion: dict | None = None

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
    conversion = record.get("conversion")
    if conversion is not None and (
        conversion.get("layout") != VALIDATED_LAYOUT or conversion.get("phase") not in ("study", "holdout")
    ):
        raise ValueError("Unrecognized validated conversion manifest")
    return Dataset(
        manifest, market, record["synthetic"], hashlib.sha256(payload).hexdigest(), partitions, conversion,
    )


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


def iter_minute_partitions(
    dataset: Dataset, *, commit: str, holdout_run: Path | None = None,
    archive_claim: Callable[[Path], None] | None = None,
    holdout_data: Dataset | None = None,
) -> Iterator[tuple[date, pd.DataFrame, str]]:
    """Yield validated daily partitions in order after any required holdout gate."""
    if dataset.conversion and dataset.conversion["phase"] != "study":
        raise ValueError("Use a study manifest as the primary dataset")
    if dataset.market == "CRYPTO" and not dataset.synthetic and not dataset.conversion:
        raise ValueError("Real crypto requires the approved completeness and gap-fill adapter")
    holdout = holdout_run is not None
    if holdout_data is not None and not holdout:
        raise ValueError("Converted holdout data requires the holdout command")
    if holdout:
        if dataset.conversion and holdout_data is None:
            raise ValueError("A validated-layer holdout requires its separately converted manifest")
        if holdout_data is not None:
            conversion = holdout_data.conversion or {}
            if (
                not dataset.conversion or conversion.get("phase") != "holdout"
                or conversion.get("study_manifest_sha256") != dataset.sha256
                or conversion.get("sources") != dataset.conversion["sources"]
                or holdout_data.market != dataset.market or holdout_data.synthetic != dataset.synthetic
            ):
                raise ValueError("Converted holdout manifest does not match the study dataset")
        if not dataset.synthetic and archive_claim is None:
            raise ValueError("Real holdout requires an archive for its claim and stage evidence")
        provenance = dataset.provenance(commit)
        require_holdout_pass(holdout_run, provenance)
        reserved_start, reserved_end = allowed_dates(dataset.market, holdout=True)
        reserved = holdout_data or dataset
        if not any(reserved_start <= day <= reserved_end for day in reserved.partitions):
            raise ValueError("No holdout partitions in the manifest")
        claim = claim_holdout(dataset.manifest, dataset.market, provenance)
        if archive_claim is not None:
            archive_claim(claim)
    start, study_end = allowed_dates(dataset.market, holdout=False)
    windows = [(dataset, start, study_end)]
    if holdout:
        windows.append((holdout_data or dataset, reserved_start, reserved_end))
    found = False
    for source, lower, upper in windows:
        root = source.manifest.parent
        for day, (relative, expected) in sorted(source.partitions.items()):
            if (lower is not None and day < lower) or day > upper:
                continue
            path = (root / relative).resolve(strict=True)
            if not path.is_relative_to(root):
                raise ValueError("A selected partition is outside its dataset directory")
            frame, checksum = _read_partition(path, day, MARKET_ZONES[dataset.market])
            if checksum != expected:
                raise ValueError(f"Partition checksum differs from manifest: {day}")
            found = True
            yield day, frame, checksum
            del frame
    if not found:
        raise ValueError("No minute partitions in the authorized window")


def load_minutes(
    dataset: Dataset, *, commit: str, holdout_run: Path | None = None,
    archive_claim: Callable[[Path], None] | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Read a small dataset into one frame. Study commands use the iterator."""
    frames, checksums = [], {}
    for day, frame, checksum in iter_minute_partitions(
        dataset, commit=commit, holdout_run=holdout_run, archive_claim=archive_claim,
    ):
        frames.append(frame)
        checksums[day.isoformat()] = checksum
    return pd.concat(frames, ignore_index=True), checksums
