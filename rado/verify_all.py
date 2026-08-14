#!/usr/bin/env python3
"""Re-check every claim this repository makes, from scratch, in one command.

Nothing here trusts a previous run: witness colorings are re-verified by the
solver-free checker, the convention is re-pinned against published values by
pure-Python exhaustion, both CNF encodings are rebuilt and re-solved, and
every UNSAT is re-certified under drat-trim.  Sections that need the kissat /
drat-trim binaries skip LOUDLY when they are absent (a clean clone still
passes; nothing is silently assumed).

Exit code 0 means every claim is currently supported by evidence on disk.

Usage:
    python rado/verify_all.py            # everything (solver sections included)
    python rado/verify_all.py --fast     # skip the slow support-mode DRAT runs
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import brute_force       # noqa: E402
import drat_certify      # noqa: E402
import encode            # noqa: E402
import lazy              # noqa: E402
import verify_witness    # noqa: E402

EVID = os.path.join(HERE, 'evidence')
PY = sys.executable

# Every term this repository claims: n -> a(n).  28..30 reproduce the
# published values; everything from 31 on is NEW (not in OEIS), established
# here 2026-08-13/14 by the same full pipeline.  A term is listed here only
# once it has all four evidence files (both encodings, both endpoints) and a
# drat-trim-verified refutation in both encodings; terms resolved by the
# reach encoding alone are documented in PREFLIGHT.md but NOT claimed here.
CLAIMS = {28: 35, 29: 41, 30: 36, 31: 41, 32: 41, 33: 37, 34: 42, 35: 44,
          36: 37}

# Terms carried by the lazy encoding (rado/lazy.py) instead of the full
# support build, which stops being a laptop job above n=36: n -> a(n).
# The bar is the same in substance -- a witness at N=a(n)-1 accepted by the
# solver-free checker, a drat-trim-verified refutation at N=a(n), and the
# reach encoding agreeing at both endpoints -- with one addition.  The lazy
# refutation is a refutation of a SUBSET of the support encoding's clauses,
# so it refutes the full instance as well; what has to be checked is that
# every clause in it really is one of those clauses.  Each carries an
# explicit solution and this file re-does that arithmetic for all of them.
LAZY_CLAIMS = {37: 45, 38: 47, 39: 52, 40: 47, 41: 47, 42: 54, 43: 48,
               44: 56, 45: 56, 46: 50, 47: 57, 48: 58, 49: 51, 50: 60,
               51: 67, 52: 59, 53: 60, 54: 68, 55: 61, 56: 62, 57: 70,
               58: 63, 59: 72, 60: 71}

# Convention pinned by every check in this file.
CONVENTION = {'distinct': False, 'z_colored': True}

# Published small terms reproduced by pure-Python exhaustion (no solver):
# n -> (a(n), sweep start).
BRUTE_PINS = {5: (23, 21), 6: (18, 16), 9: (15, 13), 10: (16, 14)}

# Published values of A250026 (Myers 2015; entry version #35) used as a
# CONTROL GROUP for the reach encoding at campaign scale.  These are not
# claims of this repository -- they are known answers the encoding has to
# get right at exactly the sizes where terms are reported on the strength
# of `reach` alone, so a systematic reach bug could not hide.
REACH_CONTROL = {18: 28, 19: 25, 20: 29, 21: 29, 22: 26, 23: 36, 24: 32,
                 25: 27, 26: 38, 27: 33, 28: 35, 29: 41, 30: 36}

_pass, _fail = [], []


def check(name, ok, detail='', fail_detail=''):
    (_pass if ok else _fail).append(name)
    extra = detail if ok else (fail_detail or detail)
    print(f'  [{"PASS" if ok else "FAIL"}] {name}'
          f'{("  " + extra) if extra else ""}', flush=True)
    return ok


def section(t):
    print(f'\n=== {t} ===', flush=True)


def load(fname):
    p = os.path.join(EVID, fname)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def main():
    fast = '--fast' in sys.argv

    section('standalone checker selftest')
    r = subprocess.run([PY, os.path.join(HERE, 'verify_witness.py'),
                        '--selftest'], capture_output=True, text=True)
    check('verify_witness --selftest', r.returncode == 0
          and 'SELFTEST PASSED' in r.stdout)

    section('support enumeration equals naive multiset enumeration (small)')
    from itertools import combinations_with_replacement

    def naive(n, N):
        out = set()
        for z in range(1, N + 1):
            for xs in combinations_with_replacement(range(1, z), n):
                if sum(v * v for v in xs) == z * z:
                    out.add(frozenset(xs) | {z})
        return out

    for n, N in [(2, 26), (3, 20), (4, 15), (9, 16)]:
        got = set(frozenset(s) for s in encode.iter_supports(n, N))
        want = naive(n, N)
        check(f'n={n} N={N}: supports match ({len(want)})', got == want)

    section('convention pinned against published values by pure exhaustion')
    for n, (a, start) in sorted(BRUTE_PINS.items()):
        sat_below, wit, _ = brute_force.brute_sat(n, a - 1, cross_check=True,
                                                  **CONVENTION)
        sat_at, _, _ = brute_force.brute_sat(n, a, cross_check=True,
                                             **CONVENTION)
        check(f'a({n})={a}: every coloring of [1,{a}] fails, [1,{a - 1}] has '
              f'a good one', sat_below is True and sat_at is False)
        if sat_below:
            check(f'a({n})={a}: brute witness survives the independent checker',
                  verify_witness.mono_solution_exists(wit, n) is None)

    section('rejected convention variants stay rejected')
    check('distinct x_i: zero solutions at n=28, N=35 (instance trivially '
          'SAT, contradicting a(28)=35)',
          not list(encode.iter_supports(28, 35, distinct=True)))
    sat15, _, _ = brute_force.brute_sat(9, 15, distinct=False, z_colored=False)
    sat11, _, _ = brute_force.brute_sat(9, 11, distinct=False, z_colored=False)
    check('z uncolored: n=9 already UNSAT far below the published a(9)=15',
          sat15 is False and sat11 is False)

    section('each claimed term, re-derived from its own evidence files')
    check('CLAIMS here and EXPECTED in drat_certify.py agree',
          CLAIMS == drat_certify.EXPECTED)
    for n, a in sorted(CLAIMS.items()):
        recs = {}
        ok_files = True
        for mode in ('support', 'reach'):
            for N, kind in ((a, 'refutation'), (a - 1, 'witness')):
                doc = load(f'{mode}_n{n}_N{N}.json')
                recs[(mode, kind)] = doc
                if doc is None:
                    ok_files = False
        if not check(f'a({n})={a}: all four evidence files present', ok_files):
            continue
        conv_ok = all(
            doc['n'] == n and doc['convention']['distinct'] is False
            and doc['convention']['z_colored'] is True
            for doc in recs.values())
        check(f'a({n})={a}: every record is n={n} under the pinned convention',
              conv_ok)
        for mode in ('support', 'reach'):
            ref, wit = recs[(mode, 'refutation')], recs[(mode, 'witness')]
            check(f'a({n})={a} [{mode}]: UNSAT at N={a}',
                  ref['sat'] is False and ref['N'] == a)
            check(f'a({n})={a} [{mode}]: SAT at N={a - 1}',
                  wit['sat'] is True and wit['N'] == a - 1)
            good = verify_witness.check_witness(wit)
            check(f'a({n})={a} [{mode}]: witness re-verified solver-free',
                  good[0], fail_detail=good[1])
            for bad in ('0' * (a - 1), '1' * (a - 1)):
                corrupt = dict(wit, coloring=bad)
                ok, _msg = verify_witness.check_witness(corrupt)
                if ok:
                    break
            check(f'a({n})={a} [{mode}]: checker rejects corrupted witnesses',
                  not ok)
        check(f'a({n})={a}: SAT at {a - 1} and UNSAT at {a} give a({n})={a} '
              f'in both encodings', all((
                  recs[(m, 'witness')]['sat'] is True
                  and recs[(m, 'refutation')]['sat'] is False
                  and recs[(m, 'refutation')]['N']
                  == recs[(m, 'witness')]['N'] + 1)
                  for m in ('support', 'reach')))

    section('terms carried by the lazy encoding')
    check('LAZY_CLAIMS here and LAZY_EXPECTED in drat_certify.py agree',
          LAZY_CLAIMS == drat_certify.LAZY_EXPECTED)
    check('no term is claimed twice', not (set(CLAIMS) & set(LAZY_CLAIMS)))
    span = sorted(set(CLAIMS) | set(LAZY_CLAIMS))
    check(f'claimed n run contiguously from {span[0]} to {span[-1]} '
          f'(OEIS DATA cannot skip a term)',
          span == list(range(span[0], span[-1] + 1)))
    for n, a in sorted(LAZY_CLAIMS.items()):
        ref, wit = load(f'lazy_n{n}_N{a}.json'), load(f'lazy_n{n}_N{a - 1}.json')
        if not check(f'a({n})={a}: both lazy evidence files present',
                     ref is not None and wit is not None):
            continue
        check(f'a({n})={a} [lazy]: UNSAT at N={a}, SAT at N={a - 1}',
              ref['sat'] is False and ref['N'] == a
              and wit['sat'] is True and wit['N'] == a - 1)
        check(f'a({n})={a} [lazy]: records are n={n} under the pinned '
              f'convention',
              all(d['n'] == n and d['convention']['distinct'] is False
                  and d['convention']['z_colored'] is True
                  for d in (ref, wit)))
        good = verify_witness.check_witness(wit)
        check(f'a({n})={a} [lazy]: witness re-verified solver-free', good[0],
              fail_detail=good[1])
        corrupt_rejected = True
        for bad in ('0' * (a - 1), '1' * (a - 1)):
            if verify_witness.check_witness(dict(wit, coloring=bad))[0]:
                corrupt_rejected = False
        check(f'a({n})={a} [lazy]: checker rejects corrupted witnesses',
              corrupt_rejected)

        # The subset argument, re-established by arithmetic: a clause whose
        # justification is a genuine solution is a clause the full support
        # encoding emits.  Every clause, not a sample.
        bad_arith = [j for j in ref['justifications']
                     if not lazy.check_justification(j['x'], j['z'], n, a)]
        check(f'a({n})={a} [lazy]: all {len(ref["justifications"])} clauses '
              f'justified by a real solution',
              not bad_arith,
              fail_detail=f'{len(bad_arith)} bad, first {bad_arith[:1]}')
        bad_sup = [j for j in ref['justifications']
                   if sorted({v for v, _c in j['x']} | {j['z']})
                   != sorted(j['support'])]
        check(f'a({n})={a} [lazy]: every clause equals the support of its '
              f'own solution', not bad_sup,
              fail_detail=f'{len(bad_sup)} mismatched')
        check(f'a({n})={a} [lazy]: clause count matches the record',
              ref['clauses'] == 2 * len(ref['justifications']))

        r_ref, r_wit = load(f'reach_n{n}_N{a}.json'), load(f'reach_n{n}_N{a - 1}.json')
        if check(f'a({n})={a}: reach evidence present at both endpoints',
                 r_ref is not None and r_wit is not None):
            check(f'a({n})={a}: reach agrees (UNSAT@{a} / SAT@{a - 1})',
                  r_ref['sat'] is False and r_wit['sat'] is True,
                  fail_detail=f"reach {r_ref['sat']} / {r_wit['sat']}")

    section('the justification check is load-bearing, not decoration')
    # Each mutation below must be caught.  If any survives, the check above
    # would pass on clauses that are not clauses of the encoding at all.
    sample = load('lazy_n37_N45.json')
    if check('a(37) evidence available to mutate', sample is not None):
        j = sample['justifications'][0]
        n, N = 37, 45
        check('unmutated justification passes',
              lazy.check_justification(j['x'], j['z'], n, N))
        mutations = {
            'z shifted by one': (j['x'], j['z'] + 1),
            'a count incremented': ([[v, c + 1] for v, c in j['x']], j['z']),
            'a value incremented': ([[v + 1, c] for v, c in j['x']], j['z']),
            'a count dropped to zero': ([[v, 0] for v, c in j['x']], j['z']),
            'z pushed outside the interval': (j['x'], N + 1),
        }
        for name, (x, z) in mutations.items():
            check(f'mutation caught: {name}',
                  not lazy.check_justification(x, z, n, N))
        # and the multiset really does have to hold exactly n values
        check('mutation caught: wrong number of x values',
              not lazy.check_justification(j['x'], j['z'], n + 1, N))

    section('prose matches evidence')
    pre = os.path.join(os.path.dirname(HERE), 'PREFLIGHT.md')
    if not check('PREFLIGHT.md present', os.path.exists(pre)):
        pass
    else:
        text = open(pre, encoding='utf-8').read()
        for n, a in sorted(CLAIMS.items()):
            check(f'PREFLIGHT.md states a({n}) = {a}',
                  f'a({n}) = {a}' in text)
        for phrase in ('repeats allowed', 'z is colored', 'distinct',
                       'GO' ):
            check(f'PREFLIGHT.md documents: {phrase!r}', phrase in text)

    # Solver-dependent sections: skip loudly when the binaries are absent.
    tools, missing = drat_certify.find_tools()
    if missing:
        section(f'SAT/UNSAT re-solves and DRAT replay '
                f'(SKIPPED: {", ".join(missing)} not on PATH / env)')
    else:
        section('instances re-solved from a fresh encoding, both modes')
        import solve
        for n, a in sorted(CLAIMS.items()):
            for mode in ('reach',) if fast else ('reach', 'support'):
                r_at = solve.solve_instance(n, a, mode=mode,
                                            kissat=tools['kissat'])
                r_bel = solve.solve_instance(n, a - 1, mode=mode,
                                             kissat=tools['kissat'])
                check(f'a({n})={a} [{mode}]: fresh solve repeats '
                      f'UNSAT@{a} / SAT@{a - 1}',
                      r_at['verdict'] == 'UNSAT'
                      and r_bel['verdict'] == 'SAT_WITNESS_VERIFIED',
                      f"solve {r_at['solve_s']}s/{r_bel['solve_s']}s")

        section('brute force agrees with kissat where exhaustion is feasible')
        # Both encodings are pinned here, not just `support`: the n whose
        # support build does not fit the campaign timebox rest on `reach`
        # alone at N = a(n), so `reach` needs its own ground-truth anchor at
        # every n this repository reports.
        for n, N in [(28, 20), (29, 21), (30, 22), (31, 23), (32, 24),
                     (33, 25), (34, 26), (35, 27), (36, 28), (37, 29),
                     (38, 30), (39, 31), (40, 32)]:
            bsat, _w, _c = brute_force.brute_sat(n, N, **CONVENTION)
            rs = solve.solve_instance(n, N, mode='support',
                                      kissat=tools['kissat'])
            rr = solve.solve_instance(n, N, mode='reach',
                                      kissat=tools['kissat'])
            check(f'n={n} N={N}: brute force, support and reach all agree',
                  (bsat is True) == (rs['sat'] is True) == (rr['sat'] is True),
                  f'all three {"SAT" if bsat else "UNSAT"}',
                  fail_detail=f'brute={bsat} support={rs["sat"]} '
                              f'reach={rr["sat"]}')

        section('published a(18)..a(30) reproduced by the reach encoding alone')
        for n, a in sorted(REACH_CONTROL.items()):
            c_at = solve.solve_instance(n, a, mode='reach',
                                        kissat=tools['kissat'])
            c_bel = solve.solve_instance(n, a - 1, mode='reach',
                                         kissat=tools['kissat'])
            check(f'published a({n})={a}: reach alone gives UNSAT@{a} / '
                  f'SAT@{a - 1}',
                  c_at['verdict'] == 'UNSAT'
                  and c_bel['verdict'] == 'SAT_WITNESS_VERIFIED',
                  f"solve {c_at['solve_s']}s/{c_bel['solve_s']}s",
                  fail_detail=f"{c_at['verdict']} / {c_bel['verdict']}")

        section('lazy clauses really are clauses of the full encoding')
        # The arithmetic argument is checked above for every clause of every
        # claim.  Here it is checked the other way, against the enumerator
        # itself, on the instances small enough to enumerate whole.
        for n, N in [(16, 17), (25, 27)]:
            rec = lazy.solve_instance(n, N, kissat=tools['kissat'])
            lazy_sups = {frozenset(j['support']) for j in rec['justifications']}
            full = {frozenset(s) for s in encode.iter_supports(n, N)}
            check(f'n={n} N={N}: every lazy clause is in the full enumeration',
                  lazy_sups <= full,
                  f'{len(lazy_sups)} of {len(full)} '
                  f'({100 * len(lazy_sups) / len(full):.2f}%)',
                  fail_detail=f'{len(lazy_sups - full)} clause(s) not in it')
            check(f'n={n} N={N}: and strictly fewer, so work was skipped',
                  len(lazy_sups) < len(full))

        section('DRAT refutations replayed under drat-trim')
        for mode in ('reach', 'lazy') if fast else ('reach', 'support', 'lazy'):
            r = subprocess.run([PY, os.path.join(HERE, 'drat_certify.py'),
                                '--all', '--mode', mode, '--json'],
                               capture_output=True, text=True)
            try:
                recs = json.loads(r.stdout)
            except ValueError:
                recs = []
            if not check(f'[{mode}] certifier returned results', bool(recs),
                         fail_detail=(r.stdout + r.stderr).strip()[-300:]):
                continue
            for rec in recs:
                check(f"[{mode}] n={rec['n']} N={rec['N']}: "
                      f"refutation machine-checked",
                      rec['verdict'] == 'VERIFIED',
                      f"{rec.get('proof_mb', '-')}MB proof, "
                      f"check {rec.get('check_s', '-')}s",
                      fail_detail=rec.get('detail', rec['verdict']))

    print(f'\n{len(_pass)} passed, {len(_fail)} failed')
    if _fail:
        print('\nFAILED:')
        for f in _fail:
            print('  -', f)
        return 1
    print('\nEVERY CLAIM IN THIS REPOSITORY IS SUPPORTED BY EVIDENCE ON DISK.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
