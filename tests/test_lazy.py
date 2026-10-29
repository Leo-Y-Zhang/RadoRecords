from itertools import product
from pathlib import Path
import subprocess

import pytest

import lazy


def test_justification_accepts_repetition_and_interval_endpoints():
    assert lazy.check_justification([[1, 9]], 3, 9, 3)
    assert lazy.check_justification([[3, 1], [4, 1]], 5, 2, 5)


@pytest.mark.parametrize('pairs,z,n,N', [
    ([[1, 9]], 2, 9, 3),                 # changed z
    ([[2, 9]], 3, 9, 3),                 # changed x
    ([[1, 8]], 3, 9, 3),                 # wrong count
    ([], 3, 9, 3),                       # removed multiset
    ([[1, 9], [2, 0]], 3, 9, 3),         # arithmetic survives zero count
    ([[0, 1], [1, 9]], 3, 10, 3),        # arithmetic survives zero value
    ([[1, 9]], 3, 9, 2),                 # z out of range, arithmetic exact
    ([[1, 9]], 3.0, 9, 3),
    ([[1, 9.0]], 3, 9, 3),
    ([[True, 9]], 3, 9, 3),
    ([[3, True], [4, 1]], 5, 2, 5),
    ([[1, 25], [2.5, 12]], 10, 37, 10),
    ([[1, -3], [2, 3]], 3, 0, 3),       # negative count with exact sum
])
def test_corrupted_justification_is_rejected(pairs, z, n, N):
    assert not lazy.check_justification(pairs, z, n, N)


@pytest.mark.parametrize('n,N', [(1, 1), (2, 5), (3, 6), (9, 3)])
@pytest.mark.parametrize('z_colored', [True, False])
def test_reconstruction_matches_arithmetic(n, N, z_colored, arithmetic_solutions):
    solutions = arithmetic_solutions(n, N)
    for bits in product('01', repeat=N):
        expected = [(xs, z) for xs, z in solutions
                    if len({bits[x - 1] for x in xs}) == 1
                    and (not z_colored or bits[z - 1] == bits[xs[0] - 1])]
        hit = lazy.mono_solution(''.join(bits), n, z_colored)
        if not expected:
            assert hit is None
            continue
        color, xs, z = hit
        assert (tuple(xs), z) in expected
        assert all(bits[x - 1] == color for x in xs)
        assert sum(x * x for x in xs) == z * z
        assert len(xs) == n


def test_multiset_counts_are_sorted_and_exact():
    assert lazy.as_multiset([5, 3, 5, 1, 3, 5]) == [[1, 1], [3, 2], [5, 3]]
    assert lazy.as_multiset([]) == []


def test_clause_pair_and_count(tmp_path):
    path = tmp_path / 'lazy.cnf'
    lazy.write_cnf(path, 5, [{5, 3, 4}, {1, 3}])
    assert path.read_text().splitlines() == [
        'p cnf 5 4', '3 4 5 0', '-3 -4 -5 0', '1 3 0', '-1 -3 0',
    ]


@pytest.mark.parametrize('threshold', [2, 3, 4, 8, 9, 10])
def test_bisect_finds_first_unsat_without_solver(monkeypatch, threshold):
    calls = []

    def decide(n, N, **kwargs):
        assert n == 9
        calls.append(N)
        return {'sat': N < threshold}

    monkeypatch.setattr(lazy, 'solve_instance', decide)
    result, cache = lazy.bisect(9, 2, 9)
    assert result == (threshold if threshold <= 9 else None)
    assert set(cache) == set(calls)
    assert len(calls) == len(set(calls))


def test_bisect_refuses_undecided_result(monkeypatch):
    monkeypatch.setattr(lazy, 'solve_instance',
                        lambda *a, **kw: {'sat': None, 'verdict': 'SOLVER_ERROR'})
    with pytest.raises(RuntimeError, match='SOLVER_ERROR'):
        lazy.bisect(9, 2, 9)


@pytest.mark.parametrize('last_code,verdict', [(10, 'SAT_WITNESS_VERIFIED'),
                                              (20, 'UNSAT'), (0, 'SOLVER_ERROR')])
def test_search_adds_justified_clause_then_checks_result(monkeypatch, tmp_path,
                                                      last_code, verdict):
    monkeypatch.setattr(lazy, 'find_kissat', lambda *a: 'mock-kissat')
    formulas = []

    def run(args, **kwargs):
        formulas.append(Path(args[-1]).read_text())
        if len(formulas) == 1:
            return subprocess.CompletedProcess(args, 10, 'v -1 -2 -3 -4 -5 0\n', '')
        return subprocess.CompletedProcess(args, last_code, 'v -1 -2 3 4 -5 0\n', '')

    monkeypatch.setattr(lazy.subprocess, 'run', run)
    rec = lazy.solve_instance(2, 5, workdir=str(tmp_path))
    assert rec['verdict'] == verdict
    assert rec['sat'] is ({10: True, 20: False, 0: None}[last_code])
    assert rec['rounds'] == 2
    assert rec['clauses'] == 2
    assert rec['justifications'] == [{'support': [3, 4, 5], 'x': [[3, 1], [4, 1]], 'z': 5}]
    assert formulas == ['p cnf 5 0\n', 'p cnf 5 2\n3 4 5 0\n-3 -4 -5 0\n']


def test_search_refuses_repeated_counterexample(monkeypatch, tmp_path):
    monkeypatch.setattr(lazy, 'find_kissat', lambda *a: 'mock-kissat')
    monkeypatch.setattr(lazy.subprocess, 'run', lambda args, **kw:
                        subprocess.CompletedProcess(args, 10, 'v -1 -2 -3 -4 -5 0\n', ''))
    with pytest.raises(AssertionError, match='repeated support'):
        lazy.solve_instance(2, 5, workdir=str(tmp_path), max_rounds=3)
