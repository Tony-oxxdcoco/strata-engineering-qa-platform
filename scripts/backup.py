#!/usr/bin/env python3
"""Consistent SQLite + referenced-blob backup. Standard library; no server import.

create and restore always require a new destination directory. A manifest binds
file bytes for corruption checks, not an authenticated anti-tamper signature.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import time

FORMAT = "strata-sqlite-backup-1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
ROOT = Path(__file__).resolve().parents[1]


class BackupError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def regular(path):
    require(path.exists() and not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), f"Expected a regular file: {path.name}")


def checksum(path):
    regular(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def read_database(path):
    regular(path)
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)


def required_blobs(database):
    with closing(read_database(database)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchall()
        require(result == [("ok",)], "SQLite integrity_check failed")
        blobs = set()
        for (encoded,) in connection.execute("SELECT data FROM resources WHERE kind = 'file'"):
            value = json.loads(encoded)
            sha = value.get("sha256")
            require(isinstance(sha, str) and HASH.fullmatch(sha), "Invalid blob hash in file resource")
            blobs.add(sha)
        return sorted(blobs)


def new_destination(destination, protected):
    destination = Path(destination).expanduser().absolute()
    require(not destination.exists() and not destination.is_symlink(), "Destination already exists; nothing was overwritten")
    resolved = destination.resolve()
    require(resolved != protected and protected not in resolved.parents, "Destination must be outside the source directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)  # Atomic reservation; exist_ok is deliberately false.
    return destination.resolve()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)


def create_backup(data_dir, destination):
    source = Path(data_dir).expanduser().resolve()
    database = source / "strata.db"
    regular(database)
    require((source / "blobs").is_dir() and not (source / "blobs").is_symlink(), "Source blobs directory is unavailable")
    target = new_destination(destination, source)
    try:
        started = time.monotonic()
        def progress(status, remaining, total):
            require(time.monotonic() - started < 60, "SQLite backup exceeded 60 seconds; retry during a quiet period")
        with closing(read_database(database)) as incoming, closing(sqlite3.connect(target / "strata.db")) as outgoing:
            incoming.backup(outgoing, pages=256, progress=progress, sleep=0.05)
            # A self-contained backup must not depend on separate WAL/SHM files.
            outgoing.execute("PRAGMA journal_mode=DELETE")
        (target / "strata.db").chmod(0o600)
        (target / "blobs").mkdir(mode=0o700)
        blobs = []
        # Derive the set from the copied database, not a moving live directory.
        for sha in required_blobs(target / "strata.db"):
            origin = source / "blobs" / sha
            regular(origin)
            output = target / "blobs" / sha
            shutil.copyfile(origin, output)
            output.chmod(0o600)
            require(checksum(output) == sha, "Referenced source blob is corrupt; backup was not completed")
            blobs.append({"sha256": sha, "size_bytes": output.stat().st_size})
        manifest = {"format": FORMAT, "created_at": timestamp(),
            "database": {"name": "strata.db", "sha256": checksum(target / "strata.db"), "size_bytes": (target / "strata.db").stat().st_size},
            "blobs": blobs, "blob_count": len(blobs),
            "scope": "Whole SQLite installation and exactly the original files referenced by this database snapshot; no environment secrets or model weights."}
        write_json(target / "manifest.json", manifest)
        verify_backup(target)
        return {"ok": True, "backup": str(target), "database_sha256": manifest["database"]["sha256"], "blob_count": len(blobs)}
    except Exception:
        shutil.rmtree(target)
        raise


def verify_backup(directory):
    root = Path(directory).expanduser().resolve()
    regular(root / "manifest.json")
    require((root / "manifest.json").stat().st_size <= 10 * 1024 * 1024, "Backup manifest exceeds size limit")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(isinstance(manifest, dict) and manifest.get("format") == FORMAT, "Unsupported backup format")
    database = manifest.get("database")
    require(isinstance(database, dict) and database.get("name") == "strata.db" and isinstance(database.get("sha256"), str) and HASH.fullmatch(database["sha256"]), "Invalid database manifest")
    require(type(database.get("size_bytes")) is int and database["size_bytes"] > 0, "Invalid database size")
    file = root / "strata.db"
    require(checksum(file) == database["sha256"] and file.stat().st_size == database["size_bytes"], "Backup database checksum mismatch")
    blobs = manifest.get("blobs")
    require(isinstance(blobs, list) and len(blobs) == manifest.get("blob_count"), "Invalid blob manifest")
    require((root / "blobs").is_dir() and not (root / "blobs").is_symlink(), "Invalid backup blobs directory")
    hashes = []
    for record in blobs:
        require(isinstance(record, dict) and isinstance(record.get("sha256"), str) and HASH.fullmatch(record["sha256"]), "Invalid blob path/hash")
        sha = record["sha256"]
        require(sha not in hashes and type(record.get("size_bytes")) is int and record["size_bytes"] >= 0, "Invalid or duplicate blob record")
        file = root / "blobs" / sha
        require(checksum(file) == sha and file.stat().st_size == record["size_bytes"], "Backup blob checksum mismatch")
        hashes.append(sha)
    require(sorted(hashes) == required_blobs(root / "strata.db"), "Backup manifest does not match database file references")
    require({p.name for p in (root / "blobs").iterdir()} == set(hashes), "Unexpected files in backup blobs directory")
    require({p.name for p in root.iterdir()} == {"strata.db", "blobs", "manifest.json"}, "Unexpected files in backup directory")
    return {"ok": True, "backup": str(root), "database_sha256": database["sha256"], "blob_count": len(hashes)}


def restore_backup(directory, destination):
    source = Path(directory).expanduser().resolve()
    verified = verify_backup(source)
    target = new_destination(destination, source)
    try:
        for name in ("strata.db", "manifest.json"):
            shutil.copyfile(source / name, target / name)
            (target / name).chmod(0o600)
        shutil.copytree(source / "blobs", target / "blobs")
        for file in (target / "blobs").iterdir():
            file.chmod(0o600)
        (target / "blobs").chmod(0o700)
        verify_backup(target)  # Verify copied bytes before changing session state.
        with closing(sqlite3.connect(target / "strata.db")) as connection:
            revoked = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            connection.execute("DELETE FROM sessions")
            connection.commit()
        receipt = {"restored_at": timestamp(), "backup_database_sha256": verified["database_sha256"],
            "restored_database_sha256": checksum(target / "strata.db"), "sessions_invalidated": revoked,
            "note": "Database differs from backup only through deliberate login-session invalidation. Review queued/recoverable jobs before starting the service."}
        (target / "manifest.json").unlink()
        write_json(target / "restore-receipt.json", receipt)
        return {"ok": True, "data_dir": str(target), "blob_count": verified["blob_count"], "sessions_invalidated": revoked}
    except Exception:
        shutil.rmtree(target)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Back up default SQLite storage into a new directory")
    create.add_argument("--data-dir", default=os.environ.get("STRATA_DATA_DIR", str(ROOT / ".runtime")))
    create.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="Verify checksums, database integrity and required blobs")
    verify.add_argument("backup")
    restore = commands.add_parser("restore", help="Restore into a new directory and invalidate old sessions")
    restore.add_argument("backup")
    restore.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            require(not os.environ.get("STRATA_DATABASE_URL"), "Custom STRATA_DATABASE_URL is set; this script supports only the default strata.db SQLite layout")
            result = create_backup(args.data_dir, args.output)
        elif args.command == "verify":
            result = verify_backup(args.backup)
        else:
            result = restore_backup(args.backup, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (BackupError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
