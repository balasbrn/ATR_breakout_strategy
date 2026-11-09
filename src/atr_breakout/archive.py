"""Upload immutable run artifacts and verify the stored object bytes."""

import hashlib
from pathlib import Path
import re
import subprocess


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


def archive_holdout_evidence(run: Path, claim: Path, destination: str) -> None:
    # Write the unique claim first so an existing remote claim blocks any retry.
    archive_file(claim, destination, claim.name)
    for name in ("stage_a.json", "stage_b.json", "pass.json"):
        archive_file(run / name, destination, name)
