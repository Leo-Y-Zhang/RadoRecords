"""Decide an endpoint without enumerating the solution supports.

The `support` encoding writes one clause pair per distinct solution support.
At n=37, N=45 that is 19,516,162 supports and 39,032,324 clauses, and the
Python that writes them takes 41 minutes before a solver starts.  Almost all
of those clauses are dead weight: if support T is a subset of support S then
clause(T) subsumes clause(S), and measuring the inclusion-minimal fraction on
instances small enough to enumerate whole gives 158x at n=28, 231x at n=30,
252x at n=33 -- the redundancy grows with n.

This module decides the same question by generating clauses on demand:

    solve the clauses found so far
      UNSAT -> the whole instance is UNSAT.  These clauses are a SUBSET of the
               full encoding, so nothing about how they were chosen matters.
      SAT   -> hand the coloring to the solver-free checker.  Accepted means
               the coloring is genuinely good, so the instance is SAT.
               Rejected means the checker found a monochromatic solution; add
               exactly that support and go round again.

Both exits are sound without trusting the search in this file:

  * UNSAT rests on subset-hood.  Every clause is emitted together with an
    explicit solution x_1..x_n, z (its "justification"), and a clause whose
    justification is arithmetically valid is by definition one the full
    encoding emits.  Re-checking the arithmetic re-establishes subset-hood
    without enumerating anything.
  * SAT rests on verify_witness, which reads the equation rather than the CNF.

A poor search costs speed and nothing else.  In practice a(60) needs 288
clauses where the full encoding would need tens of millions.

    python lazy.py --n 37 --N 45 --json evidence/lazy_n37_N45.json
    python lazy.py --n 37 --bisect             # least N that is UNSAT

Exit codes: 0 decided, 1 something is wrong, 3 kissat missing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_witness  # noqa: E402

TOOLS_MISSING = 3


def find_kissat(explicit=None):
    path = explicit or os.environ.get('KISSAT') or shutil.which('kissat')
    if path and os.path.exists(path):
        return path
    if path and shutil.which(path):
        return shutil.which(path)
    return None


def mono_solution(coloring, n, z_colored=True):
    """Find a monochromatic solution and return the x values and z.

    The same bitset DP as verify_witness.mono_solution_exists, extended to
    reconstruct a witnessing multiset instead of only reporting existence.
    Returns (color, sorted xs, z) or None.
    """
    N = len(coloring)
    for color in '01':
        cls = [v for v in range(1, N + 1) if coloring[v - 1] == color]
        if not cls:
            continue
        mask_all = (1 << (N * N + 1)) - 1
        reach = [1]                      # reach[k]: sums of exactly k squares
        for _ in range(n):
            nxt = 0
            for v in cls:
                shifted = reach[-1] << (v * v)
                if shifted > mask_all:
                    shifted &= mask_all
                nxt |= shifted
            reach.append(nxt)
            if not nxt:
                break
        if len(reach) <= n or not reach[n]:
            continue
        for z in (cls if z_colored else range(1, N + 1)):
            if not (reach[n] >> (z * z)) & 1:
                continue
            xs, target = [], z * z
            for k in range(n, 0, -1):
                for v in cls:
                    rest = target - v * v
                    if rest >= 0 and (reach[k - 1] >> rest) & 1:
                        xs.append(v)
                        target = rest
                        break
                else:
                    raise AssertionError('DP has no back-step; inconsistent')
            if target != 0 or len(xs) != n:
                raise AssertionError('reconstruction did not close')
            return color, sorted(xs), z
    return None


def as_multiset(xs):
    """[3,3,5] -> [[3,2],[5,1]].  Solutions repeat values heavily; the pairs
    are a fraction of the size of the flat list and check the same way."""
    counts = {}
    for v in xs:
        counts[v] = counts.get(v, 0) + 1
    return [[v, counts[v]] for v in sorted(counts)]


def check_justification(pairs, z, n, N):
    """Is this really a solution, and so really a clause of the encoding?

    Takes the multiset form: exactly n x values, all of them and z inside
    [1,N], and the squares summing to z^2.  Anyone can redo this by hand.
    """
    if not 1 <= z <= N:
        return False
    if any(count < 1 or not 1 <= v <= N for v, count in pairs):
        return False
    if sum(count for _v, count in pairs) != n:
        return False
    return sum(count * v * v for v, count in pairs) == z * z


def write_cnf(path, N, supports):
    """The clause pair forbidding an all-one-color support, as in encode.py."""
    with open(path, 'w', encoding='ascii', newline='\n') as fh:
        fh.write(f'p cnf {N} {2 * len(supports)}\n')
        for sup in supports:
            s = sorted(sup)
            fh.write(' '.join(map(str, s)) + ' 0\n')
            fh.write(' '.join(str(-v) for v in s) + ' 0\n')


def solve_instance(n, N, kissat=None, z_colored=True, workdir=None,
                   max_rounds=100000, keep_cnf=None):
    """Returns a record dict; record['sat'] is True or False."""
    kis = find_kissat(kissat)
    if kis is None:
        raise FileNotFoundError(
            'kissat not found (flag --kissat, env KISSAT, or PATH)')
    own = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix='rado_lazy_')
    cnf = keep_cnf or os.path.join(workdir, f'lazy_n{n}_N{N}.cnf')
    rec = {'seq': 'A250026', 'n': n, 'N': N, 'mode': 'lazy',
           'convention': {'distinct': False, 'z_colored': z_colored,
                          'equation': 'x_1^2+...+x_n^2 = z^2',
                          'interval': '[1,N]'}}
    supports, justifications, seen = [], [], set()
    solve_s = check_s = 0.0
    t_start = time.time()
    try:
        for rounds in range(1, max_rounds + 1):
            write_cnf(cnf, N, supports)
            t0 = time.time()
            r = subprocess.run([kis, '-q', cnf], capture_output=True, text=True)
            solve_s += time.time() - t0
            if r.returncode == 20:
                rec.update(sat=False, verdict='UNSAT')
                break
            if r.returncode != 10:
                rec.update(sat=None, verdict='SOLVER_ERROR',
                           returncode=r.returncode,
                           detail=(r.stderr or r.stdout or '').strip()[-400:])
                break
            val = {}
            for line in r.stdout.splitlines():
                if line.startswith('v '):
                    for tok in line[2:].split():
                        lit = int(tok)
                        if lit:
                            val[abs(lit)] = lit > 0
            coloring = ''.join('1' if val.get(i) else '0'
                               for i in range(1, N + 1))
            t0 = time.time()
            hit = mono_solution(coloring, n, z_colored=z_colored)
            check_s += time.time() - t0
            if hit is None:
                rec.update(sat=True, coloring=coloring)
                good, msg = verify_witness.check_witness(rec)
                rec['witness_check'] = msg
                rec['verdict'] = ('SAT_WITNESS_VERIFIED' if good
                                  else 'WITNESS_REJECTED')
                break
            _color, xs, z = hit
            pairs = as_multiset(xs)
            if not check_justification(pairs, z, n, N):
                raise AssertionError(f'bad justification x={pairs} z={z}')
            sup = frozenset(xs) | {z}
            if sup in seen:
                raise AssertionError(f'repeated support {sorted(sup)}: '
                                     f'the search is not making progress')
            seen.add(sup)
            supports.append(sup)
            justifications.append({'support': sorted(sup), 'x': pairs, 'z': z})
        else:
            raise AssertionError(f'undecided after {max_rounds} rounds')
    finally:
        if own and not keep_cnf:
            shutil.rmtree(workdir, ignore_errors=True)
    rec.update(rounds=rounds, clauses=2 * len(supports),
               supports=len(supports), solve_s=round(solve_s, 1),
               check_s=round(check_s, 1),
               total_s=round(time.time() - t_start, 1),
               justifications=justifications)
    return rec


def bisect(n, lo, hi, **kw):
    """Least N in [lo,hi] whose instance is UNSAT, or None.

    SAT is downward closed in N: restricting a good coloring of [1,N+1] to
    [1,N] leaves a good coloring, because a monochromatic solution inside
    [1,N] is one inside [1,N+1] too.  So the predicate flips exactly once.
    """
    cache = {}

    def unsat(N):
        if N not in cache:
            rec = solve_instance(n, N, **kw)
            if rec['sat'] is None:
                raise RuntimeError(f'n={n} N={N}: {rec["verdict"]}')
            cache[N] = rec
        return cache[N]['sat'] is False

    if not unsat(hi):
        return None, cache
    if unsat(lo):
        return lo, cache
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if unsat(mid):
            hi = mid
        else:
            lo = mid
    return hi, cache


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--N', type=int)
    ap.add_argument('--bisect', action='store_true',
                    help='find a(n) instead of deciding one N')
    ap.add_argument('--lo', type=int, default=2)
    ap.add_argument('--hi', type=int, default=130)
    ap.add_argument('--kissat')
    ap.add_argument('--json', help='write the record here')
    args = ap.parse_args()
    try:
        if args.bisect:
            a, cache = bisect(args.n, args.lo, args.hi, kissat=args.kissat)
            if a is None:
                print(f'n={args.n}: no UNSAT at or below N={args.hi}')
                return 1
            rec = cache[a]
            rec['a'] = a
            print(f'a({args.n}) = {a}  ({rec["rounds"]} rounds, '
                  f'{rec["clauses"]} clauses, {len(cache)} solves)')
        else:
            if args.N is None:
                raise SystemExit('give --N or --bisect')
            rec = solve_instance(args.n, args.N, kissat=args.kissat)
            brief = {k: v for k, v in rec.items() if k != 'justifications'}
            print(json.dumps(brief, indent=1))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return TOOLS_MISSING
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='ascii', newline='\n') as fh:
            json.dump(rec, fh, indent=1)
            fh.write('\n')
    return 0 if rec['verdict'] in ('UNSAT', 'SAT_WITNESS_VERIFIED') else 1


if __name__ == '__main__':
    sys.exit(main())
