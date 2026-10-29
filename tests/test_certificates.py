import json
from pathlib import Path
import subprocess

import pytest

import drat_certify


@pytest.fixture
def evidence(monkeypatch, tmp_path):
    # Redirect the hard-coded evidence location to a synthetic certificate.
    monkeypatch.setattr(drat_certify, '__file__', str(tmp_path / 'drat_certify.py'))
    directory = tmp_path / 'evidence'
    directory.mkdir()
    path = directory / 'lazy_n9_N3.json'
    doc = {'justifications': [{'support': [1, 3], 'x': [[1, 9]], 'z': 3}]}
    path.write_text(json.dumps(doc))
    return path, doc


def test_formula_is_rebuilt_from_checked_arithmetic(evidence, tmp_path):
    path = tmp_path / 'rebuilt.cnf'
    assert drat_certify.rebuild_lazy_formula(path, 9, 3) == (3, 2, 1, [])
    assert path.read_text() == 'p cnf 3 2\n1 3 0\n-1 -3 0\n'


@pytest.mark.parametrize('corruption', ['value', 'count', 'removed-support'])
def test_corrupt_formula_never_reaches_replay(monkeypatch, evidence, tmp_path,
                                            corruption):
    src, doc = evidence
    j = doc['justifications'][0]
    if corruption == 'value':
        j['z'] = 2
        j['support'] = [1, 2]  # support still agrees; arithmetic must reject it
    elif corruption == 'count':
        j['x'][0][1] = 8
    else:
        j['support'].remove(3)
    src.write_text(json.dumps(doc))

    def forbidden(*args, **kwargs):
        pytest.fail('invalid justification reached an external tool')

    monkeypatch.setattr(drat_certify.subprocess, 'run', forbidden)
    rec = drat_certify.certify(9, 3, 'lazy', {}, str(tmp_path))
    assert rec['verdict'] == 'BAD_JUSTIFICATION'
    assert rec['justifications_ok'] is False


def test_truncated_justification_file_is_rejected(evidence, tmp_path):
    src, _doc = evidence
    src.write_text('{"justifications": [')
    with pytest.raises(json.JSONDecodeError):
        drat_certify.rebuild_lazy_formula(tmp_path / 'rebuilt.cnf', 9, 3)


def simulate_replay(monkeypatch, tmp_path, output, solve_code=20, timeout_at=None):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs['timeout'] == 0.5
        if len(calls) == timeout_at:
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        if len(calls) == 1:
            assert args[:3] == ['mock-kissat', '-q', '--no-binary']
            assert Path(args[-2]).read_text().startswith('p cnf ')
            Path(args[-1]).write_text('0\n')
            return subprocess.CompletedProcess(args, solve_code, '', 'solver diagnostic')
        assert args[0] == 'mock-drat-trim'
        assert args[1:] == calls[0][-2:]
        return subprocess.CompletedProcess(args, 0, output, '')

    monkeypatch.setattr(drat_certify.subprocess, 'run', run)
    tools = {'kissat': 'mock-kissat', 'drat_trim': 'mock-drat-trim'}
    rec = drat_certify.certify(2, 5, 'reach', tools, str(tmp_path), timeout=0.5)
    return rec, calls


@pytest.mark.parametrize('output,verdict', [
    ('c replay\ns VERIFIED\n', 'VERIFIED'),
    ('s NOT VERIFIED\n', 'NOT_VERIFIED'),
    ('s VERIFIE', 'SOLVER_ERROR'),
    ('', 'SOLVER_ERROR'),
    ('c replay failed\n', 'SOLVER_ERROR'),
])
def test_only_successful_replay_certifies(monkeypatch, tmp_path, output, verdict):
    rec, calls = simulate_replay(monkeypatch, tmp_path, output)
    assert rec['verdict'] == verdict
    assert len(calls) == 2


@pytest.mark.parametrize('code,verdict', [(10, 'SAT'), (0, 'SOLVER_ERROR'),
                                        (-11, 'SOLVER_ERROR')])
def test_solver_failure_never_certifies(monkeypatch, tmp_path, code, verdict):
    rec, calls = simulate_replay(monkeypatch, tmp_path, 's VERIFIED\n', code)
    assert rec['verdict'] == verdict
    assert len(calls) == 1


@pytest.mark.parametrize('timeout_at', [1, 2])
def test_replay_timeout_is_not_verified(monkeypatch, tmp_path, timeout_at):
    rec, calls = simulate_replay(monkeypatch, tmp_path, 's VERIFIED\n',
                                 timeout_at=timeout_at)
    assert rec['verdict'] == 'TIMEOUT'
    assert len(calls) == timeout_at


def test_embedded_success_text_does_not_override_failed_replay(monkeypatch, tmp_path):
    rec, _calls = simulate_replay(monkeypatch, tmp_path,
                                   'c previous s VERIFIED result\ns NOT VERIFIED\n')
    assert rec['verdict'] == 'NOT_VERIFIED'
