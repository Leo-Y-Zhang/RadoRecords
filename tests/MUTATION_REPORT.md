# Mutation-guided unit tests

Added eight pytest files, shared small arithmetic fixtures in `conftest.py`,
and a reproducible mutation runner with per-mutant results in
`mutation_results.json`. The existing CI gate job now installs pytest 8.4.2
and runs `pytest -q`. No production Python or evidence files changed; no seam
was necessary. There are no new runtime dependencies.

## Measurement

The runner tries 52 targeted semantic mutations across eight modules. Each
mutation replaces one unique fragment, is compiled first, and runs in a
temporary project copy under `/work`. The source is restored before the next
mutation. Mutations include comparison boundaries, count offsets, condition
negation, clause omission, polarity changes and bypassed validation.

Before: run the original `python rado/verify_all.py` and
`python tools/oeis_lint.py --selftest` for every mutant. The unmodified linter
selftest already fails 33 of 47 cases in this checkout. Only regressions
among its 14 passing cases count as kills; its pre-existing failures never
count as kills.

After: run the relevant pytest file for every mutant, including those already
killed before. The table's after column is the union of the original checks
and the new tests. The unmutated full pytest suite is checked separately.
Tool environment overrides keep the gate solver-free, and all unit tests use
small arithmetic inputs or mocked subprocess responses. No SAT solving or
network access occurs during tests or mutation measurement.

| Module | Mutants tried | Killed before | Killed after |
| --- | ---: | ---: | ---: |
| `rado/verify_witness.py` | 6 | 2 | 6 |
| `rado/lazy.py` | 12 | 3 | 12 |
| `rado/encode.py` | 8 | 1 | 8 |
| `rado/brute_force.py` | 4 | 2 | 4 |
| `rado/solve.py` | 5 | 0 | 5 |
| `rado/drat_certify.py` | 7 | 0 | 7 |
| `rado/verify_all.py` | 5 | 0 | 5 |
| `tools/oeis_lint.py` | 5 | 1 | 5 |
| **Total** | **52** | **9** | **52** |

These counts describe the selected mutants, not an exhaustive mutation score.
The JSON records each source fragment, replacement, line, original gate
result, linter regressions, pytest command, exit code and failure output.

## A killed mutant for every new test file

| Test file | Mutation and location | Regression checked |
| --- | --- | --- |
| `test_witness.py` | `verify_witness.py:75`: replace the alphabet check with `if False` | A witness containing `x` must be rejected; valid witnesses and one changed color are checked too. |
| `test_lazy.py` | `lazy.py:138`: `count < 1` to `count < 0` | An extra zero-count pair must be rejected even when the count and square totals remain exact. |
| `test_encode.py` | `encode.py:245`: `(-s * z, -r)` to `(s * z, -r)` | For every small coloring, the reach circuit must agree with directly enumerated arithmetic solutions. |
| `test_brute_force.py` | `brute_force.py:70`: return `c` instead of `c + 1` | The first good coloring has the correct witness and exact number of examined colorings. |
| `test_solve.py` | `solve.py:54`: bypass `if missing` | An incomplete model must raise `ValueError`, including a model missing its final color variable. |
| `test_certificates.py` | `drat_certify.py:150`: match `VERIFIED` instead of `s VERIFIED` | `s NOT VERIFIED` must reject the refutation. Corrupted justifications and truncated files are also rejected. |
| `test_gate.py` | `verify_all.py:239`: `clauses > 0` to `clauses >= 0` | Removing all clauses and setting the recorded count to zero must fail the evidence gate. |
| `test_oeis_lint.py` | `oeis_lint.py:338`: remove `remaining.remove(o)` | Preservation must count duplicate lines, so removing one copy is detected. |

All eight examples survived the original checks. The suite also tests valid
inputs for each verifier, altered values, wrong counts, removed supports,
truncated JSON/model files, failed replay output, timeouts, solver errors,
lazy search progress, bisection boundaries, and both encoding polarities.

## Commands and results

Used a temporary virtual environment under `/work` because the container's
base interpreter has no pip module:

```sh
python -m venv --system-site-packages /work/.test-env
/work/.test-env/bin/python -m pip install pytest==8.4.2 ruff==0.16.1
```

The install succeeded. Mutation commands:

```sh
/work/.test-env/bin/python tests/mutation_check.py before
/work/.test-env/bin/python tests/mutation_check.py after
```

Both measurement commands completed with exit 0. The original checks killed
9/52 mutants; the new pytest files killed all 52, including the 43 original
survivors. There were no final measurement timeouts or surviving mutants.

Full `pytest -q` output (`/work/.test-env/bin/pytest -q`, exit 0):

```text
....................x................................................... [ 48%]
........................................................................ [ 97%]
....                                                                     [100%]
147 passed, 1 xfailed in 6.41s
```

A separate timing run of the same 148 cases, with `--durations=5`, finished
in 8.35 seconds; its slowest individual test call was 0.32 seconds. Every
test is below 2 seconds and the suite is below 60 seconds on this container.

`python rado/verify_all.py`: exit 0, **430 passed, 0 failed**. SAT/UNSAT
re-solves and DRAT replay explicitly skipped because kissat and drat-trim
are absent. This does not certify actual DRAT proofs.

`python tools/oeis_lint.py --selftest`: exit 1, **47 cases, 14 passed,
33 failed**, both before and after this change. These existing fixture
failures remain unchanged.

`/work/.test-env/bin/ruff check .`: exit 0, **All checks passed!**

`git diff --check`: exit 0, no whitespace errors.

## Left unchanged

One strict expected failure documents a real verifier bug:
`test_embedded_success_text_does_not_override_failed_replay`.
`drat_certify.certify` currently accepts a substring anywhere in stdout, so
`c previous s VERIFIED result` followed by `s NOT VERIFIED` is accepted.
The test requires rejection. Fixing production code is outside the task's
constraints. This expected failure does not kill mutants by itself.

Local checks used Python 3.11.2; CI remains configured for Python 3.13.
