"""Timeboxed probe of an unpublished term: how hard is a(n), and where is it?

This is a PROBE, not a claim: it runs SAT/UNSAT bisection on N under a hard
wall-clock budget, kills the solver at the deadline, and records exactly how
far it got.  a(n) = least N with UNSAT; satisfiability is monotone in N (a
good coloring of [1,N] restricts to [1,N-1]), so bisection is sound.

The reach encoding is used because its build time is polynomial in N (the
support enumeration, fine at n<=30, is the slow half at larger n).  The two
encodings are proven to agree on every reproduction instance by verify_all.py.

    python probe.py --n 31 --budget 900 --json evidence/probe_a31.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import encode            # noqa: E402
import solve as solve_mod  # noqa: E402
import verify_witness    # noqa: E402


def probe(n, budget_s, kissat, lo=2, cap=80, mode='reach'):
    """Bisect for a(n) within [lo, cap] under budget_s seconds total."""
    t_start = time.time()
    log = []
    last_sat, first_unsat = lo, None
    witnesses = {}

    def left():
        return budget_s - (time.time() - t_start)

    def run(N):
        rec = {'N': N}
        t0 = time.time()
        try:
            r = solve_mod.solve_instance(n, N, mode=mode, kissat=kissat,
                                         timeout=max(1.0, left()))
        except Exception as exc:            # noqa: BLE001 - probe must record
            rec.update(verdict='ERROR', detail=str(exc)[:200])
            log.append(rec)
            return None
        rec.update(verdict=r['verdict'], build_s=r.get('build_s'),
                   solve_s=r.get('solve_s'), clauses=r.get('clauses'))
        log.append(rec)
        if r['sat'] is True and r['verdict'] == 'SAT_WITNESS_VERIFIED':
            witnesses[N] = r['coloring']
            return True
        if r['sat'] is False:
            return False
        return None                          # timeout / error

    # Phase 1: find some UNSAT N (upper end first, since a(29)=41).  If the
    # cap itself comes back SAT the probe is UNRESOLVED, not "a(n) > cap
    # therefore stop": a(39)=52 was missed entirely by the original cap of
    # 50 and only appeared when the cap was raised, so `cap` is recorded in
    # the output and its default is deliberately generous.
    for N in (41, 46, cap):
        if left() <= 5:
            break
        if N <= last_sat:
            continue
        res = run(N)
        if res is False:
            first_unsat = N
            break
        if res is True:
            last_sat = max(last_sat, N)
        if res is None:
            break
    # Phase 2: bisect.
    while first_unsat is not None and first_unsat - last_sat > 1 and left() > 5:
        mid = (last_sat + first_unsat) // 2
        res = run(mid)
        if res is True:
            last_sat = mid
        elif res is False:
            first_unsat = mid
        else:
            break
    out = {
        'seq': 'A250026', 'n': n, 'mode': mode,
        'convention': {'distinct': False, 'z_colored': True},
        'budget_s': budget_s, 'cap': cap,
        'used_s': round(time.time() - t_start, 1),
        'last_sat_N': last_sat, 'first_unsat_N': first_unsat,
        'resolved': (first_unsat is not None
                     and first_unsat - last_sat == 1),
        'log': log,
    }
    if out['resolved']:
        out['a_n_if_confirmed'] = first_unsat
        out['note'] = ('PROBE ONLY: bisection under a timebox; a claim '
                       'would need the full evidence pipeline of this repo')
        w = witnesses.get(last_sat)
        if w is not None:
            out['witness_at_last_sat'] = w
            ok, msg = verify_witness.check_witness(
                {'n': n, 'N': last_sat, 'sat': True, 'coloring': w})
            out['witness_check'] = msg
            if not ok:
                out['resolved'] = False
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--budget', type=float, default=900.0)
    ap.add_argument('--cap', type=int, default=80)
    ap.add_argument('--kissat')
    ap.add_argument('--json')
    args = ap.parse_args()
    kis = solve_mod.find_kissat(args.kissat)
    if kis is None:
        print('kissat not found (flag --kissat, env KISSAT, or PATH)',
              file=sys.stderr)
        return 3
    out = probe(args.n, args.budget, kis, cap=args.cap)
    print(json.dumps(out, indent=1))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='ascii', newline='\n') as fh:
            json.dump(out, fh, indent=1)
            fh.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
