"""Produce and machine-check a DRAT refutation certificate for an UNSAT claim.

A SAT witness coloring can be re-checked by anyone in milliseconds
(verify_witness.py, no solver).  "Every coloring fails" is an absence, and an
absence is exactly what a buggy solver reports -- so each UNSAT here is
certified: kissat emits an ASCII DRAT proof (--no-binary is mandatory; the
binary format does not replay under drat-trim) and drat-trim replays it
against the formula.  Only the literal line 's VERIFIED' counts.

What is then trusted is drat-trim plus the claim that the CNF encodes the
definition; that second half is pinned by the brute-force agreement checks
and by both encodings agreeing on every instance (see verify_all.py).

Neither binary ships with this repository.  Point at them with the KISSAT and
DRAT_TRIM environment variables, --kissat/--drat-trim flags, or PATH.

    python drat_certify.py --n 28                 # certify a(28)=35 at N=35
    python drat_certify.py --n 28 --N 35 --mode reach
    python drat_certify.py --all --json

Exit codes (the interface verify_all.py relies on):
    0   every requested refutation verified
    1   a proof did NOT verify, or the instance was not UNSAT
    3   tools missing; nothing was checked -- callers should SKIP, not fail
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

import encode  # noqa: E402
import lazy    # noqa: E402

TOOLS_MISSING = 3

# Every claimed term: n -> a(n) (28..30 published, 31 and up new; must equal
# CLAIMS in verify_all.py).  The UNSAT half of each claim is the instance
# at N = a(n).
EXPECTED = {28: 35, 29: 41, 30: 36, 31: 41, 32: 41, 33: 37, 34: 42, 35: 44,
          36: 37}

# Terms carried by the lazy encoding (rado/lazy.py), where the full support
# build is not a laptop job: n -> a(n).  Must equal LAZY_CLAIMS in
# verify_all.py.  Certifying one of these rebuilds the formula from the
# recorded justifications rather than from a stored CNF, so the proof is
# replayed against clauses that were re-derived from arithmetic.
LAZY_EXPECTED = {37: 45, 38: 47, 39: 52, 40: 47, 41: 47, 42: 54, 43: 48,
                 44: 56, 45: 56, 46: 50, 47: 57, 48: 58, 49: 51, 50: 60,
                 51: 67, 52: 59, 53: 60, 54: 68, 55: 61, 56: 62, 57: 70,
                 58: 63, 59: 72, 60: 71}


def find_tools(kissat=None, drat_trim=None):
    found, missing = {}, []
    for key, explicit, env, exe in (
            ('kissat', kissat, 'KISSAT', 'kissat'),
            ('drat_trim', drat_trim, 'DRAT_TRIM', 'drat-trim')):
        path = explicit or os.environ.get(env) or shutil.which(exe)
        if path and os.path.exists(path):
            found[key] = path
        elif path and shutil.which(path):
            found[key] = shutil.which(path)
        else:
            missing.append(exe)
    return found, missing


def rebuild_lazy_formula(path, n, N):
    """Re-derive the lazy clause set from its recorded justifications.

    Each clause arrives with an explicit solution.  The arithmetic is
    re-checked here and the clause re-derived from the solution, so what the
    proof is replayed against never passes through the search that found it.
    A clause with a valid justification is one the full support encoding
    emits, which is what makes UNSAT here an UNSAT of the full instance.
    """
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'evidence', f'lazy_n{n}_N{N}.json')
    with open(src, encoding='utf-8') as fh:
        doc = json.load(fh)
    supports, problems = [], []
    for j in doc['justifications']:
        pairs, z = j['x'], j['z']
        if not lazy.check_justification(pairs, z, n, N):
            problems.append(f'x={pairs} z={z} is not a solution for n={n} '
                            f'in [1,{N}]')
        derived = sorted({v for v, _c in pairs} | {z})
        if derived != sorted(j['support']):
            problems.append(f'x={pairs} z={z}: support {j["support"]} '
                            f'!= {derived}')
        supports.append(derived)
    lazy.write_cnf(path, N, supports)
    return N, 2 * len(supports), len(supports), problems


def certify(n, N, mode, tools, workdir, timeout=None):
    formula = os.path.join(workdir, f'f_n{n}_N{N}_{mode}.cnf')
    proof = os.path.join(workdir, f'p_n{n}_N{N}_{mode}.drat')
    rec = {'seq': 'A250026', 'n': n, 'N': N, 'mode': mode,
           'convention': {'distinct': False, 'z_colored': True}}
    t0 = time.time()
    if mode == 'lazy':
        nv, nc, nsup, problems = rebuild_lazy_formula(formula, n, N)
        rec['justifications_ok'] = not problems
        if problems:
            rec.update(verdict='BAD_JUSTIFICATION', detail='; '.join(
                problems[:3]), build_s=round(time.time() - t0, 1))
            return rec
    else:
        nv, nc, nsup = encode.write_dimacs(formula, n, N, mode=mode)
    rec.update(vars=nv, clauses=nc, build_s=round(time.time() - t0, 1))

    t0 = time.time()
    try:
        solve = subprocess.run(
            [tools['kissat'], '-q', '--no-binary', formula, proof],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        rec.update(verdict='TIMEOUT', solve_s=round(time.time() - t0, 1))
        return rec
    rec['solve_s'] = round(time.time() - t0, 1)
    if solve.returncode == 10:
        # Not an error in this script: it means the UNSAT claim itself is
        # false, the single most important thing this could ever discover.
        rec['verdict'] = 'SAT'
        return rec
    if solve.returncode != 20:
        rec['verdict'] = 'SOLVER_ERROR'
        rec['detail'] = (solve.stderr or solve.stdout or '').strip()[-400:]
        return rec
    rec['proof_mb'] = round(os.path.getsize(proof) / 1e6, 2)

    t0 = time.time()
    try:
        chk = subprocess.run([tools['drat_trim'], formula, proof],
                             capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        rec.update(verdict='TIMEOUT', check_s=round(time.time() - t0, 1))
        return rec
    rec['check_s'] = round(time.time() - t0, 1)
    out = chk.stdout or ''
    if 's VERIFIED' in out:
        rec['verdict'] = 'VERIFIED'
    elif 's NOT VERIFIED' in out:
        rec['verdict'] = 'NOT_VERIFIED'
        rec['detail'] = out.strip()[-400:]
    else:
        rec['verdict'] = 'SOLVER_ERROR'
        rec['detail'] = (out + (chk.stderr or '')).strip()[-400:]
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, help='certify the refutation for this n')
    ap.add_argument('--N', type=int, help='at this N (default: the published a(n))')
    ap.add_argument('--mode', default='support',
                    choices=['support', 'reach', 'lazy'])
    ap.add_argument('--all', action='store_true',
                    help='certify every entry of EXPECTED in --mode')
    ap.add_argument('--timeout', type=float)
    ap.add_argument('--keep', metavar='DIR', help='keep CNF and proof here')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--kissat')
    ap.add_argument('--drat-trim', dest='drat_trim')
    args = ap.parse_args()

    tools, missing = find_tools(args.kissat, args.drat_trim)
    if missing:
        print(f'DRAT tools not installed: {", ".join(missing)} not found on '
              f'PATH or in KISSAT / DRAT_TRIM. Nothing was checked.',
              file=sys.stderr)
        return TOOLS_MISSING

    table = LAZY_EXPECTED if args.mode == 'lazy' else EXPECTED
    if args.all:
        jobs = [(n, table[n]) for n in sorted(table)]
    elif args.n is not None:
        jobs = [(args.n, args.N if args.N else table[args.n])]
    else:
        raise SystemExit('give --n or --all')

    workdir = args.keep or tempfile.mkdtemp(prefix='rado_drat_')
    os.makedirs(workdir, exist_ok=True)
    results, bad = [], False
    try:
        for n, N in jobs:
            rec = certify(n, N, args.mode, tools, workdir, args.timeout)
            results.append(rec)
            if rec['verdict'] != 'VERIFIED':
                bad = True
            if not args.json:
                print(f"n={n} N={N} [{args.mode}]: {rec['verdict']:<13}"
                      f" build {rec.get('build_s', '-')}s"
                      f" solve {rec.get('solve_s', '-')}s"
                      f" proof {rec.get('proof_mb', '-')}MB"
                      f" check {rec.get('check_s', '-')}s", flush=True)
                if rec.get('detail'):
                    print(f"    {rec['detail']}")
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
    if args.json:
        print(json.dumps(results, indent=1))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
