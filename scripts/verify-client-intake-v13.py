#!/usr/bin/env python3
"""New synthetic intake through authenticated APIs, without seed()/generated truth.

Default: isolated temporary SQLite using real FastAPI routes and deterministic tools.
--url: a real loopback HTTP server/worker and a new synthetic project in its database.
Expected answers are loaded from the independently frozen oracle, never the checker.
"""
from __future__ import annotations
import argparse
import base64
import copy
from contextlib import contextmanager
import os
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from strata.app import create_app
from strata.workflow import TOOL_FINGERPRINT
from strata.data_tools import UNITS
from fastapi.testclient import TestClient


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(content):
    return hashlib.sha256(content).hexdigest()


def assert_that(condition, message):
    if not condition:
        raise AssertionError(message)


@contextmanager
def isolated_database_environment():
    # A caller's deployment settings must not redirect temporary verification or
    # enable optional services. Keep STRATA_NODE: it selects the installed local
    # executable needed by the real deterministic tool, not a remote provider.
    keys = ('STRATA_DATA_DIR', 'STRATA_DATABASE_URL', 'STRATA_WEEK5_INSTANCE', 'STRATA_PUBLIC_ORIGIN',
            'STRATA_ALLOWED_HOSTS', 'STRATA_SETUP_TOKEN', 'STRATA_OLLAMA_MODEL',
            'STRATA_OLLAMA_URL', 'STRATA_ETABS_URL', 'STRATA_ETABS_TOKEN',
            'STRATA_ETABS_TIMEOUT_SECONDS', 'STRATA_OCR_ENABLED')
    previous = {key: os.environ.pop(key) for key in keys if key in os.environ}
    try:
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(previous)


class Intake:
    def __init__(self, client, fixtures, output, artifact, process=None):
        self.client, self.fixtures, self.output = client, fixtures, output
        self.artifact, self.process = artifact, process
        self.phase = 'preflight'
        self.base = None
        self.adapters, self.snapshots, self.sources = {}, {}, {}
        self.oracle = read(fixtures / 'oracle.json')
        self.output.mkdir(parents=True, exist_ok=True)

    def call(self, method, path, body=None, expected=200):
        response = self.client.request(method, '/api/v1' + path, **({'json': body} if body is not None else {}))
        assert_that(response.status_code == expected,
                    f'{self.phase}: {method} {path} expected HTTP {expected}, got {response.status_code}: {response.text[:1500]}')
        return response

    def upload(self, name):
        content = (self.fixtures / name).read_bytes()
        source = self.call('POST', self.base + '/files', {'filename': name, 'content_base64': base64.b64encode(content).decode(), 'source_only': Path(name).suffix.lower() in ('.csv', '.json')}).json()['file']
        assert_that(source['sha256'] == sha(content), f'Source hash changed: {name}')
        self.sources[name] = source
        return source

    def adapter(self, name):
        profile = read(self.fixtures / name)
        item = self.call('POST', self.base + '/adapters', {'profile': profile}).json()['adapter']
        exported = self.call('GET', self.base + '/adapters/' + item['id'] + '/export').json()
        assert_that(exported == profile, f'Adapter export drift: {name}')
        self.adapters[name] = item['id']
        return item['id']

    def mapped(self, name, adapter, parent=None):
        source = self.upload(name)
        aid = self.adapters[adapter]
        path = self.base + '/adapters/' + aid + '/apply'
        preview = self.call('POST', path, {'file_id': source['id'], 'preview': True}).json()['mapping']
        body = {'file_id': source['id'], 'title': 'SYNTHETIC intake ' + name}
        if parent:
            body['parent_id'] = parent
        snapshot = self.call('POST', path, body).json()['snapshot']
        assert_that(snapshot['input'] == preview['input'] and snapshot['provenance'] == preview['provenance'], f'Preview/apply mismatch: {name}')
        self.snapshots[name] = snapshot
        self.artifact['mapped_inputs'].append({'file': name, 'file_id': source['id'], 'file_sha256': source['sha256'], 'snapshot_id': snapshot['id'], 'input_hash': snapshot['input_hash'], 'adapter': adapter, 'preview_equal_applied': True, 'input': snapshot['input'], 'provenance': snapshot['provenance']})
        return snapshot

    def package(self, version, approve=True):
        name = 'rule-package-' + version + '.json'
        package = read(self.fixtures / name)
        self.call('POST', self.base + '/rule-packages/validate', {'package': package})
        rule = self.call('POST', self.base + '/rule-packages/import', {'package': package}).json()['rules'][0]
        assert_that(rule['rule']['status'] == 'draft' and rule['rule']['approved_by'] is None, 'Imported rule gained approval')
        self.artifact['rules'].append({'id': rule['id'], 'rule_id': rule['rule']['id'], 'version': version, 'imported_status': 'draft'})
        if approve:
            self.call('POST', self.base + '/rules/' + rule['id'] + '/approve', {})
        return rule

    def finished(self, rid):
        if self.process:
            self.process(rid)
        deadline = time.monotonic() + 60
        while True:
            run = self.call('GET', self.base + '/runs/' + rid).json()['run']
            if run['state'] not in ('QUEUED', 'RUNNING'):
                return run
            assert_that(time.monotonic() < deadline, 'Worker did not complete within 60 seconds')
            time.sleep(.1)

    def run(self, source, target, parent=None):
        body = {'snapshot_id': source['id'], 'compare_to': target['id']}
        path = self.base + '/runs/' + parent + '/resume' if parent else self.base + '/runs'
        if not parent:
            body['task_id'] = 'handoff'
            body['use_model'] = False
        rid = self.call('POST', path, body).json()['run']['id']
        return self.finished(rid)

    def activate(self, snapshot):
        self.call('POST', self.base + '/snapshots/' + snapshot['id'] + '/activate', {})

    def cases(self, version, source, targets, names=('pass', 'fail', 'not_verified')):
        ids = []
        for name in names:
            case = {'schema': 'strata-case/1', 'case_id': 'NEW-INTAKE-' + name.upper(), 'version': version,
                    'title': 'SYNTHETIC independently authored intake ' + name, 'authority': 'synthetic',
                    'task_id': 'handoff', 'snapshot_id': source['id'], 'compare_to': targets[name]['id'],
                    'rule_versions': [{'id': 'HANDOFF', 'version': version}],
                    'expected': copy.deepcopy(self.oracle['rule_versions'][version][name]),
                    'truth': copy.deepcopy(self.oracle['truth'])}
            cid = self.call('POST', self.base + '/cases', {'case': case}).json()['case']['id']
            ids.append(cid)
        record = self.call('POST', self.base + '/evaluations', {'case_ids': ids}).json()['evaluation']
        runs = [self.finished(entry['run_id']) for entry in record['entries']]
        result = self.call('GET', self.base + '/evaluations/' + record['id']).json()['evaluation']
        assert_that(result['state'] == 'COMPLETED' and result['summary']['matched'] == len(names), f'Frozen oracle mismatch: {version}: {result}')
        self.artifact['batches'].append({'rule_version': version, 'evaluation_id': record['id'], 'measured_before_retirement': True, 'result': result})
        for name, run in zip(names, runs):
            self.write_reports(run['id'], version + '-' + name)
        return dict(zip(names, runs)), record['id']

    def write_reports(self, rid, label):
        run = self.call('GET', self.base + '/runs/' + rid).json()['run']
        marker = 'DRAFT - CURRENT REVIEW REQUIRED' if run['stale'] else 'REVIEWED SOFTWARE RECORD' if run['review_state'] == 'APPROVED' else 'DRAFT - NOT REVIEWED'
        for language in ('en', 'zh-CN'):
            response = self.call('GET', self.base + '/runs/' + rid + '/report?format=html&language=' + language)
            assert_that('1850' in response.text and '1849.8' in response.text, 'Report lost expected or actual engineering values')
            translated_marker = read(ROOT / 'backend/strata/locales' / (language + '.json')).get(marker, marker)
            assert_that(translated_marker in response.text, f'Report is missing the correct {language} draft/review marker')
            (self.output / (label + '-' + language + '.html')).write_bytes(response.content)
        response = self.call('GET', self.base + '/runs/' + rid + '/report?format=json')
        (self.output / (label + '.json')).write_bytes(response.content)

    def execute(self):
        manifest = read(self.fixtures / 'fixture-manifest.json')
        assert_that(manifest['material_type'] == 'synthetic' and self.oracle['frozen_before_system_execution'] is True, 'Synthetic or frozen oracle label missing')
        for name, expected in manifest['files'].items():
            assert_that(Path(name).name == name and not (self.fixtures / name).is_symlink() and (self.fixtures / name).resolve().is_relative_to(self.fixtures) and sha((self.fixtures / name).read_bytes()) == expected, f'Fixture integrity mismatch: {name}')
        assert_that('N' in UNITS and 'kN' in UNITS and 'MN' not in UNITS, 'Unit capability changed: re-review the MN refusal oracle before adopting this fixture')
        self.artifact['oracle_sha256'] = sha((self.fixtures / 'oracle.json').read_bytes())
        self.artifact['fixture_manifest_sha256'] = sha((self.fixtures / 'fixture-manifest.json').read_bytes())
        self.phase = 'new project / new adapters'
        project = self.call('POST', '/projects', {'name': 'SYNTHETIC new client intake ' + datetime.now(timezone.utc).isoformat()}).json()['project']
        self.base = '/projects/' + project['id']
        self.artifact['project_id'] = project['id']
        for name in ('adapter-source.json', 'adapter-target.json', 'adapter-target-partial.json'):
            self.adapter(name)
        source = self.mapped('source.two-sheet.synthetic.xlsx', 'adapter-source.json')
        good = self.mapped('target-pass.synthetic.csv', 'adapter-target.json')
        bad = self.mapped('target-fail.synthetic.csv', 'adapter-target.json')
        partial = self.mapped('target-missing.synthetic.csv', 'adapter-target-partial.json')
        self.phase = 'explicit mapping errors'
        for oracle in self.oracle['mapping_errors']:
            raw = self.sources.get(oracle['file']) or self.upload(oracle['file'])
            before = len(self.call('GET', self.base + '/dashboard').json()['snapshots'])
            failure = self.call('POST', self.base + '/adapters/' + self.adapters[oracle['adapter']] + '/apply', {'file_id': raw['id']}, expected=422).json()
            errors = failure.get('errors') or failure.get('detail', {}).get('errors', [])
            assert_that(any(error.get('field') == oracle['field'] and oracle['reason_contains'] in error.get('reason', '') for error in errors), f'Wrong mapping failure location/reason: {failure}')
            after = len(self.call('GET', self.base + '/dashboard').json()['snapshots'])
            assert_that(before == after, 'Failed mapping published a snapshot')
            self.artifact['mapping_errors'].append({'expected': oracle, 'actual': failure, 'no_snapshot_created': True})
        self.phase = 'draft rule blocks execution'
        draft = self.package('INTAKE-R1', approve=False)
        blocked = self.run(source, good)
        assert_that(blocked['status'] == self.oracle['lifecycle']['draft_rule_run_status'] and blocked['state'] == 'WAITING', 'Draft rule authorised a calculation')
        self.call('POST', self.base + '/rules/' + draft['id'] + '/approve', {})
        self.artifact['draft_rule_gate'] = {'run_id': blocked['id'], 'status': blocked['status'], 'state': blocked['state']}
        self.phase = 'first independent batch'
        targets = {'pass': good, 'fail': bad, 'not_verified': partial}
        initial, initial_eval = self.cases('INTAKE-R1', source, targets)
        self.artifact['missing_material_requests'] = initial['not_verified'].get('material_requests', [])
        self.phase = 'missing material side/path'
        expected_missing = {('target', '/received/horizontal/force'), ('target', '/received/horizontal/unit')}
        actual_missing = {(item['where'].get('side'), item['where'].get('field')) for item in self.artifact['missing_material_requests'] if item['kind'] == 'input_field'}
        assert_that(actual_missing == expected_missing, f'Material requests target the wrong side/path: expected {sorted(expected_missing)}, actual {sorted(actual_missing)}')
        self.artifact['material_request_side_path_verified'] = True
        self.activate(good)
        self.call('POST', self.base + '/runs/' + initial['pass']['id'] + '/review', {'action': 'approve', 'note': 'Synthetic independent oracle and two-field original provenance reviewed; not engineering certification.'})
        self.phase = 'new source and target files / new snapshots'
        source2 = self.mapped('source.reissued.synthetic.xlsx', 'adapter-source.json', source['id'])
        good2 = self.mapped('target-reissued.synthetic.csv', 'adapter-target.json', good['id'])
        stale = self.call('GET', self.base + '/runs/' + initial['pass']['id']).json()['run']
        assert_that(stale['stale'] and stale['review_state'] == self.oracle['lifecycle']['input_change_review_state'] and stale['reviews'], 'New input did not invalidate/retain previous review')
        fresh = self.run(source2, good2, initial['pass']['id'])
        assert_that(fresh['status'] == 'PASS' and fresh['parent_run_id'] == initial['pass']['id'], 'Linked input refresh failed')
        self.call('POST', self.base + '/runs/' + fresh['id'] + '/review', {'action': 'approve', 'note': 'Reissued synthetic source and target checked; source files and prior review retained.'})
        self.artifact['input_change'] = {'old_run_id': stale['id'], 'old_review_state': stale['review_state'], 'old_review_count': len(stale['reviews']), 'stale_reasons': stale['stale_reasons'], 'successor_id': fresh['id'], 'source_and_target_hashes_changed': source['input_hash'] == source2['input_hash'] and good['input_hash'] == good2['input_hash'] and self.sources['source.two-sheet.synthetic.xlsx']['sha256'] != self.sources['source.reissued.synthetic.xlsx']['sha256'] and self.sources['target-pass.synthetic.csv']['sha256'] != self.sources['target-reissued.synthetic.csv']['sha256']}
        assert_that(self.artifact['input_change']['source_and_target_hashes_changed'], 'Test reissue did not preserve numeric input while changing raw source hashes')
        self.phase = 'strict rule version / old review invalidation'
        self.package('INTAKE-R2')
        old = self.call('GET', self.base + '/runs/' + fresh['id']).json()['run']
        assert_that(old['stale'] and old['review_state'] == self.oracle['lifecycle']['rule_change_review_state'] and any('rule' in reason.lower() for reason in old['stale_reasons']), 'Rule change did not invalidate review')
        strict = self.run(source2, good2, fresh['id'])
        strict_case = {'schema': 'strata-case/1', 'case_id': 'NEW-INTAKE-PASS', 'version': 'INTAKE-R2', 'title': 'SYNTHETIC same values under tighter rule', 'authority': 'synthetic', 'task_id': 'handoff', 'snapshot_id': source2['id'], 'compare_to': good2['id'], 'rule_versions': [{'id': 'HANDOFF', 'version': 'INTAKE-R2'}], 'expected': self.oracle['rule_versions']['INTAKE-R2']['pass'], 'truth': self.oracle['truth']}
        from strata.cases import compare
        strict_comparison = compare(strict_case, strict)
        assert_that(strict_comparison['matched'], f'Strict rule did not match frozen expectation: {strict_comparison}')
        self.artifact['rule_change'] = {'old_run_id': fresh['id'], 'old_review_state': old['review_state'], 'stale_reasons': old['stale_reasons'], 'strict_comparison': strict_comparison}
        self.write_reports(strict['id'], 'INTAKE-R2-strict')
        self.phase = 'relative tolerance / linked resolution and review'
        self.package('INTAKE-R3')
        relative = self.run(source2, good2, strict['id'])
        assert_that(relative['status'] == 'PASS', 'Relative tolerance did not restore the independently expected PASS')
        dashboard = self.call('GET', self.base + '/dashboard').json()
        for issue in dashboard['issues']:
            if issue['source_run_id'] == strict['id']:
                self.call('POST', self.base + '/issues/' + issue['id'], {'action': 'resolve', 'resolution_run_id': relative['id'], 'note': 'SYNTHETIC test rule changed explicitly to R3; same finding now passes under the approved relative tolerance. No previous outcome overwritten.'})
        self.call('POST', self.base + '/runs/' + relative['id'] + '/review', {'action': 'approve', 'note': 'SYNTHETIC software review only: reviewed explicit R3 tolerance, independent oracle, source provenance and linked history.'})
        final = self.call('GET', self.base + '/runs/' + relative['id']).json()['run']
        assert_that(final['review_state'] == self.oracle['lifecycle']['final_review_state'] and not final['stale'], 'Final relative-tolerance review is not current')
        self.artifact['final_review'] = {'run_id': final['id'], 'status': final['status'], 'review_state': final['review_state'], 'parent_run_id': final['parent_run_id']}
        self.write_reports(final['id'], 'INTAKE-R3-reviewed')
        self.phase = 'final pinned batch / retired oracle validity'
        targets['pass'] = good2
        latest, latest_eval = self.cases('INTAKE-R3', source2, targets)
        retired = self.call('GET', self.base + '/evaluations/' + initial_eval).json()['evaluation']
        assert_that(retired['summary']['invalid_cases'] == 3, 'Retired rule cases still reported as valid')
        self.artifact['retired_batch'] = {'evaluation_id': initial_eval, 'invalid_cases': retired['summary']['invalid_cases'], 'invalid_reasons': [item['invalid_reasons'] for item in retired['items']]}
        self.phase = 'original bytes / mapping provenance'
        for name, file in self.sources.items():
            content = self.call('GET', self.base + '/files/' + file['id'] + '/content').content
            assert_that(sha(content) == file['sha256'] == sha((self.fixtures / name).read_bytes()), f'Original bytes lost: {name}')
        original = self.snapshots['source.two-sheet.synthetic.xlsx']['provenance']
        vertical = next(item for item in original if item['target'] == '/loads/vertical/force')
        horizontal = next(item for item in original if item['target'] == '/loads/horizontal/force')
        assert_that(vertical['original_value'] == -1850000 and vertical['value'] == -1850 and vertical['original_unit'] == 'N' and vertical['unit'] == 'kN', 'Negative vertical source trace changed')
        assert_that(horizontal['original_value'] == '225000' and horizontal['value'] == 225 and horizontal['location']['table'] == 'P17_Transverse', 'Mixed string-number workbook trace changed')
        self.artifact['source_bytes_verified'] = len(self.sources)
        self.artifact['summary'] = {'initial_batch': initial_eval, 'final_batch': latest_eval, 'new_independent_case_variants': 3, 'rule_versions_exercised': 3, 'initial_matches': 3, 'final_matches': 3, 'mapping_failures_correctly_located': len(self.artifact['mapping_errors']), 'lifecycle_verified': True, 'paid_model_calls': 0, 'customer_engineering_accuracy': 'NOT VERIFIED', 'native_CSI': 'NOT VERIFIED'}
        self.artifact['status'] = 'PASS'
        self.phase = 'complete'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=ROOT / 'examples/client-intake-v13')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/client-intake-v13')
    parser.add_argument('--url', help='Optional plain loopback HTTP origin; creates a new synthetic project')
    parser.add_argument('--username', help='Local STRATA login name; password is prompted, never stored')
    args = parser.parse_args()
    try:
        revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        revision = 'packaged source; see release manifest'
    artifact = {'schema': 'strata-client-intake-verification/1', 'generated_at': datetime.now(timezone.utc).isoformat(), 'status': 'RUNNING', 'material_type': 'synthetic', 'scope': 'Actual authenticated API and deterministic calculation over entirely new synthetic intake. No browser, customer material, engineering approval, paid model, OCR or native CSI claim.', 'source_commit_at_execution': revision, 'application_version': read(ROOT / 'package.json')['version'], 'tool_fingerprint': TOOL_FINGERPRINT, 'mapped_inputs': [], 'mapping_errors': [], 'rules': [], 'batches': []}
    intake = None
    attempt = args.output.resolve() / ('attempt-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + secrets.token_hex(3))
    artifact['report_directory'] = str(attempt)
    try:
        if args.url:
            import httpx
            origin = urlsplit(args.url)
            if origin.scheme != 'http' or origin.hostname not in ('127.0.0.1', 'localhost', '::1') or origin.path not in ('', '/') or origin.username or origin.password or origin.query or origin.fragment:
                raise ValueError('Use a plain local HTTP origin; cloud deployment is deferred')
            artifact['mode'] = 'real loopback HTTP / background worker; new synthetic project'
            with httpx.Client(base_url=args.url, timeout=30) as client:
                login = client.post('/api/v1/auth/login', json={'username': args.username or input('Local STRATA username: '), 'password': getpass.getpass('Local STRATA password: ')})
                login.raise_for_status()
                client.headers['Authorization'] = 'Bearer ' + login.json()['token']
                intake = Intake(client, args.fixtures.resolve(), attempt, artifact)
                intake.execute()
        else:
            artifact['mode'] = 'real authenticated FastAPI API in-process TestClient / deterministic tools; isolated temporary SQLite'
            with tempfile.TemporaryDirectory(prefix='strata-new-intake-') as directory, isolated_database_environment():
                app = create_app(directory, testing=True, worker=False)
                with TestClient(app) as client:
                    auth = client.post('/api/v1/auth/bootstrap', json={'username': 'synthetic-intake-verifier', 'password': secrets.token_urlsafe(24)})
                    assert_that(auth.status_code == 200, 'Temporary bootstrap failed')
                    client.headers['Authorization'] = 'Bearer ' + auth.json()['token']
                    intake = Intake(client, args.fixtures.resolve(), attempt, artifact, app.state.runner.process)
                    intake.execute()
    except Exception as error:
        artifact.update(status='FAIL', failed_phase=intake.phase if intake else 'setup', error=type(error).__name__ + ': ' + str(error))
    args.output.mkdir(parents=True, exist_ok=True)
    attempt.mkdir(parents=True, exist_ok=True)
    receipt = json.dumps(artifact, ensure_ascii=False, indent=2) + '\n'
    (attempt / 'verification.json').write_text(receipt, encoding='utf-8')
    (args.output / 'verification.json').write_text(receipt, encoding='utf-8')
    print(json.dumps({'status': artifact['status'], 'output': str(args.output.resolve()), 'summary': artifact.get('summary'), 'failed_phase': artifact.get('failed_phase'), 'error': artifact.get('error')}, ensure_ascii=False))
    return 0 if artifact['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
