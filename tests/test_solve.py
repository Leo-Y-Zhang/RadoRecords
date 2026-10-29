import subprocess

import pytest

import solve


def test_model_parser_handles_lines_zeros_signs_and_auxiliaries():
    text = 'c model\ns SATISFIABLE\nv -1 -2 3 0\nv 4 -5 99 -100 0\n'
    assert solve.parse_model(text, 5) == '00110'


@pytest.mark.parametrize('text', ['s SATISFIABLE\n', 'v -1 -2 3 4 0\n',
                                  'v -1 -2 4 -5 0\n'])
def test_truncated_model_cannot_supply_a_witness(text):
    with pytest.raises(ValueError, match='does not assign color variables'):
        solve.parse_model(text, 5)


@pytest.mark.parametrize('code,stdout,verdict,sat', [
    (10, 'v -1 -2 3 4 -5 0\n', 'SAT_WITNESS_VERIFIED', True),
    (10, 'v -1 -2 3 4 5 0\n', 'WITNESS_REJECTED', True),
    (20, '', 'UNSAT', False),
    (0, 's UNSATISFIABLE\n', 'SOLVER_ERROR', None),
    (-11, '', 'SOLVER_ERROR', None),
])
def test_solver_result_requires_exit_code_and_checked_witness(
        monkeypatch, tmp_path, code, stdout, verdict, sat):
    monkeypatch.setattr(solve, 'find_kissat', lambda *args: 'mock-kissat')

    def run(args, **kwargs):
        assert args[0] == 'mock-kissat'
        return subprocess.CompletedProcess(args, code, stdout, 'diagnostic')

    monkeypatch.setattr(solve.subprocess, 'run', run)
    rec = solve.solve_instance(2, 5, workdir=str(tmp_path))
    assert rec['verdict'] == verdict
    assert rec['sat'] is sat
    assert rec['returncode'] == code
    if sat is None:
        assert rec['detail'] == 'diagnostic'


def test_solver_timeout_is_undecided(monkeypatch, tmp_path):
    monkeypatch.setattr(solve, 'find_kissat', lambda *args: 'mock-kissat')

    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])

    monkeypatch.setattr(solve.subprocess, 'run', run)
    rec = solve.solve_instance(2, 5, workdir=str(tmp_path), timeout=0.1)
    assert rec['verdict'] == 'TIMEOUT'
    assert rec['sat'] is None
