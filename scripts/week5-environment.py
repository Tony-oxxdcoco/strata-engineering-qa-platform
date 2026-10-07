#!/usr/bin/env python3
"""Manage one marked, isolated Week 5 demo; never use the installation .runtime.

The supervisor stops only a child it created, using an owned control nonce.
Checkpoints and archived runtimes are private: they contain account hashes.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'output' / 'week5-environment'
FORMAT = 'strata-week5-environment/1'
MARKER = '.strata-week5-environment.json'
NAME = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z')


class EnvironmentError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EnvironmentError(message)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load_module('strata_week5_backup', ROOT / 'scripts' / 'backup.py')
locking = load_module('strata_week5_locking', ROOT / 'backend' / 'strata' / 'locking.py')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def safe_path(value):
    path = Path(value).expanduser().absolute()
    require(not any(part.casefold() == '.runtime' for part in path.parts), 'The installation .runtime is protected; choose a new Week 5 directory')
    require(not any(p.is_symlink() for p in [path, *path.parents]), 'Symlink paths cannot be managed')
    require(path.resolve() not in [ROOT, *ROOT.parents], 'Repository and parent directories cannot be demo environments')
    return path


def regular(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1, 'Expected an unlinked regular Week 5 file: ' + path.name)


def write_json(path, value):
    require(not path.is_symlink(), 'Symlink control files are rejected')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)


def read_json(path):
    regular(path)
    require(path.stat().st_size < 64_000, 'Control file exceeds its limit')
    return json.loads(path.read_text(encoding='utf-8'))


def environment(value):
    directory = safe_path(value)
    metadata = read_json(directory / MARKER)
    require(metadata.get('format') == FORMAT and metadata.get('synthetic_only') is True,
            'This is not a marked synthetic Week 5 environment')
    require(isinstance(metadata.get('identity'), str) and re.fullmatch(r'[0-9a-f]{32}', metadata['identity']), 'Invalid environment identity')
    require(type(metadata.get('port')) is int and 1024 <= metadata['port'] <= 65535, 'Invalid environment port')
    for name in ['runtime', 'checkpoints', 'archive']:
        path = directory / name
        require(path.is_dir() and not path.is_symlink(), 'Missing or unsafe managed directory: ' + name)
    runtime = directory / 'runtime'
    for name in ['strata.db', 'strata.db-wal', 'strata.db-shm', 'worker.lock']:
        if (runtime / name).exists() or (runtime / name).is_symlink(): regular(runtime / name)
    blobs = runtime / 'blobs'
    if blobs.exists() or blobs.is_symlink():
        require(blobs.is_dir() and not blobs.is_symlink(), 'Unsafe runtime blobs directory')
        for blob in blobs.iterdir(): regular(blob)
    return directory, metadata


@contextmanager
def control_lock(directory):
    path = directory / 'environment.lock'
    require(not path.is_symlink(), 'Symlink lock files are rejected')
    with path.open('a+b') as stream:
        try:
            locking.lock_worker(stream)
        except OSError as error:
            raise EnvironmentError('Week 5 service or another environment operation is active; stop it first') from error
        try:
            yield
        finally:
            locking.unlock_worker(stream)


def lock_available(directory):
    try:
        with control_lock(directory):
            return True
    except EnvironmentError:
        return False


def require_worker_stopped(directory):
    """Also reject a core app started outside this manager on the same runtime."""
    path = directory / 'runtime' / 'worker.lock'
    require(not path.is_symlink(), 'Symlink worker locks are rejected')
    if path.exists():
        with path.open('a+b') as stream:
            try:
                locking.lock_worker(stream)
            except OSError as error:
                raise EnvironmentError('A worker still uses the Week 5 runtime; stop that service before recovery') from error
            locking.unlock_worker(stream)


def init_directory(value, port=4190):
    directory = safe_path(value)
    require(1024 <= port <= 65535, 'Port must be 1024–65535')
    if directory.exists():
        _, metadata = environment(directory)
        require(metadata['port'] == port, 'Existing environment port differs; its configuration was not changed')
        return {'ok': True, 'created': False, 'directory': str(directory), 'data_dir': str(directory / 'runtime'), 'port': port}
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700)
    for name in ['runtime', 'checkpoints', 'archive']:
        (directory / name).mkdir(mode=0o700)
    write_json(directory / MARKER, {'format': FORMAT, 'identity': uuid.uuid4().hex, 'synthetic_only': True,
                                    'created_at': timestamp(), 'port': port, 'scope': 'Week 5 synthetic demo only; not a customer installation'})
    return {'ok': True, 'created': True, 'directory': str(directory), 'data_dir': str(directory / 'runtime'), 'port': port}


def child_environment(directory):
    env = dict(os.environ)
    # Never inherit a real database, remote connector, model or public bind.
    for key in ['STRATA_DATABASE_URL', 'STRATA_ETABS_URL', 'STRATA_ETABS_TOKEN', 'STRATA_OLLAMA_MODEL',
                'STRATA_OLLAMA_URL', 'STRATA_OCR_ENABLED', 'STRATA_PUBLIC_ORIGIN', 'STRATA_ALLOWED_HOSTS',
                'STRATA_BIND', 'STRATA_SETUP_TOKEN', 'STRATA_WEEK5_INSTANCE']:
        env.pop(key, None)
    env.update({'STRATA_DATA_DIR': str(directory / 'runtime'), 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'})
    if os.environ.get('STRATA_WEEK5_SETUP_TOKEN'):
        env['STRATA_SETUP_TOKEN'] = os.environ['STRATA_WEEK5_SETUP_TOKEN']
    return env


def start(value, port=None, bind='127.0.0.1'):
    directory, metadata = environment(value)
    port = port or metadata['port']
    require(port == metadata['port'], 'Start port must match init; initialize a different isolated directory for another port')
    require(bind == '127.0.0.1' or bind == '0.0.0.0' and os.environ.get('STRATA_WEEK5_CONTAINER') == '1',
            'Only loopback is allowed; 0.0.0.0 requires the dedicated Week 5 container configuration')
    require(sys.version_info[:2] == (3, 12), 'Use the installed Python 3.12 virtual environment')
    env = child_environment(directory)
    node = env.get('STRATA_NODE', 'node')
    try:
        checked = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=5, check=True)
        version = tuple(int(n) for n in checked.stdout.strip().lstrip('v').split('.')[:2])
        require(version >= (20, 11), 'Node 20.11 or later is required')
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise EnvironmentError('Node is unavailable; set STRATA_NODE to your installed Node executable') from error
    with control_lock(directory):
        require_worker_stopped(directory)
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError as error:
                raise EnvironmentError('Demo port is already in use; no existing service was stopped') from error
        nonce = uuid.uuid4().hex
        # Public process identity for the prepared-data client. It is not a
        # credential and does not grant access. Never reuse an inherited value.
        env['STRATA_WEEK5_INSTANCE'] = nonce
        state = {'identity': metadata['identity'], 'nonce': nonce, 'port': port, 'state': 'STARTING', 'started_at': timestamp()}
        request_path = directory / 'stop-request.json'
        require(not request_path.is_symlink(), 'Symlink stop request is rejected')
        request_path.unlink(missing_ok=True)
        command = [sys.executable, '-m', 'uvicorn', 'strata.app:create_app', '--factory', '--host', bind,
                   '--port', str(port), '--workers', '1', '--no-proxy-headers']
        child = subprocess.Popen(command, cwd=ROOT / 'backend', env=env)
        state.update({'child_pid': child.pid, 'state': 'RUNNING'})
        write_json(directory / 'service.json', state)
        print(json.dumps({'ok': True, 'url': f'http://127.0.0.1:{port}', 'synthetic_only': True, 'model': 'disabled', 'data_dir': str(directory / 'runtime')}, ensure_ascii=False), flush=True)
        interrupted = False
        def stop_signal(*_):
            nonlocal interrupted
            interrupted = True
        previous = {sig: signal.signal(sig, stop_signal) for sig in [signal.SIGINT, signal.SIGTERM]}
        try:
            while child.poll() is None:
                should_stop = interrupted
                if request_path.exists():
                    request = read_json(request_path)
                    should_stop = should_stop or (request.get('identity') == metadata['identity'] and request.get('nonce') == nonce)
                if should_stop:
                    child.terminate()
                    try:
                        child.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
                    break
                time.sleep(.2)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            state.update({'state': 'STOPPED', 'stopped_at': timestamp(), 'return_code': child.returncode})
            write_json(directory / 'service.json', state)
            request_path.unlink(missing_ok=True)
        return {'ok': child.returncode in [0, -signal.SIGTERM], 'state': 'STOPPED', 'return_code': child.returncode}


def status(value):
    directory, metadata = environment(value)
    manager_running = not lock_available(directory)
    worker_running = False
    try:
        require_worker_stopped(directory)
    except EnvironmentError:
        worker_running = True
    return {'ok': True, 'synthetic_only': True, 'running': manager_running or worker_running,
            'manager_running': manager_running, 'worker_running': worker_running, 'url': f'http://127.0.0.1:{metadata["port"]}', 'data_dir': str(directory / 'runtime'),
            'database_exists': (directory / 'runtime' / 'strata.db').is_file(),
            'checkpoints': sorted(p.name for p in (directory / 'checkpoints').iterdir() if p.is_dir() and not p.is_symlink())}


def stop(value):
    directory, metadata = environment(value)
    if lock_available(directory):
        require_worker_stopped(directory)
        return {'ok': True, 'state': 'STOPPED', 'already_stopped': True}
    state = read_json(directory / 'service.json')
    require(state.get('identity') == metadata['identity'] and state.get('state') == 'RUNNING', 'No owned supervisor to stop; never kill a process by an unverified PID')
    write_json(directory / 'stop-request.json', {'identity': metadata['identity'], 'nonce': state['nonce']})
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if lock_available(directory):
            require_worker_stopped(directory)
            return {'ok': True, 'state': 'STOPPED'}
        time.sleep(.2)
    raise EnvironmentError('Stop timed out; do not reset or restore until the foreground supervisor and worker have exited')


def valid_name(name):
    require(isinstance(name, str) and NAME.fullmatch(name), 'Checkpoint name must use 1–64 letters, digits, underscores or hyphens')
    return name


def checkpoint(value, name):
    directory, metadata = environment(value)
    with control_lock(directory):
        require_worker_stopped(directory)
        target = directory / 'checkpoints' / valid_name(name)
        result = backup.create_backup(directory / 'runtime', target)
        return {**result, 'synthetic_only': True, 'name': name}


def archive_runtime(directory):
    target = directory / 'archive' / ('runtime-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
    (directory / 'runtime').replace(target)
    return target


def reset(value):
    directory, _ = environment(value)
    with control_lock(directory):
        require_worker_stopped(directory)
        archived = archive_runtime(directory)
        (directory / 'runtime').mkdir(mode=0o700)
        return {'ok': True, 'synthetic_only': True, 'archived': str(archived), 'data_dir': str(directory / 'runtime'), 'accounts': 'New runtime: create your own account again'}


def restore(value, name):
    directory, _ = environment(value)
    with control_lock(directory):
        require_worker_stopped(directory)
        source = directory / 'checkpoints' / valid_name(name)
        require(source.is_dir() and not source.is_symlink(), 'Checkpoint must belong to this marked environment')
        staged = directory / ('restore-' + uuid.uuid4().hex)
        result = backup.restore_backup(source, staged)
        archived = None
        try:
            archived = archive_runtime(directory)
            staged.replace(directory / 'runtime')
        except Exception:
            if archived is not None and not (directory / 'runtime').exists():
                archived.replace(directory / 'runtime')
            raise
        return {**result, 'data_dir': str(directory / 'runtime'), 'synthetic_only': True, 'archived': str(archived), 'name': name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ['init', 'start', 'stop', 'status', 'checkpoint', 'reset', 'restore']:
        sub = subs.add_parser(name)
        sub.add_argument('--directory', type=Path, default=DEFAULT)
        if name == 'init': sub.add_argument('--port', type=int, default=4190)
        if name == 'start':
            sub.add_argument('--port', type=int)
            sub.add_argument('--bind', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1')
        if name in ['checkpoint', 'restore']: sub.add_argument('--name', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init': result = init_directory(args.directory, args.port)
        elif args.command == 'start': result = start(args.directory, args.port, args.bind)
        elif args.command in ['checkpoint', 'restore']: result = globals()[args.command](args.directory, args.name)
        else: result = globals()[args.command](args.directory)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result.get('ok') else 1
    except (EnvironmentError, backup.BackupError, OSError, ValueError, KeyError) as error:
        print('Week 5 environment operation failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
