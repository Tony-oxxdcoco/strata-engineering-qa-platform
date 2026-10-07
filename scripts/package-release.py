#!/usr/bin/env python3
"""Build a source-only teammate ZIP. Never include local accounts or documents."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {'backend', 'web', 'dist', 'scripts', 'tests', 'docs', '.github', 'examples'}
FILES = {'pytest.ini', 'package.json', 'README.md', 'TEAM_START_HERE.md', 'PROJECT_JOURNAL.md', 'CUSTOMER_REQUIREMENTS.md', 'VALIDATION.md', 'ITERATION_PLAN.md', 'TASK_QUEUE.md', 'Dockerfile', 'compose.yaml', 'compose.week5.yaml', '.env.example', '.dockerignore', '.gitignore', '.gitattributes', 'Setup STRATA.cmd', 'Start STRATA.cmd', 'Setup STRATA.command', 'Start STRATA.command', 'CLIENT_ADAPTATION.md', 'NEXT_SESSION.md'}
RELEASE = 'STRATA-' + json.loads((ROOT / 'package.json').read_text())['version']
EXCLUDED = {'__pycache__', '.pytest_cache', '.DS_Store', '.venv', '.runtime', 'output', '.git', 'node_modules'}


def source_paths():
    """Only reviewed Git index paths, or the original packaged source manifest.

    Untracked notes/uploads under otherwise permitted directories are private by
    default. New source files must be staged before building a repository release.
    An extracted teammate ZIP can be repackaged using its existing manifest.
    """
    try:
        result = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'],
                                capture_output=True, check=True, timeout=10)
        return [Path(name.decode('utf-8')) for name in result.stdout.split(b'\0') if name]
    except (OSError, subprocess.SubprocessError):
        manifest = ROOT / 'release-manifest.json'
        if not manifest.is_file() or manifest.is_symlink():
            raise ValueError('Release requires a Git source index or a packaged release-manifest.json')
        value = json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or not isinstance(value.get('files'), dict):
            raise ValueError('Invalid packaged source manifest')
        return [Path(name) for name in value['files']]


def validate_env_example(path):
    """Never publish a populated setup token or other credential in the example."""
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not key or ('TOKEN' in key or 'PASSWORD' in key or 'SECRET' in key or 'KEY' in key) and value.strip() not in {'', '\"\"', "''"}:
            raise ValueError('Environment example must contain only blank credential fields')


def private_release_path(rel):
    """Defence against accidentally staged local secrets/logs inside docs."""
    return any(part.lower() in {'private', 'secrets'}
               or part.lower().startswith(('private-', 'private.'))
               or '.private.' in part.lower() or part.lower().endswith('.private')
               for part in rel.parts)


def build(destination):
    selected = []
    for rel in sorted(source_paths()):
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            raise ValueError('Release source path must remain inside its source directory')
        path = ROOT / rel
        if (not path.is_file() or path.is_symlink() or private_release_path(rel) or set(rel.parts) & EXCLUDED
                or (path.name.startswith('.env') and str(rel) != '.env.example')
                or path.suffix.lower() in {'.pyc', '.log', '.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}):
            continue
        if path.resolve() != ROOT.resolve() / rel:
            raise ValueError('Release source traverses or redirects through a symbolic-link directory')
        if rel.parts[0] not in DIRECTORIES and str(rel) not in FILES:
            continue
        if str(rel) == '.env.example':
            validate_env_example(path)
        selected.append((path, rel.as_posix()))
    manifest = {'release': RELEASE, 'scope': 'reviewed source and synthetic fixtures only; untracked files, accounts, project database, original customer files, model weights and proposal/report documents excluded', 'files': {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in selected}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, name in selected:
            archive.write(path, RELEASE + '/' + name)
        archive.writestr(RELEASE + '/release-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name, expected in manifest['files'].items():
            assert hashlib.sha256(archive.read(RELEASE + '/' + name)).hexdigest() == expected
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.sha256').write_text(sha + '  ' + destination.name + '\n', encoding='utf-8')
    print(json.dumps({'path': str(destination), 'source_files': len(selected), 'bytes': destination.stat().st_size, 'sha256': sha}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / f'output/releases/{RELEASE}-team.zip')
    build(parser.parse_args().output.resolve())
