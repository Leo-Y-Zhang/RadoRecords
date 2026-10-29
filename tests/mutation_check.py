"""Targeted, one-at-a-time mutation measurement, without editing project sources.

Run with the same Python that has pytest installed:
    python tests/mutation_check.py before
    python tests/mutation_check.py after

The before phase runs the existing solver-free gate and linter selftest.
Both must pass unmutated; a mutant is killed if either then fails. The after
phase runs the relevant pytest file for every mutant, including those killed
by the gate. Copies stay in a temporary directory inside the repository; no
solver or network is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'tests' / 'mutation_results.json'

# Each tuple replaces exactly one unique source fragment. These are semantic
# mutations of validation, arithmetic, boundaries, polarity and control flow.
MUTATIONS = {
    'rado/verify_witness.py': [
        ('sat-identity', "if doc['sat'] is not True:", "if doc['sat'] is False:"),
        ('long-coloring', 'len(coloring) != N:', 'len(coloring) < N:'),
        ('alphabet', "if set(coloring) - set('01'):", 'if False:'),
        ('missing-field', "('n', 'N', 'sat', 'coloring')", "('n', 'N', 'sat')"),
        ('dp-count', 'for _ in range(n):', 'for _ in range(n - 1):'),
        ('color-1-only', "for color in '01':", "for color in '1':"),
    ],
    'rado/lazy.py': [
        ('zero-count', 'count < 1 or not', 'count < 0 or not'),
        ('zero-value', 'not 1 <= v <= N', 'not 0 <= v <= N'),
        ('z-upper-bound', 'not 1 <= z <= N:', 'not 1 <= z <= N + 1:'),
        ('z-type', 'if not is_int(z) or not all', 'if not all'),
        ('boolean-integer', 'type(v) is int', 'isinstance(v, int)'),
        ('wrong-count', 'pairs) != n:', 'pairs) == n:'),
        ('wrong-squares', 'pairs) == z * z', 'pairs) != z * z'),
        ('reconstruct-count', 'for _ in range(n):', 'for _ in range(n - 1):'),
        ('multiset-count', 'counts.get(v, 0) + 1', 'counts.get(v, 0) - 1'),
        ('clause-polarity', "str(-v) for v in s", "str(v) for v in s"),
        ('bisect-boundary', 'while hi - lo > 1:', 'while hi - lo > 2:'),
        ('bisect-polarity', "cache[N]['sat'] is False", "cache[N]['sat'] is True"),
    ],
    'rado/encode.py': [
        ('support-boundary', 'if t * v2 > target:', 'if t * v2 >= target:'),
        ('distinct-boundary', 'if v < k:', 'if v <= k:'),
        ('reach-target', 'if z * z >= n and', 'if z * z > n and'),
        ('reach-premise', '(-s * v, -pre, r)', '(-s * v, pre, r)'),
        ('reach-z-polarity', '(-s * z, -r)', '(s * z, -r)'),
        ('support-polarity', 'neg = tuple(-v for v in sup)', 'neg = tuple(v for v in sup)'),
        ('dimacs-count', "f'p cnf {N} {2 * nsup}\\n'", "f'p cnf {N} {2 * nsup + 1}\\n'"),
        ('drop-clause', "chunk.append(' '.join(map(str, neg)) + ' 0')", 'pass'),
    ],
    'rado/brute_force.py': [
        ('mask-index', 'm |= 1 << (v - 1)', 'm |= 1 << v'),
        ('monochromatic-or', 'if x == m or x == 0:', 'if x == m and x == 0:'),
        ('checked-count', 'return True, witness, c + 1', 'return True, witness, c'),
        ('budget-direction', 'time.time() - t0 > budget_s', 'time.time() - t0 < budget_s'),
    ],
    'rado/solve.py': [
        ('model-sign', 'val[abs(lit)] = lit > 0', 'val[abs(lit)] = lit < 0'),
        ('missing-model', 'if missing:', 'if False:'),
        ('model-length', "for i in range(1, N + 1))", "for i in range(1, N))"),
        ('accept-bad-witness', "if ok else 'WITNESS_REJECTED'", "if True else 'WITNESS_REJECTED'"),
        ('unsat-exit', 'elif r.returncode == 20:', 'elif r.returncode == 0:'),
    ],
    'rado/drat_certify.py': [
        ('skip-arithmetic', 'if not lazy.check_justification(pairs, z, n, N):', 'if False:'),
        ('support-comparison', "if derived != sorted(j['support']):", "if derived == sorted(j['support']):"),
        ('drop-z', 'sorted({v for v, _c in pairs} | {z})', 'sorted({v for v, _c in pairs})'),
        ('ignore-problems', 'if problems:\n', 'if False:\n'),
        ('verification-marker', "elif 's VERIFIED' in status:", "elif 's VERIFIED' in out:"),
        ('any-output', "elif 's VERIFIED' in status:", 'elif out:'),
        ('failure-first', "if 's NOT VERIFIED' in status:", 'if False:'),
        ('unsat-exit', 'if solve.returncode != 20:', 'if solve.returncode != 0:'),
    ],
    'rado/verify_all.py': [
        ('empty-clauses', "and ref['clauses'] > 0", "and ref['clauses'] >= 0"),
        ('clause-count', "ref['clauses'] == 2 * len(ref['justifications'])", "ref['clauses'] >= 2 * len(ref['justifications'])"),
        ('reach-N', "d['N'] == want", "d['N'] <= want"),
        ('reach-convention', "and d['convention']['z_colored'] is True\n                      for d, want", "and d['convention']['z_colored'] is not None\n                      for d, want"),
        ('reach-witness', 'r_good[0], fail_detail=r_good[1]', 'True, fail_detail=r_good[1]'),
    ],
    'tools/oeis_lint.py': [
        ('lost-duplicate', 'remaining.remove(o)', 'pass'),
        ('leap-day', '1 <= day <= calendar.monthrange(year, m)[1]', '1 <= day < calendar.monthrange(year, m)[1]'),
        ('min-terms', 'if len(post_terms) < 4:', 'if len(post_terms) <= 4:'),
        ('term-prefix', 'if post_terms[:len(old_terms)] != old_terms:', 'if post_terms[:len(old_terms)] == old_terms:'),
        ('parse-offset', 'offset = int(mo.group(1)) if mo else None', 'offset = abs(int(mo.group(1))) if mo else None'),
    ],
}

TEST_FILES = {
    'rado/verify_witness.py': 'tests/test_witness.py',
    'rado/lazy.py': 'tests/test_lazy.py',
    'rado/encode.py': 'tests/test_encode.py',
    'rado/brute_force.py': 'tests/test_brute_force.py',
    'rado/solve.py': 'tests/test_solve.py',
    'rado/drat_certify.py': 'tests/test_certificates.py',
    'rado/verify_all.py': 'tests/test_gate.py',
    'tools/oeis_lint.py': 'tests/test_oeis_lint.py',
}


def run(args, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    # Intentionally nonexistent tools keep the gate solver-free on any host.
    env.update(KISSAT='/nonexistent/kissat', DRAT_TRIM='/nonexistent/drat-trim')
    try:
        result = subprocess.run([sys.executable, *args], cwd=cwd, env=env,
                                capture_output=True, text=True, timeout=60)
        return {'returncode': result.returncode,
                'output': result.stdout + result.stderr}
    except subprocess.TimeoutExpired:
        return {'returncode': 'timeout', 'output': '60 second timeout'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('before', 'after'))
    args = parser.parse_args()
    if args.phase == 'before':
        gate = run(['rado/verify_all.py'], ROOT)
        linter = run(['tools/oeis_lint.py', '--selftest'], ROOT)
        if gate['returncode'] != 0 or linter['returncode'] != 0:
            raise SystemExit('The unmutated gate and linter selftest must pass first')
        results = {'baseline_gate': gate, 'baseline_linter': linter, 'mutants': []}
    else:
        results = json.loads(RESULTS.read_text(encoding='utf-8'))
        clean = run(['-m', 'pytest', '-q', 'tests'], ROOT)
        if clean['returncode'] != 0:
            raise SystemExit(clean['output'])
        results['baseline_pytest'] = clean
    with tempfile.TemporaryDirectory(prefix='.mutation-', dir=ROOT) as tmp:
        work = Path(tmp)
        for directory in ('rado', 'tools', 'tests'):
            shutil.copytree(ROOT / directory, work / directory,
                            ignore=shutil.ignore_patterns('__pycache__',
                                                         'mutation_results.json'))
        for filename in ('README.md', 'PREFLIGHT.md', 'ruff.toml'):
            shutil.copy2(ROOT / filename, work / filename)
        for module, mutations in MUTATIONS.items():
            for name, old, new in mutations:
                source = (work / module).read_text(encoding='utf-8')
                if source.count(old) != 1:
                    raise SystemExit(f'{module}:{name}: expected one source match')
                mutated = source.replace(old, new, 1)
                compile(mutated, module, 'exec')
                (work / module).write_text(mutated, encoding='utf-8')
                if args.phase == 'before':
                    gate = run(['rado/verify_all.py'], work)
                    lint = run(['tools/oeis_lint.py', '--selftest'], work)
                    record = {'module': module, 'name': name,
                              'line': source[:source.index(old)].count('\n') + 1,
                              'old': old, 'new': new,
                              'killed_before': gate['returncode'] != 0
                              or lint['returncode'] != 0,
                              'gate_returncode': gate['returncode'],
                              'linter_returncode': lint['returncode']}
                    results['mutants'].append(record)
                else:
                    record = next(r for r in results['mutants']
                                  if r['module'] == module and r['name'] == name)
                    command = ['-m', 'pytest', '-q', '-x', '--tb=short', TEST_FILES[module]]
                    pytest = run(command, work)
                    record['pytest_command'] = command
                    record['pytest_returncode'] = pytest['returncode']
                    record['pytest_output'] = pytest['output']
                    record['killed_after'] = record['killed_before'] or pytest['returncode'] != 0
                killed = record['killed_' + args.phase]
                print(f'{module}:{name}: {"KILLED" if killed else "SURVIVED"}', flush=True)
                # Restore this source before trying the next independent mutant.
                (work / module).write_text(source, encoding='utf-8')
                RESULTS.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    counts = Counter(r['module'] for r in results['mutants'])
    for module, count in counts.items():
        before = sum(r['killed_before'] for r in results['mutants'] if r['module'] == module)
        after = sum(r.get('killed_after', False) for r in results['mutants'] if r['module'] == module)
        print(f'{module}: tried={count}, before={before}, after={after}')


if __name__ == '__main__':
    main()
