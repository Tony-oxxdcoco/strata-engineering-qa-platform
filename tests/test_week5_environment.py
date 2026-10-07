"""Risk-focused tests for isolated Week 5 operations, not engineering answers."""
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import socket
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('week5_environment', ROOT / 'scripts/week5-environment.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


@pytest.fixture
def demo(tmp_path):
    directory = tmp_path / 'independent-week5'
    manager.init_directory(directory)
    return directory


def database(directory):
    """Independent storage fixture; no system outputs are used as expected data."""
    content = b'Explicit synthetic source used for environment recovery tests.'
    sha = hashlib.sha256(content).hexdigest()
    blobs = directory / 'runtime' / 'blobs'
    blobs.mkdir()
    (blobs / sha).write_bytes(content)
    with closing(sqlite3.connect(directory / 'runtime' / 'strata.db')) as c, c:
        c.execute('CREATE TABLE resources(kind TEXT,data TEXT)')
        c.execute('INSERT INTO resources VALUES (?,?)', ('file', json.dumps({'sha256': sha})))
        c.execute('CREATE TABLE sessions(token_hash TEXT)')
        c.execute('INSERT INTO sessions VALUES (?)', ('synthetic-old-session-hash',))
        c.execute('CREATE TABLE sample(value TEXT)')
        c.execute('INSERT INTO sample VALUES (?)', ('before-checkpoint',))
    return sha, content


def test_init_rejects_real_runtime_existing_data_and_symlink_ancestor(tmp_path):
    protected = tmp_path / '.runtime'
    protected.mkdir()
    (protected / 'original.txt').write_text('Preserve this')
    with pytest.raises(manager.EnvironmentError, match='protected'):
        manager.init_directory(protected / 'week5')
    with pytest.raises(manager.EnvironmentError, match='protected'):
        manager.init_directory(tmp_path / '.RUNTIME' / 'week5')
    original = tmp_path / 'unmarked'
    original.mkdir()
    (original / 'strata.db').write_bytes(b'Original data')
    with pytest.raises(manager.EnvironmentError, match='regular Week 5 file'):
        manager.init_directory(original)
    link = tmp_path / 'alias'
    try:
        link.symlink_to(original, target_is_directory=True)
    except OSError:
        pytest.skip('Platform cannot create the symlink safety fixture')
    with pytest.raises(manager.EnvironmentError, match='Symlink'):
        manager.init_directory(link / 'week5')
    assert (original / 'strata.db').read_bytes() == b'Original data'
    assert (protected / 'original.txt').read_text() == 'Preserve this'


def test_init_is_idempotent_but_never_relabels_or_changes_existing_port(demo):
    identity = manager.environment(demo)[1]['identity']
    assert manager.init_directory(demo)['created'] is False
    assert manager.environment(demo)[1]['identity'] == identity
    with pytest.raises(manager.EnvironmentError, match='port differs'):
        manager.init_directory(demo, 4191)
    marker = json.loads((demo / manager.MARKER).read_text())
    marker['synthetic_only'] = False
    (demo / manager.MARKER).write_text(json.dumps(marker))
    with pytest.raises(manager.EnvironmentError, match='marked synthetic'):
        manager.reset(demo)


def test_start_environment_discards_external_integrations_and_account_token(demo, monkeypatch):
    for key in ['STRATA_DATABASE_URL','STRATA_ETABS_URL','STRATA_ETABS_TOKEN','STRATA_OLLAMA_MODEL',
                'STRATA_OLLAMA_URL','STRATA_OCR_ENABLED','STRATA_PUBLIC_ORIGIN','STRATA_ALLOWED_HOSTS',
                'STRATA_BIND','STRATA_SETUP_TOKEN','STRATA_WEEK5_INSTANCE']:
        monkeypatch.setenv(key, 'must-not-inherit')
    monkeypatch.setenv('STRATA_DATA_DIR', '/original/data')
    monkeypatch.delenv('STRATA_WEEK5_SETUP_TOKEN', raising=False)
    env = manager.child_environment(demo)
    assert env['STRATA_DATA_DIR'] == str(demo / 'runtime')
    assert all(key not in env for key in ['STRATA_DATABASE_URL','STRATA_ETABS_TOKEN','STRATA_OLLAMA_MODEL','STRATA_SETUP_TOKEN','STRATA_BIND','STRATA_WEEK5_INSTANCE'])
    monkeypatch.setenv('STRATA_WEEK5_SETUP_TOKEN', 'synthetic-temporary-init-token')
    assert manager.child_environment(demo)['STRATA_SETUP_TOKEN'] == 'synthetic-temporary-init-token'
    assert 'synthetic-temporary-init-token' not in (demo / manager.MARKER).read_text()


def test_start_binds_child_public_instance_to_its_own_service_record(tmp_path,monkeypatch):
    with socket.socket() as available:
        available.bind(('127.0.0.1',0));port=available.getsockname()[1]
    demo=tmp_path/'process-identity';manager.init_directory(demo,port)
    monkeypatch.setenv('STRATA_WEEK5_INSTANCE','inherited-unrelated-service')
    passed=[]
    monkeypatch.setattr(manager.subprocess,'run',lambda *a,**kw:types.SimpleNamespace(stdout='v24.12.0'))
    class CompletedOwnedChild:
        pid=12345
        returncode=0
        def poll(self):return 0
    def child(*a,**kw):passed.append(kw['env']['STRATA_WEEK5_INSTANCE']);return CompletedOwnedChild()
    monkeypatch.setattr(manager.subprocess,'Popen',child)
    assert manager.start(demo)['ok'] is True
    record=manager.read_json(demo/'service.json')
    assert passed==[record['nonce']]
    assert len(record['nonce'])==32 and record['nonce']!='inherited-unrelated-service'
    assert record['identity']==manager.environment(demo)[1]['identity']


def test_active_manager_and_unmanaged_worker_block_reset_restore_checkpoint(demo):
    database(demo)
    manager.checkpoint(demo, 'prepared')
    with manager.control_lock(demo):
        for operation in [lambda:manager.reset(demo),lambda:manager.restore(demo,'prepared'),lambda:manager.checkpoint(demo,'another')]:
            with pytest.raises(manager.EnvironmentError, match='active'):
                operation()
    with (demo / 'runtime' / 'worker.lock').open('a+b') as stream:
        manager.locking.lock_worker(stream)
        try:
            assert manager.status(demo)['running'] is True
            assert manager.status(demo)['manager_running'] is False
            with pytest.raises(manager.EnvironmentError, match='worker still'):
                manager.reset(demo)
            with pytest.raises(manager.EnvironmentError, match='worker still'):
                manager.restore(demo,'prepared')
        finally:
            manager.locking.unlock_worker(stream)
    assert not list((demo / 'archive').iterdir())


def test_checkpoint_reset_and_restore_preserve_originals_and_revoke_sessions(demo):
    sha, content = database(demo)
    manager.checkpoint(demo, 'prepared')
    with pytest.raises(manager.backup.BackupError, match='already exists'):
        manager.checkpoint(demo, 'prepared')
    reset = manager.reset(demo)
    assert not (demo / 'runtime' / 'strata.db').exists()
    assert (Path(reset['archived']) / 'strata.db').is_file()
    restored = manager.restore(demo, 'prepared')
    assert restored['sessions_invalidated'] == 1
    assert (demo / 'runtime' / 'blobs' / sha).read_bytes() == content
    with closing(sqlite3.connect(demo / 'runtime' / 'strata.db')) as c, c:
        assert c.execute('SELECT value FROM sample').fetchone()[0] == 'before-checkpoint'
        assert c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
    with closing(sqlite3.connect(Path(reset['archived']) / 'strata.db')) as c, c:
        assert c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
    assert len(list((demo / 'archive').iterdir())) == 2


def test_corrupt_checkpoint_and_traversal_do_not_archive_or_modify_runtime(demo):
    database(demo)
    manager.checkpoint(demo, 'prepared')
    original = (demo / 'runtime' / 'strata.db').read_bytes()
    for name in ['../prepared','prepared/next','.','']:
        with pytest.raises(manager.EnvironmentError, match='Checkpoint name'):
            manager.restore(demo, name)
    manifest = demo / 'checkpoints' / 'prepared' / 'manifest.json'
    value = json.loads(manifest.read_text());value['database']['sha256'] = '0' * 64
    manifest.write_text(json.dumps(value))
    with pytest.raises(manager.backup.BackupError, match='checksum'):
        manager.restore(demo, 'prepared')
    assert (demo / 'runtime' / 'strata.db').read_bytes() == original
    assert not list((demo / 'archive').iterdir())


def test_nested_runtime_aliases_and_hardlinks_cannot_reach_original_files(demo, tmp_path):
    original = tmp_path / 'private-database'
    original.write_bytes(b'Original private contents')
    linked = demo / 'runtime' / 'strata.db'
    try:
        os.link(original, linked)
    except OSError:
        pytest.skip('Platform cannot create the hardlink safety fixture')
    with pytest.raises(manager.EnvironmentError, match='unlinked regular'):
        manager.reset(demo)
    assert original.read_bytes() == b'Original private contents'
    linked.unlink()
    linked.symlink_to(original)
    with pytest.raises(manager.EnvironmentError, match='unlinked regular'):
        manager.reset(demo)
    linked.unlink()
    (demo / 'runtime' / 'blobs').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(manager.EnvironmentError, match='Unsafe runtime blobs'):
        manager.reset(demo)


def test_failed_switch_restores_prior_runtime_and_retains_staged_recovery(demo, monkeypatch):
    database(demo);manager.checkpoint(demo,'prepared')
    original = (demo / 'runtime' / 'strata.db').read_bytes()
    replace = Path.replace
    def fail_staged(self, target):
        if self.name.startswith('restore-'):
            raise OSError('Synthetic switch fault')
        return replace(self, target)
    monkeypatch.setattr(Path,'replace',fail_staged)
    with pytest.raises(OSError, match='switch fault'):
        manager.restore(demo,'prepared')
    assert (demo / 'runtime' / 'strata.db').read_bytes() == original
    assert len(list(demo.glob('restore-*'))) == 1


def test_simulated_linux_without_vision_keeps_basic_api_available(demo, monkeypatch):
    """Host-side simulation only; this is not a Linux container runtime test."""
    import sys
    sys.path.insert(0,str(ROOT/'backend'))
    from fastapi.testclient import TestClient
    from strata.app import create_app
    from strata import ocr
    monkeypatch.setattr(ocr.platform,'system',lambda:'Linux')
    monkeypatch.setattr(ocr.shutil,'which',lambda name:None if name in ['swift','pdftoppm'] else '/synthetic-unrelated-tool')
    monkeypatch.setenv('STRATA_OCR_ENABLED','1')
    monkeypatch.delenv('STRATA_DATABASE_URL',raising=False)
    with TestClient(create_app(data_dir=demo/'runtime',testing=True,worker=False)) as client:
        health=client.get('/api/v1/health');assert health.status_code==200 and health.json()['status']=='ok'
        result=client.post('/api/v1/auth/bootstrap',json={'username':'synthetic-linux-probe','password':'synthetic-linux-probe-password'})
        assert result.status_code==200
        client.headers['Authorization']='Bearer '+result.json()['token']
        capabilities=client.get('/api/v1/ocr').json()
        assert capabilities['provider'] is None and capabilities['available'] is False
        with pytest.raises(ValueError,match='requires macOS'):
            ocr.recognize(b'untrusted-synthetic-input',1)
        assert client.get('/api/v1/projects').status_code==200
