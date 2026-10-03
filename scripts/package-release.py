#!/usr/bin/env python3
"""Build a source-only teammate ZIP. Never include local accounts or documents."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {'backend', 'web', 'dist', 'scripts', 'tests', 'docs', '.github'}
FILES = {'package.json', 'README.md', 'TEAM_START_HERE.md', 'PROJECT_JOURNAL.md', 'CUSTOMER_REQUIREMENTS.md', 'VALIDATION.md', 'ITERATION_PLAN.md', 'Dockerfile', 'compose.yaml', '.dockerignore', '.gitignore', '.gitattributes', 'Setup STRATA.cmd', 'Start STRATA.cmd', 'Setup STRATA.command', 'Start STRATA.command'}
EXCLUDED = {'__pycache__', '.pytest_cache', '.DS_Store', '.venv', '.runtime', 'output', '.git', 'node_modules'}


def build(destination):
    selected = []
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if (not path.is_file() or path.is_symlink() or set(rel.parts) & EXCLUDED
                or path.name.startswith('.env')
                or path.suffix.lower() in {'.pyc', '.log', '.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}):
            continue
        if rel.parts[0] not in DIRECTORIES and str(rel) not in FILES:
            continue
        selected.append((path, rel.as_posix()))
    manifest = {'release': 'STRATA-1.0.0', 'scope': 'source and synthetic fixtures only; no accounts, project database, original customer files, model weights or proposal/report documents', 'files': {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in selected}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, name in selected:
            archive.write(path, 'STRATA-1.0.0/' + name)
        archive.writestr('STRATA-1.0.0/release-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name, expected in manifest['files'].items():
            assert hashlib.sha256(archive.read('STRATA-1.0.0/' + name)).hexdigest() == expected
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.sha256').write_text(sha + '  ' + destination.name + '\n', encoding='utf-8')
    print(json.dumps({'path': str(destination), 'source_files': len(selected), 'bytes': destination.stat().st_size, 'sha256': sha}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'output/releases/STRATA-1.0.0-team.zip')
    build(parser.parse_args().output.resolve())
