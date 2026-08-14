"""Standalone, solver-free check of a claimed good coloring.

A "good" 2-coloring of [1,N] for parameter n is one with NO monochromatic
solution to x_1^2 + ... + x_n^2 = z^2 (all n+1 values in [1,N], repeats
allowed, z included in the color requirement -- the Myers/Parrish convention
behind A250026).

This checker shares NOTHING with the CNF encoder: instead of enumerating
solutions it runs, for each color class C and each candidate z in C, a bitset
DP asking whether z^2 is a sum of exactly n squares of members of C.  If the
encoder and this checker were both wrong they would have to be wrong in the
same direction by accident across two unrelated algorithms.

Usage:
    python verify_witness.py probe.json            # check a witness file
    python verify_witness.py --selftest            # internal tests

Witness JSON must carry: n, N, sat=true, coloring = string of N chars '0'/'1'
(color of integer i at index i-1).

Exit codes: 0 accepted, 1 rejected / malformed.
"""
from __future__ import annotations

import json
import sys


def mono_solution_exists(coloring, n, z_colored=True):
    """Is there a monochromatic solution for this coloring of [1,N]?

    coloring: string of '0'/'1', length N.  Returns a description tuple
    (color, z) of some monochromatic solution, or None.
    """
    N = len(coloring)
    for color in '01':
        cls = [v for v in range(1, N + 1) if coloring[v - 1] == color]
        if not cls:
            continue
        # reach[k] = bitmask of sums of exactly k squares of class members
        top = N * N
        mask_all = (1 << (top + 1)) - 1
        reach = 1
        for _ in range(n):
            nxt = 0
            for v in cls:
                shifted = reach << (v * v)
                if shifted > mask_all:
                    shifted &= mask_all
                if not shifted:
                    break
                nxt |= shifted
            reach = nxt
            if not reach:
                break
        if not reach:
            continue
        zs = cls if z_colored else range(1, N + 1)
        for z in zs:
            if (reach >> (z * z)) & 1:
                return (color, z)
    return None


def check_witness(doc):
    """Return (ok, message)."""
    for key in ('n', 'N', 'sat', 'coloring'):
        if key not in doc:
            return False, f'missing field {key!r}'
    n, N, coloring = doc['n'], doc['N'], doc['coloring']
    if doc['sat'] is not True:
        return False, 'witness file does not claim SAT'
    if not isinstance(coloring, str) or len(coloring) != N:
        return False, f'coloring length {len(coloring)} != N={N}'
    if set(coloring) - set('01'):
        return False, 'coloring contains characters other than 0/1'
    z_colored = doc.get('convention', {}).get('z_colored', True)
    hit = mono_solution_exists(coloring, n, z_colored=z_colored)
    if hit is not None:
        color, z = hit
        return False, (f'coloring is NOT good: color {color} contains a '
                       f'solution with z={z} (z^2={z * z} is a sum of {n} '
                       f'squares of that class)')
    return True, f'ACCEPTED: good coloring of [1,{N}] for n={n}'


def selftest():
    # 1. n=9: 9*a^2 = (3a)^2, so {a,3a} monochromatic is a solution.
    #    All-one-color [1,15] must be rejected (z=3..: 9*1=3^2).
    assert mono_solution_exists('1' * 15, 9) is not None
    # 2. n=9, N=8: color {1,2} vs rest. 9*1^2=9=3^2 needs 1 and 3 same color
    #    (not here); other solutions need z^2>=9+... check a known-good split:
    #    class {1,2}: sums of 9 squares from {1,4} range 9..36; squares of the
    #    class are 1,4: neither 9..36 hit 1 or 4 -> safe. class {3..8}:
    #    min sum 9*9=81 > 64=8^2 -> safe.
    assert mono_solution_exists('11000000', 9) is None
    # 3. n=2 Pythagorean: {3,4,5} monochromatic must be caught (N=5 so the
    #    complement {1,2} stays solution-free).
    assert mono_solution_exists('00111', 2) == ('1', 5)
    # 4. same but z=5 colored differently: with z required in the class the
    #    solution disappears, z_colored=False keeps it.
    assert mono_solution_exists('00110', 2, z_colored=True) is None
    assert mono_solution_exists('00110', 2, z_colored=False) is not None
    # 5. check_witness plumbing: malformed and corrupted docs are rejected.
    ok, _ = check_witness({'n': 9, 'N': 8, 'sat': True, 'coloring': '11000000'})
    assert ok
    ok, _ = check_witness({'n': 9, 'N': 8, 'sat': True, 'coloring': '11111111'})
    assert not ok
    ok, _ = check_witness({'n': 9, 'N': 8, 'sat': True, 'coloring': '110000'})
    assert not ok
    print('SELFTEST PASSED')
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] == '--selftest':
        return selftest()
    if len(argv) != 2:
        print(__doc__)
        return 1
    with open(argv[1], encoding='utf-8') as fh:
        doc = json.load(fh)
    ok, msg = check_witness(doc)
    print(msg)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
