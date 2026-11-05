"""Write private event-card exports using the pinned Trade555 schema."""

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

import pyarrow as pa
import pyarrow.parquet as pq

from .entry import CARD_VERSION

SCHEMA_SHA256 = "bdf76c7b21a55e057f2344a6e330659807c4059889a148f9efd1b1d641d8f7b3"
PUBLIC_TABLES = ("entry", "exit", "outcome")
ARROW_TYPES = {
    "string": pa.string(), "object": pa.string(), "array": pa.string(),
    "number": pa.float64(), "integer": pa.int64(), "boolean": pa.bool_(),
}
FIELD_TYPES = {"string": str, "object": dict, "array": list, "number": (float, int), "integer": int, "boolean": bool}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _checked(value, spec, enums, name):
    if value is None:
        if spec.get("nullable") is False:
            raise ValueError(f"Required card field is missing: {name}")
        return None
    kind = spec["type"]
    if not isinstance(value, FIELD_TYPES[kind]) or (kind in ("number", "integer") and isinstance(value, bool)):
        raise ValueError(f"Invalid card field type: {name}")
    if kind in ("number", "integer") and (
        not math.isfinite(value) or value < spec.get("min", -math.inf) or value > spec.get("max", math.inf)
    ):
        raise ValueError(f"Card field out of bounds: {name}")
    if "enum_ref" in spec and value not in enums[spec["enum_ref"]]:
        raise ValueError(f"Invalid card enum: {name}")
    if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
        raise ValueError(f"Invalid card identifier: {name}")
    if name == "trigger":
        if (
            set(value) != {"name", "values"}
            or value["name"] != "atr_breakout_v1"
            or not isinstance(value["values"], dict)
            or set(value["values"]) != {"atr_rank_prev", "impulse_atr"}
            or any(type(item) not in (int, float) or not math.isfinite(item) for item in value["values"].values())
        ):
            raise ValueError("Invalid public card trigger")
    if "fields" in spec:
        return _row(value, spec["fields"], enums)
    if "required_keys" in spec and not set(spec["required_keys"]) <= value.keys():
        raise ValueError(f"Required nested card field is missing: {name}")
    return value


def _row(row, fields, enums):
    if set(row) - fields.keys():
        raise ValueError("Unknown or private field in a public card")
    return {key: _checked(row.get(key), spec, enums, key) for key, spec in fields.items()}


def _parquet(table, path):
    with path.open("xb") as output:
        path.chmod(0o600)
        pq.write_table(table, output, compression="zstd", use_dictionary=False)


def write_cards(
    directory: Path, cards: dict[str, list[dict]], *, schema_path: Path,
    code_commit: str, synthetic: bool,
) -> Path:
    """Write a fresh, owner-only delivery. Manifest presence marks completion."""
    raw_schema = schema_path.read_bytes()
    if hashlib.sha256(raw_schema).hexdigest() != SCHEMA_SHA256:
        raise ValueError("Trade555 event-card schema checksum does not match")
    if not re.fullmatch(r"[0-9a-f]{40}", code_commit):
        raise ValueError("A full code commit SHA is required")
    schema = json.loads(raw_schema)
    entry_fields = schema["tables"]["entry"]["fields"]
    table_fields = {
        "entry": entry_fields,
        "exit": {**entry_fields, **schema["tables"]["exit"]["additional_fields"]},
        "outcome": schema["tables"]["outcome"]["fields"],
    }
    partitions = {}
    for name in PUBLIC_TABLES:
        by_day = defaultdict(list)
        for row in cards[name]:
            normalized = _row(row, table_fields[name], schema["enums"])
            by_day[normalized["day_key"]].append(normalized)
        partitions[name] = by_day

    directory.mkdir(mode=0o700)
    public = directory / "public"
    public.mkdir(mode=0o700)
    manifest = {
        "card_version": CARD_VERSION, "synthetic": synthetic,
        "metadata": {"code_commit": code_commit},
        "counts": {name: len(cards[name]) for name in PUBLIC_TABLES},
        "partitions": [],
    }
    for name, by_day in partitions.items():
        fields = table_fields[name]
        for day, rows in sorted(by_day.items()):
            rows.sort(key=lambda row: (row["event_id"], row.get("exit_track", "")))
            path = public / name / f"day_key={day}" / "part-00000.parquet"
            path.parent.mkdir(parents=True)
            arrays = [
                pa.array([
                    _json(value) if isinstance(value := row[key], (dict, list)) else value
                    for row in rows
                ], type=ARROW_TYPES[spec["type"]])
                for key, spec in fields.items()
            ]
            _parquet(pa.Table.from_arrays(arrays, names=list(fields)), path)
            manifest["partitions"].append({
                "table": name, "day_key": day, "relative_path": path.relative_to(public).as_posix(),
                "row_count": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    if cards["event_map"]:
        _parquet(pa.Table.from_pylist(cards["event_map"]), directory / "event_map.parquet")
    payload = (_json(manifest) + "\n").encode()
    manifest_path = public / "manifest.json"
    (public / "manifest.json.sha256").write_text(
        f"{hashlib.sha256(payload).hexdigest()}  manifest.json\n", encoding="utf-8",
    )
    temporary_manifest = public / ".manifest.tmp"
    temporary_manifest.write_bytes(payload)
    temporary_manifest.rename(manifest_path)
    return manifest_path
