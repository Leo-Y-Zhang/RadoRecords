"""Exhaustive check of small instances: no solver, no CNF, just all colorings.

For a given n and N this walks every 2-coloring of [1,N] (color of 1 fixed,
since the property is invariant under swapping the colors) and reports whether
some coloring avoids a monochromatic solution of x_1^2+...+x_n^2 = z^2 under
the pinned convention (repeats allowed, z colored).  It is the ground truth
the CNF encodings are compared against, and it independently reproduces the
small published values of A250026 with no SAT solver in the loop.

The per-coloring test uses bitmasks over the distinct solution supports from
encode.iter_supports; for small cases the completely independent DP checker in
verify_witness.py is run as well, so the two disagreeing would flag an
encoder bug.

    python brute_force.py --n 9 --sweep 12-16     # threshold must be 15
    python brute_force.py --n 28 --N 20           # SAT/UNSAT at one point
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import encode            # noqa: E402
import verify_witness    # noqa: E402


def support_masks(n, N, distinct=False, z_colored=True):
    masks = []
    for sup in encode.iter_supports(n, N, distinct=distinct,
                                    z_colored=z_colored):
        m = 0
        for v in sup:
            m |= 1 << (v - 1)
        masks.append(m)
    # deduplicate and prefer small masks first: they refute colorings sooner
    return sorted(set(masks), key=lambda m: bin(m).count('1'))


def brute_sat(n, N, distinct=False, z_colored=True, budget_s=None,
              cross_check=False):
    """Exhaustively decide: does a good coloring of [1,N] exist?

    Returns (sat, witness_or_None, colorings_checked).  Raises TimeoutError
    if budget_s elapses first.
    """
    masks = support_masks(n, N, distinct=distinct, z_colored=z_colored)
    t0 = time.time()
    total = 1 << (N - 1)          # color of integer 1 fixed to 0
    for c in range(total):
        if budget_s is not None and (c & 0xFFFF) == 0:
            if time.time() - t0 > budget_s:
                raise TimeoutError(f'budget exceeded after {c}/{total} colorings')
        good = True
        for m in masks:
            x = c & m
            if x == m or x == 0:
                good = False
                break
        if good:
            witness = ''.join('1' if (c >> (i - 1)) & 1 else '0'
                              for i in range(1, N + 1))
            if cross_check:
                assert verify_witness.mono_solution_exists(
                    witness, n, z_colored=z_colored) is None, \
                    'mask check and DP checker disagree on a witness'
            return True, witness, c + 1
    if cross_check:
        # spot-check some refuted colorings against the independent DP
        step = max(1, total // 64)
        for c in range(0, total, step):
            witness = ''.join('1' if (c >> (i - 1)) & 1 else '0'
                              for i in range(1, N + 1))
            assert verify_witness.mono_solution_exists(
                witness, n, z_colored=z_colored) is not None, \
                'mask check refutes a coloring the DP checker accepts'
    return False, None, total


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--N', type=int)
    ap.add_argument('--sweep', help='e.g. 12-16: report SAT/UNSAT for each N')
    ap.add_argument('--distinct', action='store_true')
    ap.add_argument('--no-z-colored', dest='z_colored', action='store_false')
    ap.add_argument('--budget', type=float, default=None, help='seconds per N')
    ap.add_argument('--cross-check', action='store_true')
    args = ap.parse_args()
    if args.sweep:
        lo, hi = (int(t) for t in args.sweep.split('-'))
        Ns = range(lo, hi + 1)
    elif args.N:
        Ns = [args.N]
    else:
        raise SystemExit('give --N or --sweep')
    threshold = None
    for N in Ns:
        t0 = time.time()
        try:
            sat, wit, checked = brute_sat(args.n, N, distinct=args.distinct,
                                          z_colored=args.z_colored,
                                          budget_s=args.budget,
                                          cross_check=args.cross_check)
        except TimeoutError as exc:
            print(f'n={args.n} N={N}: BUDGET EXCEEDED ({exc})')
            break
        print(f'n={args.n} N={N}: {"SAT" if sat else "UNSAT"} '
              f'({checked} colorings, {time.time() - t0:.1f}s)'
              + (f' witness {wit}' if sat else ''))
        if not sat and threshold is None:
            threshold = N
    if args.sweep and threshold is not None:
        print(f'least UNSAT N in sweep: {threshold}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
