# Mutation-guided unit tests

Eight pytest files, shared small arithmetic fixtures in `conftest.py`, and a
reproducible mutation runner with per-mutant results in
`mutation_results.json`. The CI gate job installs pytest 8.4.2 and runs
`pytest -q`. There are no new runtime dependencies.

## Measurement

The runner tries 53 targeted semantic mutations across eight modules. Each
mutation replaces one unique fragment, is compiled first, and runs in a
temporary project copy inside the repository. The source is restored before
the next mutation. Mutations include comparison boundaries, count offsets,
condition negation, clause omission, polarity changes and bypassed validation.

Before: run the original `python rado/verify_all.py` and
`python tools/oeis_lint.py --selftest` for every mutant. Both must pass on the
unmutated checkout (430/430 and 47/47); a mutant is killed if either fails.

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
| `rado/drat_certify.py` | 8 | 0 | 8 |
| `rado/verify_all.py` | 5 | 0 | 5 |
| `tools/oeis_lint.py` | 5 | 1 | 5 |
| **Total** | **53** | **9** | **53** |

These counts describe the selected mutants, not an exhaustive mutation score.
The JSON records each source fragment, replacement, line, gate and linter exit
codes, pytest command, exit code and failure output.

## A killed mutant for every new test file

| Test file | Mutation and location | Regression checked |
| --- | --- | --- |
| `test_witness.py` | `verify_witness.py:75`: replace the alphabet check with `if False` | A witness containing `x` must be rejected; valid witnesses and one changed color are checked too. |
| `test_lazy.py` | `lazy.py:138`: `count < 1` to `count < 0` | An extra zero-count pair must be rejected even when the count and square totals remain exact. |
| `test_encode.py` | `encode.py:245`: `(-s * z, -r)` to `(s * z, -r)` | For every small coloring, the reach circuit must agree with directly enumerated arithmetic solutions. |
| `test_brute_force.py` | `brute_force.py:70`: return `c` instead of `c + 1` | The first good coloring has the correct witness and exact number of examined colorings. |
| `test_solve.py` | `solve.py:54`: bypass `if missing` | An incomplete model must raise `ValueError`, including a model missing its final color variable. |
| `test_certificates.py` | `drat_certify.py`: test `'s VERIFIED' in out` instead of whole status lines | Output whose only mention of `s VERIFIED` is inside a comment must not certify. `s NOT VERIFIED` must reject the refutation, even after such a comment. |
| `test_gate.py` | `verify_all.py:239`: `clauses > 0` to `clauses >= 0` | Removing all clauses and setting the recorded count to zero must fail the evidence gate. |
| `test_oeis_lint.py` | `oeis_lint.py:338`: remove `remaining.remove(o)` | Preservation must count duplicate lines, so removing one copy is detected. |

All eight examples survived the original checks. The suite also tests valid
inputs for each verifier, altered values, wrong counts, removed supports,
truncated JSON/model files, failed replay output, timeouts, solver errors,
lazy search progress, bisection boundaries, and both encoding polarities.

## Bug found

The mutation work found a soundness bug in `drat_certify.certify`: it
accepted the substring `s VERIFIED` anywhere in drat-trim's output, so a
failed replay could be recorded as verified. It now reads whole status lines
and checks `s NOT VERIFIED` first. The `certificates` workflow re-replayed
every stored proof with the fix and all passed.

## Commands and results

```sh
python -m venv .venv
.venv/bin/python -m pip install pytest==8.4.2 ruff==0.16.1
.venv/bin/python tests/mutation_check.py before
.venv/bin/python tests/mutation_check.py after
```

Both measurement commands complete with exit 0. The original checks kill
9/53 mutants; the new pytest files kill all 53, including the 44 original
survivors. No measurement timeouts, no surviving mutants.

| Check | Result |
| --- | --- |
| `pytest -q` | 149 passed in under a second; slowest test 0.04 s |
| `python rado/verify_all.py` | 430 passed, 0 failed (SAT/UNSAT re-solves and DRAT replay skipped: kissat and drat-trim absent, so this does not certify DRAT proofs) |
| `python tools/oeis_lint.py --selftest` | 47 cases, 47 passed, 0 failed |
| `ruff check .` | All checks passed |
| `git diff --check` | clean |

Measured with Python 3.13, the version CI uses.
