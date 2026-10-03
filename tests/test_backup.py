import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location("strata_backup", Path(__file__).resolve().parents[1] / "scripts/backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "live"
    (root / "blobs").mkdir(parents=True)
    content = b"original source\n"
    sha = backup.hashlib.sha256(content).hexdigest()
    (root / "blobs" / sha).write_bytes(content)
    with sqlite3.connect(root / "strata.db") as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE resources(kind TEXT, data TEXT)")
        db.execute("CREATE TABLE sessions(token_hash TEXT)")
        db.execute("INSERT INTO resources VALUES (?,?)", ("file", json.dumps({"sha256": sha})))
        db.execute("INSERT INTO sessions VALUES ('revocable-token-hash')")
        db.commit()
    return root, sha


def test_backup_restore_preserves_files_and_revokes_sessions(source, tmp_path):
    root, sha = source
    result = backup.create_backup(root, tmp_path / "backup")
    assert result["blob_count"] == 1
    assert backup.verify_backup(tmp_path / "backup")["ok"]
    restored = backup.restore_backup(tmp_path / "backup", tmp_path / "restored")
    assert restored["sessions_invalidated"] == 1
    assert (tmp_path / "restored/blobs" / sha).read_bytes() == (root / "blobs" / sha).read_bytes()
    with sqlite3.connect(tmp_path / "restored/strata.db") as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 1
    with sqlite3.connect(root / "strata.db") as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_backup_never_overwrites_destination(source, tmp_path):
    root, _ = source
    target = tmp_path / "exists"
    target.mkdir()
    (target / "keep").write_text("keep")
    with pytest.raises(backup.BackupError): backup.create_backup(root, target)
    assert (target / "keep").read_text() == "keep"


def test_corrupt_source_prevents_completed_backup(source, tmp_path):
    root, sha = source
    (root / "blobs" / sha).write_bytes(b"corrupt")
    with pytest.raises(backup.BackupError): backup.create_backup(root, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_corrupt_backup_and_extra_files_rejected(source, tmp_path):
    root, sha = source
    target = tmp_path / "backup"
    backup.create_backup(root, target)
    (target / "extra").write_text("not part of manifest")
    with pytest.raises(backup.BackupError): backup.verify_backup(target)
    (target / "extra").unlink()
    (target / "blobs" / sha).write_bytes(b"changed")
    with pytest.raises(backup.BackupError): backup.restore_backup(target, tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_nested_or_symlink_destination_rejected(source, tmp_path):
    root, _ = source
    with pytest.raises(backup.BackupError): backup.create_backup(root, root / "backup")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(backup.BackupError): backup.create_backup(root, alias)
