from itertools import product
import json
from pathlib import Path
import subprocess
import sys

import pytest

import verify_witness


def witness(**changes):
    return dict({'n': 2, 'N': 5, 'sat': True, 'coloring': '00110'}, **changes)


def test_one_changed_color_is_rejected():
    assert verify_witness.check_witness(witness())[0]
    # Only color(5) changes: 3^2 + 4^2 = 5^2 becomes monochromatic.
    assert not verify_witness.check_witness(witness(coloring='00111'))[0]


@pytest.mark.parametrize('changes', [
    {'sat': False}, {'sat': 1}, {'sat': None},
    {'coloring': '0011'}, {'coloring': '001100'},
    {'coloring': '0011x'}, {'coloring': [0, 0, 1, 1, 0]}, {'N': 6},
])
def test_malformed_witness_is_rejected(changes):
    assert not verify_witness.check_witness(witness(**changes))[0]


@pytest.mark.parametrize('field', ['n', 'N', 'sat', 'coloring'])
def test_missing_field_is_rejected(field):
    doc = witness()
    del doc[field]
    assert not verify_witness.check_witness(doc)[0]


@pytest.mark.parametrize('n,N', [(1, 1), (2, 5), (3, 6), (4, 5), (9, 3)])
@pytest.mark.parametrize('z_colored', [True, False])
def test_dp_matches_arithmetic_for_every_small_coloring(n, N, z_colored,
                                                      arithmetic_solutions):
    solutions = arithmetic_solutions(n, N)
    for bits in product('01', repeat=N):
        coloring = ''.join(bits)
        hits = {(bits[xs[0] - 1], z) for xs, z in solutions
                if len({bits[x - 1] for x in xs}) == 1
                and (not z_colored or bits[z - 1] == bits[xs[0] - 1])}
        hit = verify_witness.mono_solution_exists(coloring, n, z_colored)
        if hits:
            assert hit in hits, (n, coloring, z_colored)
        else:
            assert hit is None, (n, coloring, z_colored)


@pytest.mark.parametrize('kind', ['valid', 'changed-color', 'truncated'])
def test_witness_file_cli(tmp_path, kind):
    path = tmp_path / 'witness.json'
    doc = witness(coloring='00111') if kind == 'changed-color' else witness()
    text = json.dumps(doc)
    path.write_text(text[:-2] if kind == 'truncated' else text)
    script = Path(verify_witness.__file__)
    result = subprocess.run([sys.executable, str(script), str(path)],
                            capture_output=True, text=True, timeout=1)
    assert result.returncode == (0 if kind == 'valid' else 1)
