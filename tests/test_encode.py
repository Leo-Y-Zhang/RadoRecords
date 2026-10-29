from itertools import product

import pytest

import encode


@pytest.mark.parametrize('n,N', [(2, 5), (3, 9), (4, 7), (9, 6)])
@pytest.mark.parametrize('distinct', [False, True])
@pytest.mark.parametrize('z_colored', [False, True])
def test_supports_equal_arithmetic(n, N, distinct, z_colored, arithmetic_solutions):
    expected = {frozenset(xs) | ({z} if z_colored else set())
                for xs, z in arithmetic_solutions(n, N, distinct)}
    actual = [frozenset(s) for s in encode.iter_supports(
        n, N, distinct=distinct, z_colored=z_colored)]
    assert set(actual) == expected
    assert len(actual) == len(set(actual)), 'duplicate supports'


def propagates_without_conflict(clauses, colors):
    """Unit propagation only, with all color variables fixed.

    The reach encoding is a forward implication circuit: fixing its inputs
    makes propagation complete. No SAT solver or assignment search is used.
    """
    values = dict(enumerate(colors, 1))
    while True:
        changed = False
        for clause in clauses:
            if any(values.get(abs(lit)) == (lit > 0)
                   for lit in clause if abs(lit) in values):
                continue
            unknown = [lit for lit in clause if abs(lit) not in values]
            if not unknown:
                return False
            if len(unknown) == 1:
                lit = unknown[0]
                values[abs(lit)] = lit > 0
                changed = True
        if not changed:
            return True


@pytest.mark.parametrize('n,N', [(1, 1), (2, 5), (3, 6), (9, 3)])
@pytest.mark.parametrize('z_colored', [True, False])
def test_reach_circuit_for_every_small_coloring(n, N, z_colored,
                                              arithmetic_solutions):
    nv, clauses = encode.build_reach_cnf(n, N, z_colored=z_colored)
    assert nv >= N
    assert all(0 < abs(lit) <= nv for clause in clauses for lit in clause)
    solutions = arithmetic_solutions(n, N)
    for colors in product([False, True], repeat=N):
        bad = any(len({colors[x - 1] for x in xs}) == 1
                  and (not z_colored or colors[z - 1] == colors[xs[0] - 1])
                  for xs, z in solutions)
        assert propagates_without_conflict(clauses, colors) is not bad, colors


@pytest.mark.parametrize('mode', ['support', 'reach'])
def test_dimacs_header_and_both_clause_polarities(tmp_path, mode):
    path = str(tmp_path / 'tiny.cnf')
    nv, nc, nsup = encode.write_dimacs(path, 2, 5, mode=mode)
    with open(path) as fh:
        header, *body = fh.read().splitlines()
    assert header == f'p cnf {nv} {nc}'
    assert len(body) == nc
    clauses = []
    for line in body:
        literals = [int(token) for token in line.split()]
        assert literals[-1] == 0
        assert all(0 < abs(lit) <= nv for lit in literals[:-1])
        clauses.append(literals[:-1])
    if mode == 'support':
        assert (nv, nc, nsup) == (5, 2, 1)
        assert {frozenset(c) for c in clauses} == {
            frozenset([3, 4, 5]), frozenset([-3, -4, -5])}
    for colors, good in [([False] * 5, False), ([True] * 5, False),
                         ([False, False, True, True, False], True)]:
        assert propagates_without_conflict(clauses, colors) is good


def test_dimacs_rejects_unsupported_modes(tmp_path):
    path = str(tmp_path / 'tiny.cnf')
    with pytest.raises(ValueError, match='unknown mode'):
        encode.write_dimacs(path, 2, 5, mode='typo')
    with pytest.raises(ValueError, match='nondistinct'):
        encode.write_dimacs(path, 2, 5, mode='reach', distinct=True)
