"""Operational safety tests only; these do not replace real Docker checks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('week5_docker_verifier',ROOT/'scripts/verify-week5-docker.py')
verifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def args(tmp_path,port=4194):
    return argparse.Namespace(docker='docker',port=port,restore_port=4195,
                              output=tmp_path/'docker-verification.json')


def test_occupied_port_never_runs_docker_or_stops_other_services(tmp_path,monkeypatch):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        verification=verifier.Verification(args(tmp_path,listener.getsockname()[1]))
        def forbidden(*a,**kw):raise AssertionError('Existing service must not be changed')
        monkeypatch.setattr(verification,'command',forbidden)
        with pytest.raises(verifier.VerificationError,match='occupied'):
            verification.run()
        assert not verification.touched
        verification.result['status']='NOT RUN'
        verification.finish()
        assert verification.args.output.is_file()


def test_missing_engine_receipt_and_private_log_contain_no_credentials(tmp_path,monkeypatch):
    verification=verifier.Verification(args(tmp_path))
    def missing(*a,**kw):raise FileNotFoundError('No Docker executable')
    monkeypatch.setattr(verifier.subprocess,'run',missing)
    with pytest.raises(FileNotFoundError):verification.command(['version','--format','json'])
    verification.result['status']='NOT RUN';verification.finish()
    public=verification.args.output.read_text()
    private=verification.args.output.with_name('docker-commands.private.json')
    assert verification.token not in public and verification.password not in public
    assert not json.loads(public)['retained_test_volumes']
    assert private.stat().st_mode & 0o077 == 0


def test_cleanup_is_limited_to_created_project_and_failed_stop_is_visible(tmp_path,monkeypatch):
    verification=verifier.Verification(args(tmp_path));verification.touched=[1]
    commands=[]
    def compose(index,*a,**kw):
        commands.append((index,a))
        if a[0]=='stop':raise RuntimeError('Synthetic engine stop failure')
        return ''
    monkeypatch.setattr(verification,'compose',compose)
    verification.result['status']='PASS';verification.finish()
    assert commands==[(1,('stop','app'))]
    assert verification.result['status']=='FAILED'
    assert verification.result['owned_test_services_stopped'] is False
    assert verification.token not in verification.args.output.read_text()


def test_compose_only_uses_generated_projects_with_private_runtime_environment(tmp_path,monkeypatch):
    verification=verifier.Verification(args(tmp_path));record=[]
    def command(a,env=None,timeout=90):record.append((a,env));return ''
    monkeypatch.setattr(verification,'command',command)
    verification.compose(1,'config','--quiet')
    command,environment=record[0]
    assert command[command.index('-p')+1]==verification.projects[1]
    assert command[-2:]==['config','--quiet']
    assert environment['STRATA_WEEK5_SETUP_TOKEN']==verification.token
    assert environment['STRATA_WEEK5_PORT']=='4195'
    assert verification.password not in command and verification.token not in command
