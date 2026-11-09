"""Upload immutable run artifacts and verify the stored object bytes."""

import hashlib
from pathlib import Path
import re
import subprocess

from atr_breakout.data.windows import HoldoutLocked


def _safe_path(value: str) -> bool:
    return all(re.fullmatch(r"[A-Za-z0-9_.=-]+", part) and part not in (".", "..")
               for part in value.split("/"))


def archive_destination(uri: str, directory: Path) -> str:
    """Use the output directory basename as the run ID."""
    match = re.fullmatch(r"gs://([a-z0-9][a-z0-9._-]*)/(.+?)/?", uri)
    run_id = directory.resolve().name
    if not match or not _safe_path(match[2]) or not _safe_path(run_id):
        raise ValueError("Archive requires gs://bucket/prefix and a safe output directory name")
    return f"gs://{match[1]}/{match[2]}/{run_id}"


def _fingerprint(stream) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def archive_file(path: Path, destination: str, name: str) -> None:
    if not _safe_path(name) or path.is_symlink() or not path.is_file():
        raise ValueError(f"Archive expected a regular file with a safe name: {name}")
    target = f"{destination}/{name}"
    try:
        with path.open("rb") as source:
            expected = _fingerprint(source)
        subprocess.run(
            ["gcloud", "storage", "cp", "--no-clobber", str(path.resolve()), target],
            check=True,
        )
        with subprocess.Popen(["gcloud", "storage", "cat", target], stdout=subprocess.PIPE) as reader:
            actual = _fingerprint(reader.stdout)
            if reader.wait() != 0:
                raise ValueError(f"Could not read archived object: {name}")
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Could not archive file: {name}") from error
    if actual != expected:
        raise ValueError(f"Archived size or SHA-256 differs: {name}")


def archive_directory(directory: Path, destination: str) -> None:
    for path in sorted(directory.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        archive_file(path, destination, path.relative_to(directory).as_posix())


def _require_claim_absent(target: str) -> None:
    try:
        result = subprocess.run(["gcloud", "storage", "ls", target], capture_output=True, text=True)
    except OSError as error:
        raise HoldoutLocked("Could not check the remote holdout claim") from error
    if result.returncode == 0:
        raise HoldoutLocked("A remote holdout claim already exists for this dataset or run")
    # A permission or transport error does not establish that the object is absent.
    if not result.stderr.strip().endswith("One or more URLs matched no objects."):
        raise HoldoutLocked("Could not confirm that the remote holdout claim is absent")


def archive_holdout_evidence(
    run: Path, claim: Path, destination: str, *, market: str, manifest_sha256: str, purpose: str = "holdout",
) -> None:
    archive_prefix = destination.rsplit("/", 1)[0]
    claims = f"{archive_prefix}/{purpose}-claims"
    fixed_name = f"v1-{market}-{manifest_sha256}.claim"
    _require_claim_absent(f"{claims}/{fixed_name}")
    _require_claim_absent(f"{destination}/{claim.name}")
    # The unique claim also detects a competing upload after the existence check.
    archive_file(claim, claims, fixed_name)
    archive_file(claim, destination, claim.name)
    for name in ("stage_a.json", "stage_b.json", "pass.json"):
        archive_file(run / name, destination, name)
