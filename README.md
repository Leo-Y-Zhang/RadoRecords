# RadoRecords

Computational evidence for 2-color Rado numbers of the equation
`x_1^2 + x_2^2 + ... + x_n^2 = z^2` — the family behind OEIS
[A250026](https://oeis.org/A250026) (Myers 2014; Myers & Parrish,
*Some Nonlinear Rado Numbers*, Integers 18B (2018), #A6).

`a(n)` is the least `N` such that **every** 2-coloring of `{1,...,N}`
contains a monochromatic solution: all `n+1` values `x_1,...,x_n,z` lie in
`[1,N]` and share one color. Variables need not be distinct (Myers's
convention; `a(1)=1` via `x_1=z=1`).

## What is established here

This began as the pre-flight reproduction for an extension campaign — the
last three published terms re-derived from scratch, twice — and became the
extension: A250026 is published only to a(30), and every value from a(31)
on below is new.

A term is **claimed** here only if it clears the whole bar: a SAT witness at
N = a(n)-1 re-checked by a solver-free checker, a drat-trim-verified UNSAT
at N = a(n), *both* independent encodings agreeing, and the cold gate green
with the term in `CLAIMS`.

| term | UNSAT at | SAT at | status |
|------|----------|--------|--------|
| a(28) = 35 | N=35 | N=34 | reproduced, both encodings, DRAT-certified |
| a(29) = 41 | N=41 | N=40 | reproduced, both encodings, DRAT-certified |
| a(30) = 36 | N=36 | N=35 | reproduced, both encodings, DRAT-certified |
| a(31) = 41 | N=41 | N=40 | **NEW**, both encodings, DRAT-certified |
| a(32) = 41 | N=41 | N=40 | **NEW**, both encodings, DRAT-certified |
| a(33) = 37 | N=37 | N=36 | **NEW**, both encodings, DRAT-certified |
| a(34) = 42 | N=42 | N=41 | **NEW**, both encodings, DRAT-certified |
| a(35) = 44 | N=44 | N=43 | **NEW**, both encodings, DRAT-certified |
| a(36) = 37 | N=37 | N=36 | **NEW**, both encodings, DRAT-certified |

and then, on the `lazy` encoding described below, with `reach` agreeing at
both endpoints and a drat-trim-verified refutation for each:

| a(37) = 45 | a(41) = 47 | a(45) = 56 | a(49) = 51 | a(53) = 60 | a(57) = 70 |
| a(38) = 47 | a(42) = 54 | a(46) = 50 | a(50) = 60 | a(54) = 68 | a(58) = 63 |
| a(39) = 52 | a(43) = 48 | a(47) = 57 | a(51) = 67 | a(55) = 61 | a(59) = 72 |
| a(40) = 47 | a(44) = 56 | a(48) = 58 | a(52) = 59 | a(56) = 62 | a(60) = 71 |

a(59) = 72 is the largest value anywhere in the sequence apart from
a(2) = 7825 and a(3) = 105, and the values stay wildly non-monotone
throughout: a(49) = 51 sits between a(48) = 58 and a(50) = 60.

## What the third encoding changed

The `support` encoding writes one clause pair per distinct solution support.
At n = 37, N = 45 that is 19,516,162 supports and 39,032,324 clauses, and the
Python that writes them takes 41 minutes before a solver starts. That build
cost, not the solver, is what had stopped the campaign at a(36).

Almost every one of those clauses is dead weight. If support T is a subset of
support S then clause(T) subsumes clause(S), and the inclusion-minimal
fraction, measured on instances small enough to enumerate whole, is 158x at
n = 28, 188x at n = 28/N = 35, 231x at n = 30 and 252x at n = 33 — the
redundancy grows with n. `rado/lazy.py` therefore never enumerates: it solves
the clauses found so far, and when the solver returns a coloring it hands that
coloring to the solver-free checker, which either accepts it (the instance is
SAT) or returns a monochromatic solution, whose support becomes the next
clause. a(60) needs 288 clauses. a(37) needs 218, against 39,032,324.

Both exits stay sound without trusting that search:

- **UNSAT** rests on subset-hood. Every clause is recorded with an explicit
  solution — the multiset of x values and z — and a clause whose solution
  checks out arithmetically is by definition one the full encoding emits. So
  the refutation refutes a subset of the full instance, and the full instance
  is UNSAT too. The gate re-does that arithmetic for every clause of every
  claim, and `rado/drat_certify.py --mode lazy` rebuilds the formula from the
  justifications before replaying the proof against it, so the proof is never
  checked against a file the search produced.
- **SAT** rests on `verify_witness.py`, which reads the equation rather than
  the CNF, exactly as it always did.

The method was not adopted on that argument alone. It reproduces every
published value a(3)..a(30) and every term this repository had already claimed
with the full encoding, both polarities, 68 endpoints, in 47 seconds.

**An earlier revision of this file reported a kissat allocation ceiling
"between 22M and 39M clauses" and left a(37)..a(40) unclaimed because of it.
That was wrong.** The support instance at n = 35, N = 44 solved at 29,639,268
clauses, not 22,088,930 — that figure is the N = 43 row — and kissat parses and
solves a 47,000,000-clause, 1.5 GB instance on this machine in 14 seconds. The
n = 37 run died silently at 0.2 s with empty output; every genuine kissat error
writes to stderr and exits 1. `solve.py` never recorded the return code that
would have distinguished a crash from a refusal, so the evidence could not tell
them apart. The failure was transient, the ceiling did not exist, and the terms
it was blocking were reachable all along.

The convention is additionally pinned, with no solver in the loop, by
pure-Python exhaustion over all colorings reproducing the published
`a(5)=23, a(6)=18, a(9)=15, a(10)=16`; and the `reach` encoding alone
reproduces all thirteen published values a(18)..a(30) as a control group.

See `PREFLIGHT.md` for the pinned convention, the rejected variants, the
probes, the timings and the full evidence round for every term.

## Layout

- `rado/encode.py` — two independent CNF encodings: `support` (one clause
  pair per distinct solution support, enumerated by a bitset DP; naive
  multiset enumeration would be 10^8–10^9 items) and `reach` (a monotone
  encoding of the reachability DP itself, polynomial size).
- `rado/lazy.py` — the third encoding: generates support clauses on demand
  from the checker's counterexamples, recording the solution that justifies
  each one. Decides an endpoint in hundreds of clauses instead of millions.
- `rado/verify_witness.py` — solver-free check of a claimed good coloring,
  by an algorithm sharing nothing with the encoder.
- `rado/brute_force.py` — exhaustive small-`N` ground truth.
- `rado/solve.py` — build + kissat + witness extraction; writes evidence JSON.
- `rado/drat_certify.py` — kissat `--no-binary` proof, replayed under
  drat-trim; only the literal line `s VERIFIED` counts.
- `rado/probe.py` — timeboxed bisection probe of an unpublished term.
- `rado/evidence/` — the JSON records every claim rests on.
- `rado/verify_all.py` — the gate: re-checks every claim from scratch.

## Verifying

```
python rado/verify_all.py          # full gate
python rado/verify_all.py --fast   # skips the slow support-mode re-solves
```

Sections needing SAT tooling locate `kissat` / `drat-trim` via the `KISSAT`
and `DRAT_TRIM` environment variables, `--kissat`/`--drat-trim` flags, or
`PATH`, and skip loudly when absent — a clean clone with no solver still
passes on the solver-free evidence.

Continuous integration runs exactly that solver-free half on every push: 380
checks in about two seconds, plus the submission linter's own 46-case fixture
suite. **A green run is not a re-certification.** Proof files are regenerated
rather than stored, so the DRAT ladder needs kissat present to produce them and
takes far longer than a CI job should; it stays a local step.

## Honest limits

- The reproductions match the published values; they are reproductions, not
  new results.
- The new terms are stated only because they cleared the full pipeline
  (both encodings, independent witness check, DRAT certificates).
  **`a(31) = 41` is published**: approved at OEIS on 2026-08-14 and now part
  of A250026. **`a(32)` to `a(60)` are a proposed draft** awaiting an editor
  as of 2026-08-15. Until a term is approved it is this repository's claim,
  not a published value, and this paragraph is checked against the live entry
  rather than remembered.
- a(37) and above rest on `lazy` plus `reach`, not on the full `support`
  build. `lazy` emits a subset of `support`'s clauses and the gate re-checks,
  by arithmetic, that every clause it emitted is one of them — so an UNSAT
  there is an UNSAT of the full instance. That is a proof, not an
  approximation, but it is a different route to the same claim and worth
  naming as such.
- The sequence is only claimed to a(60) because that is where this stopped,
  not because anything obstructs a(61). Each further term costs seconds.
- UNSAT results are certified DRAT proofs of the *encoded* CNFs; the link
  from CNF to definition rests on the brute-force agreement checks and on
  two unrelated encodings agreeing everywhere they were both run.
