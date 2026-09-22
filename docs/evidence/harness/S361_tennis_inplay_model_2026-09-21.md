# S361 tennis exact score recursion

PREPARE ONLY. Construct acceptance passed locally; the model is unused by the
capture loop. No archive was opened, no data directory was accessed, no network
was used, and no pod operation was performed. No scored comparison was run.

Vocabulary follows contract Q6; automated scan required.

## Binding before-condition

Re-run before creating files, using the PowerShell equivalents of ls and grep:

```text
Get-Item scripts/platformkit/ingame/tennis_point_recursion.py
Get-Item : Cannot find path 'C:\Users\neelj\nba-harness-h19\scripts\platformkit\ingame\tennis_point_recursion.py'
because it does not exist.

Select-String -Path scripts/platformkit/ingame/inplay_capture_loop.py -Pattern '_MODEL_SPORTS'
scripts\platformkit\ingame\inplay_capture_loop.py:99:_MODEL_SPORTS: Tuple[str, ...] = ("mlb", "soccer_intl", "nba")
```

The expected absence held. The existing S348 coverage artifact was inspected
as context only; its archive counts were not reproduced in this row.

## Model and assumptions

The new stdlib module computes A's probability using memoized score recursion.
Game deuce uses p squared divided by p squared plus (1-p) squared. Tiebreaks
use the initial single serve followed by alternating pairs of serves. Extended
tied tiebreaks sum their infinite return-to-tie series analytically. Advantage
sets use the analogous two-game expression. No simulation or truncation is used.

Set recursion preserves the joint distribution of the set winner and next-set
server. After a tiebreak, the first receiver serves the next set, including when
the supplied state is partway through that tiebreak. The public server field is
the NEXT point's server. Normal point scores are counts, not 15/30/40 labels.

Rules are best_of=3 or 5 and final_set=tiebreak, match_tiebreak, or advantage.
The tiebreak rule means seven points at 6-6. The match_tiebreak rule replaces the
entire deciding set with a ten-point tiebreak, games 0-0 and in_tiebreak=True.
All earlier sets use the seven-point tiebreak at 6-6. Advantage means no deciding
set tiebreak. Nonterminating deterministic cases raise an explicit ValueError.

ASSUMPTION: points are independent, with fixed serve-point probabilities for
each player throughout the match. Retirement, injury, fatigue, surface changes,
and point-to-point dependence are not modeled.

ASSUMPTION: base_hold=0.64 is a declared rounded men's-tour average serve-POINT
level, not a game-hold probability. Public tour-level reference:
[Tennis Abstract ATP statistics](https://www.tennisabstract.com/reports/atp_stats.html).
This is an offline source citation, not a newly retrieved or computed average;
the exact reference aggregation and its applicability to either tour remain
unverified. The constant is fixed by this spec, not fitted to an archive.
One pre-match prior identifies only the difference after imposing this level:
p_a=base_hold+delta and p_b=base_hold-delta. Deterministic bisection inverts the
start-of-match recursion with equal first-server weights to tolerance 1e-9.

The parser consumes the already-landed ingestion schema in
domains/tennis/ingest_espn.py: paired player_name/comp_id rows, best_of,
sets_won, and s1 through s5. Explicit player names determine orientation;
row order does not. Raw ingestion is not copied or reimplemented. Finite whole
game counts are required; missing per-set columns, gaps, contradictory totals,
ambiguous deciding match-tiebreak encodings, and unknown shapes return None
with a reason. Every caught exception increments REJECTIONS by reason.
Best-of-five rows require explicit matching rules, also passed to the model.

COARSE per-set states explicitly assume points 0-0 and server unknown. The
model averages equally over both possible servers. This is a coarsening
assumption, not a reconstruction of an unobserved point score. Null trailing
sets are unplayed, never an observed zero. Missing current games are refused.
The live module ingame_live_state.py exposes home_score/away_score as set totals
but lacks current games, points and server; those lossy states are refused.
No venue time or quantity is consumed by these modules.

## Initial construct verification (before FIX 1b)

```text
python -m pytest tests/platformkit/ingame/test_tennis_point_recursion.py -q -p no:cacheprovider
63 passed
python -m scripts.platformkit.ingame.tennis_point_recursion
S361 self-check PASS (construct only)
```

All fixtures are inline in the new test file. The denominator is 63 collected
construct cases. Checks include game closed forms, score symmetry, monotonicity,
terminal matches, ABBA rotation and next-set service, both match lengths, all
deciding-set rules, prior inversion, unknown-server averaging, invalid inputs,
and independent enumeration of finite set paths. No tracked test needs a
gitignored fixture. Only the four spec-listed new files are delivered.

Contract B review: no filtering-based metric, schema mutation, evidence gate,
claim loop, deployment, moved module, sampling, fitted comparison, recycled
metric denominator, or threshold change. Q1-Q5: no scoring or trial charge in
this row; their scoring prerequisites remain mandatory for a later row.
Q6: automated contract_preflight passed all nine checks on the four delivered
files, including vocabulary, line limits, additive scope and artifact paths.
Q7: the test count is CONSTRUCT, not a sampled corpus. Q8: premise re-run above.

## Later scored row

Seal a preregistration before joining/scoring and charge any required trial
ledger before the first metric. Freeze four arms: pre-match prior, exact score
recursion, contemporaneous mid, and a preregistered fixed model/mid blend.
Join state and price by resolved match/player identities with as-of timestamps,
using the landed venue_time.parse_venue_time parser; any quantities must be
Decimal values parsed from strings. Preserve refusal and missingness counts.
Split walk-forward by match date, keep all ticks from each match together, purge
and symmetrically embargo as required by contract Q4. Compare all arms against
the contemporaneous mid on identical eligible observations; outcomes are labels
only. Keep coarse and detailed states separate, audit truncation invariance,
and require independent corpora before any Q5 comparison claim.

## FIX 1b

The verifier's terminal-state defect was confirmed in the candidate's validation:
no check excluded residual games, points or a tiebreak flag after a match win.
Validation now rejects each with `ValueError: completed match has residual score`.
Clean terminal states remain accepted. The probability mathematics, recursion,
service rotation, inversion and memoization keys are unchanged.

The parser requires integer canonical counts; negative, fractional, float and
boolean canonical counts are refused with exact reasons. Paired ingestion keeps
its finite whole numeric conversion. Existing impossible game/point scores and
excess set totals are covered by exact `(None, reason)` assertions. Both tiebreak
targets now require `type(first_to) is int` as well as membership in `(7, 10)`.

Local reproduction using the commands above: 168 passed in 5.23s; the module
printed `S361 self-check PASS (construct only)`. The denominator is 168 collected
CONSTRUCT cases, including both winners, both formats and all final-set rules
for terminal residuals. No real observations were scored. Contract preflight
uses the four delivered files, `--base master`, and
`--spec docs/evidence/tracking/specs/S361_spec.md`.

## FIX 1c

Finding 1 (BLOCKING): unreachable point scores remained accepted after the
race had already ended. The verifier's minimal reproduction before this fix:

```text
p_game(0.6, 5, 0) = 1.0
p_tiebreak(0.6, 0.6, 8, 0, True, 7) = 1.0
parse = (state, 'OK')
rejection counter delta = 0
match_win_prob = 0.7499999999999998
```

The state was sets 0-0, games 6-6, points 8-0, server a, in_tiebreak=True.
The shared `_validate_race_score` now checks p_game, p_tiebreak and `_state`
tiebreak points. Beyond the target, a terminal score must have a two-point
lead: otherwise the race ended earlier. The existing parser calls `_state`,
so its unchanged exception handler records the specific refusal exactly once.
The same reproduction after the fix:

```text
p_game(0.6, 5, 0) = ValueError: race score continued after completion
p_tiebreak(0.6, 0.6, 8, 0, True, 7) = ValueError: race score continued after completion
match_win_prob = ValueError: race score continued after completion
parse = (None, 'ValueError: race score continued after completion')
rejection counter delta = 1
Minimal reproduction PASS: 3 direct refusals, 1 counted parser refusal
```

Regression `test_race_score_reachability` adds 48 CONSTRUCT cases: three
race targets (4, 7, 10), both score orientations and eight score patterns.
These preserve 4-0, 5-3, 7-0, 8-6 and the ten-point equivalents, extended
ties and advantages, while refusing three overshoot patterns per target.
Seven- and ten-point cases also check exact parser reasons, counter changes
and the public match entry point. Existing tests remain, with blank-line
spacing reduced to keep the test file within 300 lines.

Findings 2 and 3 (NOTE; fix none): existing impossible-state validation,
probability mathematics, service rotation and inversion are unchanged.
Neither the worktree spec nor `git show master:docs/evidence/tracking/specs/S361_spec.md`
contained an AMENDMENT block. The recursion module, its test and this memo
are the only files edited for FIX 1c; the row's parser is delivered unchanged.

Verification commands are the per-file pytest command above, the recursion
module with and without `--help`, and contract_preflight on the four delivered
files with `--base master --spec docs/evidence/tracking/specs/S361_spec.md`.
The module has no argument parser: both invocations execute its self-check.
Final local results: 216 passed in 3.44s (216 CONSTRUCT cases); both module
invocations printed `S361 self-check PASS (construct only)`; contract preflight
passed all nine checks over the four delivered files. The earlier verifier's
temporary-directory setup failure did not recur in this writable worktree.

## NOT VERIFIED

- Any real archive state, identity join, price alignment, or outcome label.
- Calibration, contemporaneous-price comparison, or production predictive quality.
- The public source's exact average or transport of the fixed level to ATP/WTA.
- The i.i.d. point, fixed serve strength, and coarse-state assumptions in practice.
- Capture-loop integration, service deployment, pod execution, or real-time latency.
- A sealed scoring preregistration, scored trial, or independent-corpus validation.
