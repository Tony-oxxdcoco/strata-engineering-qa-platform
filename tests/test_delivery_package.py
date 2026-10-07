"""Release boundary tests using tiny Git fixtures, never the live runtime."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

spec = importlib.util.spec_from_file_location("release_builder", Path(__file__).resolve().parents[1] / "scripts/package-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init")
    for directory in ("web", "docs", "examples", ".runtime", "scripts"):
        (root / directory).mkdir()
    (root / "package.json").write_text('{"version":"test"}')
    (root / "web/app.js").write_text("// reviewed source\n")
    (root / "docs/public.md").write_text("Public maintenance guide\n")
    (root / ".env.example").write_text("STRATA_SETUP_TOKEN=\nSTRATA_PORT=4180\n")
    (root / ".runtime/strata.db").write_bytes(b"private account database")
    (root / ".env").write_text("STRATA_SETUP_TOKEN=private\n")
    git(root, "add", "package.json", "web/app.js", "docs/public.md", ".env.example", ".runtime/strata.db", ".env")
    (root / "docs/untracked-private-note.md").write_text("private meeting notes")
    (root / "examples/untracked-customer-file.csv").write_text("private engineering data")
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(release, "RELEASE", "STRATA-test")
    return root


def test_only_staged_source_and_blank_example_are_released(source, tmp_path):
    destination = tmp_path / "delivery.zip"
    release.build(destination)
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "STRATA-test/.env.example" in names
        assert "STRATA-test/docs/public.md" in names
        assert not any("private" in name or ".runtime" in name or name.endswith("/.env") for name in names)
        manifest = json.loads(archive.read("STRATA-test/release-manifest.json"))
        assert len(manifest["files"]) == 4
    assert destination.with_suffix(".sha256").exists()


def test_populated_env_example_is_refused(source, tmp_path):
    (source / ".env.example").write_text("STRATA_SETUP_TOKEN=do-not-distribute\n")
    with pytest.raises(ValueError, match="blank credential"):
        release.build(tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


def test_no_git_or_original_manifest_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / "unknown-source"
    root.mkdir()
    monkeypatch.setattr(release, "ROOT", root)
    with pytest.raises(ValueError, match="Git source index"):
        release.build(tmp_path / "bad.zip")


def test_original_source_manifest_can_repackage_without_git(source, tmp_path, monkeypatch):
    destination = tmp_path / "delivery.zip"
    release.build(destination)
    with zipfile.ZipFile(destination) as archive:
        archive.extractall(tmp_path / "unpacked")
    root = tmp_path / "unpacked/STRATA-test"
    (root / "docs/untracked-private.md").write_text("local team note")
    monkeypatch.setattr(release, "ROOT", root)
    release.build(tmp_path / "repacked.zip")
    with zipfile.ZipFile(tmp_path / "repacked.zip") as archive:
        assert "STRATA-test/docs/untracked-private.md" not in archive.namelist()


def test_manifest_cannot_escape_source_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "release-manifest.json").write_text(json.dumps({"files": {"../private.md": "hash"}}))
    monkeypatch.setattr(release, "ROOT", root)
    with pytest.raises(ValueError, match="inside"):
        release.build(tmp_path / "bad.zip")
