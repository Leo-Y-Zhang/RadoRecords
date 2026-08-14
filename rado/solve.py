"""Build an instance, run kissat, and record the outcome as evidence JSON.

Solver location: --kissat flag, else KISSAT env var, else `kissat` on PATH.
No machine-specific path is baked in.

    python solve.py --n 28 --N 34 --mode support --json evidence/w.json

On SAT the witness coloring is extracted from the model, immediately
re-checked by the independent solver-free checker in verify_witness.py, and
only then written.  On UNSAT the JSON records sat=false.  Exit codes:
0 = solved (either way) and any witness passed the independent check,
1 = something is wrong (solver error, witness rejected), 3 = kissat missing.
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

import encode            # noqa: E402
import verify_witness    # noqa: E402

TOOLS_MISSING = 3


def find_kissat(explicit=None):
    path = explicit or os.environ.get('KISSAT') or shutil.which('kissat')
    if path and os.path.exists(path):
        return path
    if path and shutil.which(path):
        return shutil.which(path)
    return None


def parse_model(stdout, N):
    """Colors of 1..N from kissat 'v' lines: '1' where the var is true."""
    lits = []
    for line in stdout.splitlines():
        if line.startswith('v '):
            lits.extend(int(t) for t in line[2:].split())
    val = {}
    for lit in lits:
        if lit == 0:
            continue
        val[abs(lit)] = lit > 0
    missing = [i for i in range(1, N + 1) if i not in val]
    if missing:
        raise ValueError(f'model does not assign color variables {missing[:5]}')
    return ''.join('1' if val[i] else '0' for i in range(1, N + 1))


def solve_instance(n, N, mode='support', distinct=False, z_colored=True,
                   kissat=None, workdir=None, timeout=None, keep_cnf=None):
    """Returns a record dict; record['sat'] is True/False/None(timeout)."""
    kis = find_kissat(kissat)
    if kis is None:
        raise FileNotFoundError('kissat not found (flag --kissat, env KISSAT, or PATH)')
    own = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix='rado_')
    cnf = keep_cnf or os.path.join(workdir, f'a250026_n{n}_N{N}_{mode}.cnf')
    rec = {'seq': 'A250026', 'n': n, 'N': N, 'mode': mode,
           'convention': {'distinct': distinct, 'z_colored': z_colored,
                          'equation': 'x_1^2+...+x_n^2 = z^2',
                          'interval': '[1,N]'}}
    t0 = time.time()
    nv, nc, nsup = encode.write_dimacs(cnf, n, N, mode=mode,
                                       distinct=distinct, z_colored=z_colored)
    rec.update(vars=nv, clauses=nc, build_s=round(time.time() - t0, 1))
    if nsup is not None:
        rec['supports'] = nsup
    t0 = time.time()
    try:
        r = subprocess.run([kis, '-q', cnf], capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        rec.update(sat=None, verdict='TIMEOUT',
                   solve_s=round(time.time() - t0, 1))
        return rec
    finally:
        if own and not keep_cnf:
            shutil.rmtree(workdir, ignore_errors=True)
    rec['solve_s'] = round(time.time() - t0, 1)
    # Recorded always, and not only on failure: an exit that is neither 10 nor
    # 20 with empty output is a crash, while a refusal exits 1 with a message
    # on stderr.  A run of this that stored only stderr could not tell the two
    # apart, and a transient crash was read off it as a solver ceiling.
    rec['returncode'] = r.returncode
    if r.returncode == 10:
        rec['sat'] = True
        rec['coloring'] = parse_model(r.stdout, N)
        ok, msg = verify_witness.check_witness(rec)
        rec['witness_check'] = msg
        rec['verdict'] = 'SAT_WITNESS_VERIFIED' if ok else 'WITNESS_REJECTED'
    elif r.returncode == 20:
        rec['sat'] = False
        rec['verdict'] = 'UNSAT'
    else:
        rec['sat'] = None
        rec['verdict'] = 'SOLVER_ERROR'
        rec['detail'] = (r.stderr or r.stdout or '').strip()[-400:]
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--N', type=int, required=True)
    ap.add_argument('--mode', default='support', choices=['support', 'reach'])
    ap.add_argument('--distinct', action='store_true')
    ap.add_argument('--no-z-colored', dest='z_colored', action='store_false')
    ap.add_argument('--kissat')
    ap.add_argument('--timeout', type=float)
    ap.add_argument('--json', help='write the record here')
    ap.add_argument('--keep-cnf', help='also keep the DIMACS file here')
    args = ap.parse_args()
    try:
        rec = solve_instance(args.n, args.N, mode=args.mode,
                             distinct=args.distinct, z_colored=args.z_colored,
                             kissat=args.kissat, timeout=args.timeout,
                             keep_cnf=args.keep_cnf)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return TOOLS_MISSING
    print(json.dumps(rec, indent=1))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='ascii', newline='\n') as fh:
            json.dump(rec, fh, indent=1)
            fh.write('\n')
    return 0 if rec['verdict'] in ('SAT_WITNESS_VERIFIED', 'UNSAT') else 1


if __name__ == '__main__':
    sys.exit(main())
