# Pre-flight: reproducing A250026's frontier before extending it

Goal: before any attempt at a(31), rebuild the machinery from scratch and
prove it reproduces the last three published terms exactly. All three did:
a(28) = 35, a(29) = 41, a(30) = 36, each as UNSAT at N = a(n) plus an
independently re-checked SAT witness at N = a(n) - 1, in two unrelated CNF
encodings, with drat-trim-verified DRAT certificates for every UNSAT.

## The pinned convention

a(n) is the least N such that every 2-coloring of the integer interval
[1, N] contains a monochromatic solution of

    x_1^2 + x_2^2 + ... + x_n^2 = z^2

with ALL of x_1, ..., x_n, z in [1, N] and all n+1 of them the same color
(z is colored, same class as the x_i); variables need NOT be distinct
(repeats allowed among the x_i; for n >= 2, x_i < z is forced
arithmetically). Colored objects are the integers themselves, not their
squares. This is Definition 1 plus the Section-2 nondistinctness remark of
Myers & Parrish, Integers 18B (2018) #A6, and matches the A250026 example
line for a(3) = 105.

Pinned against SEVEN published values:

- solver-free (pure-Python exhaustion over all colorings, masks
  cross-checked against an independent per-coloring DP):
  a(5) = 23, a(6) = 18, a(9) = 15, a(10) = 16.
- solver (both encodings, witnesses re-checked solver-free):
  a(28) = 35, a(29) = 41, a(30) = 36.

## Rejected convention variants

- **distinct x_i** (some authors' convention): at n = 28, N = 35 the
  equation has ZERO solutions inside [1, 35] (the minimum sum of 28
  distinct squares is 7714 > 35^2), so the instance is trivially SAT,
  contradicting a(28) = 35. Same at (29, 41) and (30, 36); it also breaks
  the small terms (no solutions at n = 9, N = 15). Produces a(n) far above
  every published value. REJECTED.
- **z not colored** (monochromatic = the x_i only): degenerate — e.g. for
  n = 9 the multiset {1 x 9} solves 9 * 1^2 = 3^2 whatever color 3 has, so
  every coloring of [1, N >= 3] fails and the brute-force threshold is at
  most 8, against the published a(9) = 15 (n = 10: <= 9 vs 16;
  n = 6: <= 9 vs 18). REJECTED.
- The linear form x_1 + ... + x_{n-1} = z^2 guessed by an earlier draft
  brief was already ruled out by the entry's own example line before any
  computation; never encoded.

## Reproduction runs (wall seconds, this machine, single-threaded kissat)

Instance = (n, N). Expected: UNSAT at N = a(n), SAT at N = a(n) - 1.

### support encoding (one clause pair per distinct solution support)

| n | N | result | supports | clauses | build s | solve s |
|---|---|--------|----------|---------|---------|---------|
| 28 | 35 | UNSAT | 1,012,712 | 2,025,424 | 39.3 | 4.6 |
| 28 | 34 | SAT, witness verified | 733,061 | 1,466,122 | 37.8 | 0.3 |
| 29 | 41 | UNSAT | 6,434,668 | 12,869,336 | 458.2 | 15.3 |
| 29 | 40 | SAT, witness verified | 4,754,952 | 9,509,904 | 242.9 | 2.3 |
| 30 | 36 | UNSAT | 1,354,176 | 2,708,352 | 120.6 | 6.5 |
| 30 | 35 | SAT, witness verified | 982,782 | 1,965,564 | 74.1 | 0.5 |

Naive multiset enumeration would have been 3.7e7..6.9e8 solutions per
instance; the encoder enumerates distinct supports instead (a solution's
clause depends only on its support), via a bitset reachability DP and a
set-of-states recursion emitting each support exactly once, validated
against naive enumeration on small instances. Support enumeration is the
cost driver (458 s at n=29, N=41), which is why the reach encoding exists
and is what any campaign at n >= 31 should lead with.

### reach encoding (monotone reachability DP, polynomial size)

| n | N | result | clauses | build s | solve s |
|---|---|--------|---------|---------|---------|
| 28 | 35 | UNSAT | 1,236,830 | 0.7 | 2.7 |
| 28 | 34 | SAT, witness verified | 1,129,394 | 0.5 | 0.2 |
| 29 | 41 | UNSAT | 2,108,958 | 1.0 | 5.6 |
| 29 | 40 | SAT, witness verified | 1,954,074 | 1.0 | 0.4 |
| 30 | 36 | UNSAT | 1,464,136 | 0.7 | 3.0 |
| 30 | 35 | SAT, witness verified | 1,339,858 | 0.6 | 0.2 |

Both encodings agree on every instance above and on every small-N /
brute-force comparison; SAT witnesses are re-checked by a solver-free DP
that shares nothing with either encoder.

## DRAT certificates (kissat --no-binary, replayed by drat-trim)

Only the literal line `s VERIFIED` counts.

| n | N | mode | solve s | proof MB | check s | verdict |
|---|---|------|---------|----------|---------|---------|
| 28 | 35 | reach | 2.6 | 0.19 | 1.2 | VERIFIED |
| 29 | 41 | reach | 7.5 | 0.33 | 2.2 | VERIFIED |
| 30 | 36 | reach | 2.9 | 0.26 | 1.3 | VERIFIED |
| 28 | 35 | support | 4.7 | 0.94 | 9.0 | VERIFIED |
| 29 | 41 | support | 15.3 | 1.2 | 89.1 | VERIFIED |
| 30 | 36 | support | 5.5 | 0.91 | 13.9 | VERIFIED |

All three reproduced UNSATs are certified in BOTH encodings (the n=29
support certificate, still queued at the original session cutoff, was
finished 2026-08-13). The certificates for the new a(31) refutation are
in the a(31) section below.

## Pipeline validation

- Witness checker rejects corruptions (all-one-color colorings at every
  witness instance; enforced cold by the gate).
- Off-by-one instances really flip: SAT at a(n)-1, UNSAT at a(n), for all
  three n, in both encodings.
- Brute force over all 2-colorings (color of 1 fixed by symmetry) agrees
  with the CNF encodings everywhere it was run, and reproduces
  a(5), a(6), a(9), a(10) with no solver in the loop.
- Support enumeration equals naive multiset enumeration on small cases
  (n=2 N=26, n=3 N=20, n=4 N=15, n=9 N=16).
- Brute force, the support encoding AND the reach encoding are all required
  to agree at one small N for every n from 28 to 40 — the reach encoding is
  no longer pinned only indirectly.
- The reach encoding alone reproduces all THIRTEEN published values
  a(18) = 28 through a(30) = 36 (40 s for the set). This is the control
  group added when the sweep started reporting values the support encoding
  could not reach: a systematic reach bug would have to leave thirteen known
  answers intact to survive it. Enforced by the gate.
- drat-trim was checked to have teeth, not just to say VERIFIED: on the
  n=33 N=37 reach refutation, flipping one literal of a single lemma gives
  `s NOT VERIFIED`, and replaying the honest proof against the *N = 36*
  formula (which is satisfiable) gives `s NOT VERIFIED` at proof line 789.
  Truncating the proof, by contrast, keeps verifying down to 10% of the
  emitted lemmas — kissat's proofs of these instances are highly redundant
  and the refutation core is small. That is a property of the instances,
  not a hole in the checker.
- For every term reported here, the verified witness at N = a(n) - 1,
  extended by the integer a(n) in EITHER color, is rejected by the
  solver-free checker — every time by a solution with z = a(n) itself. That
  is not a proof of UNSAT on its own (some other coloring of [1, a(n) - 1]
  might have extended), but it puts the flip point exactly where the solver
  puts it with no solver in the loop.

## a(31) = 41 (NEW): probe, then the full evidence round

The timeboxed probe ran 2026-08-13 (`python rado/probe.py --n 31
--budget 900 --json rado/evidence/probe_a31.json`) and resolved in 13.9 s
of its 900 s budget: bisecting on N under the reach encoding it found SAT
(witness verified solver-free) at N = 21, 31, 36, 38, 39, 40 and UNSAT at
N = 41 (6.1 s solve, 2,278,548 clauses). A probe is not a claim, so the
full evidence round followed the same day, identical in shape to the
reproductions above (wall seconds, this machine, single-threaded kissat):

| mode | N | result | supports | clauses | build s | solve s |
|------|---|--------|----------|---------|---------|---------|
| reach | 41 | UNSAT | - | 2,278,548 | 1.1 | 5.7 |
| reach | 40 | SAT, witness verified | - | 2,110,970 | 1.0 | 0.4 |
| support | 41 | UNSAT | 6,306,948 | 12,613,896 | 402.1 | 11.5 |
| support | 40 | SAT, witness verified | 4,662,929 | 9,325,858 | 290.7 | 2.1 |

Both SAT witnesses (the same coloring, found independently by the two
encodings) were re-checked by the standalone solver-free checker; both
UNSATs are DRAT-certified:

| n | N | mode | solve s | proof MB | check s | verdict |
|---|---|------|---------|----------|---------|---------|
| 31 | 41 | reach | 4.8 | 0.05 | 1.8 | VERIFIED |
| 31 | 41 | support | 15.8 | 1.3 | 66.5 | VERIFIED |

SAT at N = 40 and UNSAT at N = 41, agreeing across two unrelated
encodings, give a(31) = 41. This term is NEW: OEIS A250026 ends at
a(30) = 36 (checked 2026-08-13). a(31) = 41 was computed here first,
2026-08-13, and was approved at OEIS on 2026-08-14. Note a(31) = a(29)
= 41 while a(30) = 36 -- the sequence is not monotone, as the published
terms already show.

## a(32) .. a(40) (NEW): the n = 32..40 sweep

Run 2026-08-13/14 on this machine, single-threaded kissat, same pipeline and
same claim bar as everything above.

### Step 1 - probes

`python rado/probe.py --n <n> --budget 900`, reach encoding, one at a time;
records in `rado/evidence/probe_a<n>.json`.  A probe is not a claim.

| n | budget s | used s | SAT at | UNSAT at | a(n) if confirmed |
|---|----------|--------|--------|----------|-------------------|
| 32 | 900 | 13.2 | 40 | 41 | 41 |
| 33 | 900 | 19.5 | 36 | 37 | 37 |
| 34 | 900 | 27.2 | 41 | 42 | 42 |
| 35 | 900 | 26.1 | 43 | 44 | 44 |
| 36 | 900 | 22.4 | 36 | 37 | 37 |
| 37 | 900 | 28.0 | 44 | 45 | 45 |
| 38 | 900 | 53.6 | 46 | 47 | 47 |
| 39 | 1800 | 163.0 | 51 | 52 | 52 |
| 40 | 900 | 52.7 | 46 | 47 | 47 |

n = 39 is the one that broke the mould: the probe's default search cap of 50
did not bracket it at all (SAT at N = 50, no UNSAT found; that first,
unresolved run is kept as `probe_a39_cap50.json`), and it was re-run with
`--cap 80 --budget 1800`, which found UNSAT at 80, 63, 54, 52 and SAT at 50,
51.  a(39) = 52 is the largest value in the whole known sequence apart from
a(2) = 7825 and a(3) = 105.

### Step 2 - reach encoding, full round on all nine

| n | N | result | clauses | build s | solve s |
|---|---|--------|---------|---------|---------|
| 32 | 41 | UNSAT | 2,363,256 | 1.1 | 6.3 |
| 32 | 40 | SAT, witness verified | 2,189,120 | 1.1 | 0.4 |
| 33 | 37 | UNSAT | 1,778,068 | 0.8 | 4.0 |
| 33 | 36 | SAT, witness verified | 1,631,914 | 0.8 | 0.3 |
| 34 | 42 | UNSAT | 2,729,230 | 1.3 | 5.8 |
| 34 | 41 | SAT, witness verified | 2,531,726 | 1.2 | 0.4 |
| 35 | 44 | UNSAT | 3,255,626 | 1.5 | 8.1 |
| 35 | 43 | SAT, witness verified | 3,032,466 | 1.4 | 0.5 |
| 36 | 37 | UNSAT | 1,959,944 | 0.9 | 4.6 |
| 36 | 36 | SAT, witness verified | 1,798,498 | 0.9 | 0.3 |
| 37 | 45 | UNSAT | 3,716,368 | 1.7 | 9.4 |
| 37 | 44 | SAT, witness verified | 3,465,264 | 1.6 | 0.6 |
| 38 | 47 | UNSAT | 4,378,816 | 2.1 | 13.7 |
| 38 | 46 | SAT, witness verified | 4,097,268 | 1.9 | 0.7 |
| 39 | 52 | UNSAT | 6,154,382 | 3.2 | 17.0 |
| 39 | 51 | SAT, witness verified | 5,796,454 | 2.8 | 1.0 |
| 40 | 47 | UNSAT | 4,635,406 | 2.2 | 11.8 |
| 40 | 46 | SAT, witness verified | 4,336,768 | 2.1 | 0.8 |

Every witness was re-checked by the solver-free checker, and re-checked
again standalone (`python rado/verify_witness.py <file>`) after the fact.

### Step 3 - support encoding, second and independent

Attempted in ascending order of N (the cost driver), with a hard 1500 s
(25 minute) timebox on each build; a term whose support build does not fit
the box is recorded as a measured limit and is NOT claimed.

**The campaign stopped at a solver ceiling, and the ceiling is bracketed.**
The largest support instance that has ever solved here is n = 35, N = 44 at
22,088,930 clauses (build 1281.3 s, solve 6.3 s). The next one attempted,
n = 37, N = 45, *built* without trouble — 19,516,162 supports, 39,032,324
clauses, 2444.6 s — and then kissat exited after 0.2 s with an empty stdout
and stderr and a status that is neither 10 nor 20. Recorded as
`SOLVER_ERROR` in `rado/evidence/support_n37_N45.json`.

That 0.2 s matters: it is far too fast to have read a file of that size, so
the solver died at start-up rather than while solving. It is also not a parse
or file error — those print `kissat: error: ...` and exit 1 even under `-q`
(checked directly against a missing file). The remaining explanation is an
allocation failure; free memory at the time was 5.8 GB of 15.4 GB.

So the support ceiling on this machine is **between 22M and 39M clauses**, and
a(37), a(38), a(39), a(40) all sit above it. They are measured, DRAT-certified
in the reach encoding, and deliberately NOT claimed. Re-testing them needs
either more free memory or a support encoding that is smaller at the same n;
neither was attempted here, and no claim rests on the difference.

| n | N | result | supports | clauses | build s | solve s |
|---|---|--------|----------|---------|---------|---------|
| 33 | 37 | UNSAT | 1,802,637 | 3,605,274 | 130.4 | 6.8 |
| 33 | 36 | SAT, witness verified | 1,312,545 | 2,625,090 | 83.5 | 0.6 |
| 36 | 37 | UNSAT | 1,749,816 | 3,499,632 | 156.9 | 1.7 |
| 36 | 36 | SAT, witness verified | 1,274,284 | 2,548,568 | 104.0 | 0.6 |
| 32 | 41 | UNSAT | 6,251,055 | 12,502,110 | 450.0 | 14.5 |
| 32 | 40 | SAT, witness verified | 4,619,432 | 9,238,864 | 328.9 | 2.1 |
| 34 | 42 | UNSAT | 8,273,165 | 16,546,330 | 742.1 | 18.0 |
| 34 | 41 | SAT, witness verified | 6,137,157 | 12,274,314 | 519.7 | 3.0 |

The two encodings agree on every instance in this sweep; no disagreement was
seen anywhere, at any n, at any N.

### Step 4 - DRAT certificates

kissat `--no-binary`, replayed by drat-trim; only the literal line
`s VERIFIED` counts.

| n | N | mode | solve s | proof MB | check s | verdict |
|---|---|------|---------|----------|---------|---------|
| 32 | 41 | reach | 6.1 | 0.21 | 2.7 | VERIFIED |
| 33 | 37 | reach | 4.1 | 0.27 | 1.8 | VERIFIED |
| 34 | 42 | reach | 6.3 | 0.10 | 2.6 | VERIFIED |
| 35 | 44 | reach | 9.3 | 0.25 | 3.5 | VERIFIED |
| 36 | 37 | reach | 4.8 | 0.21 | 1.6 | VERIFIED |
| 37 | 45 | reach | 9.5 | 0.09 | 3.8 | VERIFIED |
| 38 | 47 | reach | 13.8 | 0.51 | 4.8 | VERIFIED |
| 39 | 52 | reach | 17.8 | 1.04 | 6.5 | VERIFIED |
| 40 | 47 | reach | 12.0 | 0.08 | 3.8 | VERIFIED |
| 32 | 41 | support | 15.9 | 1.21 | 79.9 | VERIFIED |
| 33 | 37 | support | 6.2 | 0.94 | 15.7 | VERIFIED |
| 34 | 42 | support | 19.8 | 1.59 | 78.5 | VERIFIED |
| 36 | 37 | support | 2.1 | 112.93 | 255.4 | VERIFIED |

The n = 36 support proof is a 113 MB outlier next to its neighbours' ~1 MB:
kissat found the refutation in 2.1 s but wrote a very wide proof, and
drat-trim still replayed it to `s VERIFIED` in 255 s.  Nothing was tuned to
make that happen and nothing was re-run to make it smaller.

### What is claimed, and what is only measured

At the time this section was written: a(32) = 41, a(33) = 37, a(34) = 42,
a(35) = 44, a(36) = 37 were claimed and a(37) .. a(40) were measured on the
reach encoding alone.  The section below closes that gap and goes past it —
everything through a(60) is now claimed.

### Status of these values

All of a(31) .. a(40) are now in OEIS.  A250026 ended at a(30) = 36 when this
section was written (entry version #35 of Nov 05 2025, re-fetched read-only
2026-08-13).  a(31) = 41 was submitted on 2026-08-13 and approved on
2026-08-14; a(32) .. a(60) were approved on 2026-08-19.  The values in this
section were computed here first, on 2026-08-13/14, and each is credited to
the author.

## Hardness curve and GO/NO-GO

The published frontier stopped at a(30) in 2015 because Myers's
Mathematica tree-search slowed past k = 30, not because the instances are
intrinsically hard: every solve above is seconds. The cost driver at
larger n is instance GENERATION, and the reach encoding keeps that
polynomial (about N^2 * n aux variables) — for n around 31-40 and N up to
50 the build stays under a few seconds.

**Recommendation: GO** for the a(31)+ extension campaign, with the reach
encoding leading and these conditions: (1) finish the two items above
(n=29, N=40 support solve; n=29 support DRAT) and run `rado/verify_all.py`
cold to 0 failures before any new-term work; (2) run the timeboxed a(31)
probe first — if it resolves in minutes, as every reproduced instance here
suggests, sweep n = 31..40; (3) every new term ships only with the full
evidence set this repo defines: SAT witness re-checked solver-free at
a(n)-1, DRAT-certified UNSAT at a(n), both encodings agreeing. The risk
that stopped Myers in 2015 (instance generation cost in a computer algebra
system) is retired by the polynomial reach encoding; the solver side was
never the bottleneck at these sizes.

Status 2026-08-13: conditions (1) and (2) are met — both n=29 items
finished, the cold gate passed 73/73 before any new-term work, and the
probe resolved in 13.9 s — and the first new term, a(31) = 41, has
shipped under (3) with the full evidence set (section above). The
campaign continues at n = 32..40.

## a(37) .. a(60) (NEW): the lazy encoding

### What was actually blocking these

The sweep left a(37) .. a(40) measured on `reach` alone, recording a kissat
allocation ceiling "between 22M and 39M clauses" as the reason the `support`
round could not be finished.  Re-examined on 2026-08-14, that diagnosis does
not survive:

- The largest support instance that had solved was n = 35, N = 44 at
  **29,639,268** clauses, not 22,088,930 — the smaller figure is the N = 43
  row of the same table.
- kissat parses and solves a **47,000,000-clause, 1.5 GB** instance on this
  machine in 14 s.  Ladder run at 31M, 39M and 47M clauses; all three
  returned normally.
- Every genuine kissat failure writes to stderr and exits 1 — verified
  separately for a short file, a long file, an out-of-range literal and a
  missing file.  The n = 37 run exited at 0.2 s with **empty stdout and empty
  stderr**, which is a silent process death, not a refusal.
- `solve.py` recorded only stderr, never the return code, so the evidence on
  disk could not distinguish the two.  That is the gap the wrong conclusion
  came through, and it is worth remembering: the field that would have
  settled it was the one nobody stored.

The real cost was never the solver.  It was the 2444.6 s of Python that
writes 39,032,324 clauses before a solver sees them.

**Settled by rebuilding it.**  The identical instance -- same n, same N, same
encoder, 39,032,324 clauses in a 1.29 GB file -- was rebuilt on 2026-08-14
(2994.5 s) and kissat returned **20 (UNSAT) in 50.7 s**.  So a(37) = 45 is
confirmed on the full support encoding as well as on `lazy` and `reach`, and
the first attempt is kept as
`rado/evidence/support_n37_N45_first_attempt.json` because it is the single
data point a mechanism was named from.  One failure is not a ceiling.

### The method

Almost all of those clauses are subsumed.  If support T is a subset of
support S then clause(T) subsumes clause(S).  Measured inclusion-minimal
fractions, on instances small enough to enumerate whole:

| n | N | supports | inclusion-minimal | factor |
|---|---|---------:|------------------:|-------:|
| 28 | 34 | 733,061 | 4,633 | 158x |
| 28 | 35 | 1,012,712 | 5,378 | 188x |
| 30 | 35 | 982,782 | 4,966 | 198x |
| 30 | 36 | 1,354,176 | 5,850 | 231x |
| 33 | 36 | 1,312,545 | 5,207 | 252x |

`rado/lazy.py` skips the enumeration entirely: solve what you have, and when
the solver hands back a coloring, give it to the solver-free checker, which
either accepts it or returns a monochromatic solution whose support becomes
the next clause.

### Why both answers are sound

- **UNSAT**: the clause set is a SUBSET of the full support encoding, so its
  refutation refutes the full instance.  What has to hold is that each clause
  really is one of the encoding's — and each is recorded with an explicit
  solution (multiset of x values, and z), so that is arithmetic anyone can
  redo.  `verify_all.py` redoes it for every clause of every claim; five
  mutations of a real justification are checked to be caught.
- **SAT**: `verify_witness.py`, unchanged, reading the equation not the CNF.

Neither depends on the search being good.  A bad search costs time only.

### Control group

Every published value a(3) .. a(30) and every term already claimed here with
the full encoding, both polarities — 68 endpoints — reproduced in **47
seconds** total.  Separately, on instances small enough to enumerate whole,
every clause the lazy method emitted was checked to be present in
`encode.iter_supports` output, and to be a strict subset of it (0.0017% of
the full clause set at n = 36, N = 37).

### Results

Each term below has a witness at N = a(n)-1 accepted by the solver-free
checker, a drat-trim-verified refutation at N = a(n), and the `reach`
encoding agreeing at both endpoints.

| n | a(n) | clauses used | n | a(n) | clauses used |
|---|-----:|-------------:|---|-----:|-------------:|
| 37 | 45 | 218 | 49 | 51 | 102 |
| 38 | 47 | 402 | 50 | 60 | 424 |
| 39 | 52 | 440 | 51 | 67 | 460 |
| 40 | 47 | 110 | 52 | 59 | 154 |
| 41 | 47 | 342 | 53 | 60 | 466 |
| 42 | 54 | 264 | 54 | 68 | 462 |
| 43 | 48 | 194 | 55 | 61 | 288 |
| 44 | 56 | 304 | 56 | 62 | 354 |
| 45 | 56 | 594 | 57 | 70 | 512 |
| 46 | 50 | 242 | 58 | 63 | 256 |
| 47 | 57 | 548 | 59 | 72 | 454 |
| 48 | 58 | 180 | 60 | 71 | 288 |

The full support encoding would have needed tens of millions of clauses for
each of these; a(37) took 218.

### Status of these values

All of a(31) .. a(60) are now in OEIS.  a(31) = 41 was submitted on 2026-08-13
and approved on 2026-08-14; a(32) .. a(60) were approved on 2026-08-19.  They
were computed here first, and each is credited to the author.
The stopping point a(60) is where the run stopped, not a wall — each further
term costs seconds.
