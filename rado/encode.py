"""CNF encodings for the 2-color Rado numbers of x_1^2 + ... + x_n^2 = z^2.

A250026: a(n) is the least N such that every 2-coloring of {1,...,N} contains
a monochromatic solution to x_1^2 + x_2^2 + ... + x_n^2 = z^2, where all n+1
variables take values in {1,...,N} and "monochromatic" means x_1,...,x_n AND z
all receive the same color.  Under the conventions of Myers & Parrish
("Some Nonlinear Rado Numbers", Integers 18B (2018), #A6, Definition 1 and
Section 2), the variables are NOT required to be distinct.

The instance for (n, N) is satisfiable iff a good coloring of [1,N] exists,
i.e. iff N < a(n).  Boolean variable i (1 <= i <= N) is the color of the
integer i.

Two independent encodings are provided; they must agree on satisfiability:

support:  one clause pair per distinct solution SUPPORT.  A solution is a
    multiset {x_1 <= ... <= x_n} plus z; whether it is monochromatic depends
    only on the SET of distinct integers it uses (its support), so solutions
    sharing a support share a clause pair.  For n >= 2 every x_i < z
    (x_i >= z would force the sum past z^2), so the support is T | {z} with
    max = z, and supports never collide across different z.  Naive multiset
    enumeration is hopeless here (10^8..10^9 multisets for the instances of
    interest); distinct supports number ~10^6 and are enumerated by a bitset
    reachability DP plus a set-of-states recursion that emits each support
    exactly once.

reach:  a monotone Tseitin-style encoding of the reachability DP itself.
    Aux var r[c][k][m] means "m is a sum of k squares of integers colored c".
    Only implication clauses r <- premise are emitted (derivations are
    well-founded because k strictly decreases), plus for every z a clause
    forbidding color(z)=c together with r[c][n][z^2].  Size is polynomial in
    N and n, so it scales where support enumeration would explode.

Convention knobs (for pinning the convention against published values):
    distinct:   require x_1,...,x_n pairwise distinct (NOT Myers's convention)
    z_colored:  z must carry the common color (Myers's convention: True)

Stdlib only.  CLI writes DIMACS:
    python encode.py --n 28 --N 34 --mode support --out f.cnf
"""
from __future__ import annotations

import argparse
import sys
import time


# ---------------------------------------------------------------------------
# solution-support enumeration (nondistinct, the Myers convention)
# ---------------------------------------------------------------------------

def _reach_tables(n, z):
    """reach[v][k] = bitmask over m: exists T subset of {1..v} with
    multiplicities t_i >= 1, sum of t_i = k, sum of t_i*v_i^2 = m."""
    target = z * z
    vmax = z - 1
    mask_all = (1 << (target + 1)) - 1
    reach = [[0] * (n + 1) for _ in range(vmax + 1)]
    reach[0][0] = 1
    for v in range(1, vmax + 1):
        v2 = v * v
        prev = reach[v - 1]
        cur = reach[v]
        for k in range(n + 1):
            acc = prev[k]
            for t in range(1, k + 1):
                if t * v2 > target:
                    break
                p = prev[k - t]
                if p:
                    acc |= (p << (t * v2)) & mask_all
            cur[k] = acc
    return reach


def supports_for_z(n, z):
    """Yield each distinct support {x-values} (WITHOUT z) exactly once, as a
    tuple, for solutions x_1 <= ... <= x_n < z with sum x_i^2 = z^2."""
    target = z * z
    vmax = z - 1
    if vmax < 1 or target < n:
        return
    reach = _reach_tables(n, z)
    if not ((reach[vmax][n] >> target) & 1):
        return

    # Iterative DFS over values v = vmax..1, branching on "v in support".
    # A node carries the set of open (k, m) demands consistent with the chosen
    # prefix; demands are pre-filtered against reach so every branch taken
    # leads to at least one support.
    stack = [(vmax, ((n, target),), ())]
    while stack:
        v, states, chosen = stack.pop()
        if v == 0:
            # states nonempty and filtered => contains (0, 0)
            yield chosen
            continue
        rv = reach[v - 1]
        v2 = v * v
        # branch: v not in the support
        out = tuple((k, m) for (k, m) in states if (rv[k] >> m) & 1)
        if out:
            stack.append((v - 1, out, chosen))
        # branch: v in the support with some multiplicity t >= 1
        acc = set()
        for (k, m) in states:
            for t in range(1, k + 1):
                m2 = m - t * v2
                if m2 < 0:
                    break
                if (rv[k - t] >> m2) & 1:
                    acc.add((k - t, m2))
        if acc:
            stack.append((v - 1, tuple(acc), chosen + (v,)))


def supports_distinct_for_z(n, z, N):
    """Distinct-x variant: supports are n-subsets of [1,N] with
    sum of squares = z^2 (still x_i < z for n >= 2)."""
    target = z * z
    hi = min(z - 1, N)
    out = []

    def rec(v, k, m, chosen):
        # choose k distinct values from 1..v summing (squares) to m
        if k == 0:
            if m == 0:
                out.append(tuple(chosen))
            return
        if v < k:
            return
        # min possible sum: 1^2+..+k^2 ; max possible: v^2+..+(v-k+1)^2
        if m < k * (k + 1) * (2 * k + 1) // 6:
            return
        mx = sum((v - i) * (v - i) for i in range(k))
        if m > mx:
            return
        if v * v <= m:
            rec(v - 1, k - 1, m - v * v, chosen + [v])
        rec(v - 1, k, m, chosen)

    rec(hi, n, target, [])
    return out


def iter_supports(n, N, distinct=False, z_colored=True):
    """Yield each distinct clause-support (a tuple of integers in [1,N])
    exactly once, over all solutions with all variables in [1,N]."""
    seen = None if z_colored else set()
    for z in range(1, N + 1):
        if distinct:
            zs = supports_distinct_for_z(n, z, N)
        else:
            zs = supports_for_z(n, z)
        for sup in zs:
            full = sup + (z,) if z_colored else sup
            if z_colored:
                yield full            # max(full) = z: never collides across z
            else:
                key = frozenset(full)
                if key not in seen:
                    seen.add(key)
                    yield full


# ---------------------------------------------------------------------------
# monotone reachability encoding
# ---------------------------------------------------------------------------

def build_reach_cnf(n, N, z_colored=True):
    """Return (num_vars, clauses) for the reach encoding.

    Vars 1..N are colors (True = color A).  For each color and each useful DP
    state (k, m) an aux var r means "m is expressible as a sum of k squares of
    integers of this color (repeats allowed)".  Only <- implications are
    emitted, so any satisfying assignment's colors admit no monochromatic
    solution, and any good coloring extends to a satisfying assignment.
    """
    top = N * N
    # forward reachability (any colors): R[k] = bitmask of sums of k squares
    R = [0] * (n + 1)
    R[0] = 1
    mask_all = (1 << (top + 1)) - 1
    sq = [v * v for v in range(1, N + 1)]
    for k in range(1, n + 1):
        acc = 0
        prev = R[k - 1]
        for v2 in sq:
            shifted = prev << v2
            if shifted > mask_all:
                shifted &= mask_all
            if not shifted:
                break
            acc |= shifted
        R[k] = acc
    # backward usefulness: states that can still reach some (n, z^2)
    targets = 0
    zs = []
    for z in range(1, N + 1):
        if z * z >= n and ((R[n] >> (z * z)) & 1):
            targets |= 1 << (z * z)
            zs.append(z)
    CO = [0] * (n + 1)
    CO[n] = targets
    for k in range(n - 1, -1, -1):
        acc = 0
        nxt = CO[k + 1]
        for v2 in sq:
            acc |= nxt >> v2
        CO[k] = acc
    useful = [R[k] & CO[k] for k in range(n + 1)]

    # allocate vars
    nv = N
    var = [dict(), dict()]  # per color: (k, m) -> var id
    for c in (0, 1):
        for k in range(1, n + 1):
            u = useful[k]
            m = 0
            while u:
                low = u & -u
                m = low.bit_length() - 1
                var[c][(k, m)] = nv = nv + 1
                u &= u - 1
    clauses = []
    for c in (0, 1):
        vc = var[c]
        s = 1 if c == 0 else -1   # color literal: c=0 wants  x_v, c=1 wants -x_v
        for (k, m), r in vc.items():
            for v in range(1, N + 1):
                v2 = v * v
                if v2 > m:
                    break
                if k == 1:
                    if v2 == m:
                        clauses.append((-s * v, r))
                else:
                    pre = vc.get((k - 1, m - v2))
                    if pre is not None:
                        clauses.append((-s * v, -pre, r))
        for z in zs:
            r = vc.get((n, z * z))
            if r is not None:
                if z_colored:
                    clauses.append((-s * z, -r))
                else:
                    clauses.append((-r,))
    return nv, clauses


# ---------------------------------------------------------------------------
# CNF assembly / DIMACS
# ---------------------------------------------------------------------------

def support_clause_pair(sup):
    """The two clauses forbidding an all-same coloring of the support."""
    pos = tuple(v for v in sup)
    neg = tuple(-v for v in sup)
    return pos, neg


def write_dimacs(path, n, N, mode='support', distinct=False, z_colored=True):
    """Write the instance; returns (num_vars, num_clauses, support_count)."""
    t0 = time.time()
    if mode == 'reach':
        if distinct:
            raise ValueError('reach mode implements the nondistinct convention')
        nv, clauses = build_reach_cnf(n, N, z_colored=z_colored)
        with open(path, 'w', encoding='ascii', newline='\n') as fh:
            fh.write(f'p cnf {nv} {len(clauses)}\n')
            fh.write('\n'.join(' '.join(map(str, cl)) + ' 0' for cl in clauses))
            fh.write('\n')
        return nv, len(clauses), None
    if mode != 'support':
        raise ValueError(f'unknown mode {mode!r}')
    body = []
    nsup = 0
    with open(path + '.body', 'w', encoding='ascii', newline='\n') as bf:
        chunk = []
        for sup in iter_supports(n, N, distinct=distinct, z_colored=z_colored):
            nsup += 1
            pos, neg = support_clause_pair(sup)
            chunk.append(' '.join(map(str, pos)) + ' 0')
            chunk.append(' '.join(map(str, neg)) + ' 0')
            if len(chunk) >= 200000:
                bf.write('\n'.join(chunk) + '\n')
                chunk = []
        if chunk:
            bf.write('\n'.join(chunk) + '\n')
    import os
    with open(path, 'w', encoding='ascii', newline='\n') as fh:
        fh.write(f'p cnf {N} {2 * nsup}\n')
        with open(path + '.body', 'r', encoding='ascii') as bf:
            while True:
                buf = bf.read(1 << 22)
                if not buf:
                    break
                fh.write(buf)
    os.remove(path + '.body')
    del body
    return N, 2 * nsup, nsup


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, required=True, help='number of x variables')
    ap.add_argument('--N', type=int, required=True, help='color the interval [1,N]')
    ap.add_argument('--mode', default='support', choices=['support', 'reach'])
    ap.add_argument('--distinct', action='store_true')
    ap.add_argument('--no-z-colored', dest='z_colored', action='store_false')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    t0 = time.time()
    nv, nc, nsup = write_dimacs(args.out, args.n, args.N, mode=args.mode,
                                distinct=args.distinct, z_colored=args.z_colored)
    print(f'n={args.n} N={args.N} mode={args.mode} distinct={args.distinct} '
          f'z_colored={args.z_colored}: {nv} vars, {nc} clauses'
          + (f' ({nsup} supports)' if nsup is not None else '')
          + f' in {time.time() - t0:.1f}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
