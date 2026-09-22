# S355 four-arm eligibility and counts-only census

Construct verification only. The required row-owned modules were edited in
C:/Users/neelj/nba-harness-h13. No real corpus was opened or scored.
Vocabulary follows contract Q6; automated scan required.

## Authority and binding before-condition

- Spec: docs/evidence/tracking/specs/S355_spec.md.
- Authority: docs/evidence/ingame/S347_PREREG_REVIEW_2026-09-21.md.
- Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q.
- Machine: local Windows worktree, synthetic CPU tests only. The pod is OFF.

Before editing, a temporary JSONL corpus contained exactly three synthetic ticks
of one game. The second row omitted inning from state_summary. The existing
predict_rows eligibility path raised, with this exact output:

```text
BINDING BEFORE-CONDITION: 3 synthetic rows; row 2 lacks inning; ValueError: incomplete mlb state_summary
```

The temporary input was removed by TemporaryDirectory. Its rows are reproduced
by the missing-inning construct in the new test file; no real input is needed.
Resolution is not applicable to these JSONL constructs.

## Changes and denominators

The shared loader verifies the manifest inventory and each file hash, rejects
directories outside the resolved gate DATA_ROOT, and parses every nonblank row.
Integrity checks cover excluded ticks as well as retained ticks. Hash mismatch,
unparseable JSON, inconsistent outcomes and unknown corpus names still raise.
Amendment 1 replaces the duplicate-key abort as documented in FIX 1b below.
Existing chronology and structural refusals also remain.

Eligibility excludes ticks from all four arms together. Histograms count each
distinct reason once per tick, per file and per game. They report unavailable
state features, missing probabilities, nonfinite values, unparseable timestamps,
and missing_outcome. Multiple reasons can describe one excluded tick; reason
totals are not a distinct-tick denominator. All-ineligible games remain named
with their reason histograms. Finite market values use the inherited EPS clip;
the finite model covariate is not clipped. Soccer optional red counts retain the
declared zero value plus zero presence indicator, as in the original draft.

Both CLI modes use the same loader and eligibility function. census.json has
scored=false, fields_read, exact source paths, byte sizes and hashes, per-sport
totals, eligible populations, exclusions, transition counts, UTC date counts,
warmup folds and the inherited eligible-game count check. Empty files count.
The census only checks outcome presence and within-game consistency; it computes
no loss or outcome statistic and fits nothing. It needs no preregistration seal.
The scoring route retains the manifest, valid seal and committed-bytes refusals.

First-tick dates include excluded ticks whose timestamps are parseable. Games
with no parseable tick are counted separately. State transitions compare
successive eligible state vectors. Folds cover eligible games; an empty eligible
population has no folds. Every fold reports training games and ticks, including
warmup folds. Scoring checks evaluator outcome equality by canonical stable key
before computing any paired loss. The temporal settlement embargo remains the
binding chronology guard where team identities are absent.

Existing output fields remain; training counts and eligibility reports are
additive. The existing test for malformed times, missing model probability and
missing outcome previously expected an abort. It now asserts counted exclusion.
There was no dedicated missing-state-aborts test in the old test file; the new
missing-inning test verifies the changed rule. Synthetic fixtures now set
DATA_ROOT to their temporary directory so the new containment check is exercised.
The legacy load import remains available; CLI modes use the complete loader.

## Initial candidate verification (prior lane record)

All executable checks use the exact commands requested, one file at a time:

```text
python -m pytest tests/platformkit/ingame/test_baseline_four_arm_eligibility.py -q -p no:cacheprovider
32 passed in 0.85s
python -m pytest tests/platformkit/ingame/test_baseline_four_arm.py -q -p no:cacheprovider
29 passed in 1.81s
python -m scripts.platformkit.ingame.baseline_four_arm --help
Exit 0; --census-only is listed.
```

The new file enumerates exclusion reasons, all-ineligible games, all required
integrity failures, no-prereg census with loss/fitting functions patched to raise,
containment before file reads, per-key outcome mismatch, fold training sizes,
embargo boundaries, UTC dates, EPS clipping, sport features and empty files.
This is n = 32 (CONSTRUCT); the existing file supplies 29 additional constructs.
No calibration number is reported. A separate read-only review found no blocking
issue; it did not execute tests or inspect a real corpus.

```text
python -m scripts.platformkit.ingame.baseline_four_arm --self-check
S355 self-check PASS: ASCII, LOC, Q6 scan, unchanged bars, unsealed draft, memo.
```

Contract preflight used --paths with all seven files listed below, --base master
and --spec docs/evidence/tracking/specs/S355_spec.md. Exit 0, all nine checks PASS:
vocabulary, CRLF, LOC, schema, head slices, spec thresholds, proposed diff,
removed artifacts and row duplication. Every modified or new Python file is
at most 300 lines. The preflight reported no explicit threshold-line declaration
in the spec and no proposed diff; the self-check separately verifies inherited
bar lines against the unchanged GATE A0 source.

## Contract self-review

B: Every input tick remains in the census denominator; excluded ticks and games
are explicitly named by reason. No schema field was removed, no shared module
was edited, and no file was moved or retired. Reader inspection in the ingame
module/test directories found the scorer and its tests as the affected consumers.
No sampled slices, fitted-residual evidence, deployment or service changes exist.
The unchanged inherited bars are checked against the GATE A0 source.

Q: The new prereg draft stays UNSEALED. No real-corpus metric or charged trial
was run. No trial count is inferred. Scoring retains walk_forward with strict
redaction and vintage/key checks, the symmetric embargo and SINGLE-WINDOW
labelling. The original draft remains in place. The new r2 draft adds the
orchestrator's unfilled pre-seal eligibility census section. Verification is
construct-only; there is no cross-corpus conclusion.

## Files for lane_commit

Modified:
- scripts/platformkit/ingame/baseline_four_arm.py
- scripts/platformkit/ingame/baseline_four_arm_features.py
- tests/platformkit/ingame/test_baseline_four_arm.py

Created:
- scripts/platformkit/ingame/baseline_four_arm_eligibility.py
- tests/platformkit/ingame/test_baseline_four_arm_eligibility.py
- docs/evidence/ingame/S347_PREREG_DRAFT_r2_2026-09-21.md
- docs/evidence/harness/S355_four_arm_eligibility_2026-09-21.md

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1b

Amendment 1 is binding. The orchestrator reported the real-corpus duplicate
abort after the initial constructs passed. That real measurement was supplied
in the spec; this fix did not reproduce it on real input. All input opened by
this fix's tests is generated under temporary directories by the two test files.
The loader archives exact synthetic source paths, byte sizes and hashes in its
census provenance; resolution is not applicable to JSONL constructs.

Each binding item is quoted below beside its implementation locations. Paths
in these references are relative to this worktree.

> (a) IDENTICAL REPEATS (every field equal) collapse to ONE row; counted as duplicate_identical per file and per game.

Code: scripts/platformkit/ingame/baseline_four_arm_eligibility.py lines 73-85
compare canonical JSON with sorted keys and retain one representative only for
an identical group. Lines 117-118 count surplus rows per file and game.
Lines 196-198 preserve canonical JSON of EVERY original parsed field before
adding loader provenance; field-order differences do not cause a conflict.
Lines 203-204 report every field read, including otherwise unused fields.

> (b) A CONFLICTING KEY (same game_id and ts, any field differing) is AMBIGUOUS: EVERY row of that key is excluded from ALL FOUR
> arms identically, counted as conflicting_duplicate_key per file and per game. Never keep-first, keep-last or an average:
> any such choice would be an unregistered analyst decision.

Code: scripts/platformkit/ingame/baseline_four_arm_eligibility.py lines 76-85
assign the conflict reason to EVERY row of a conflicting group, even where
some members repeat identically. Lines 91-123 count and exclude them together.
scripts/platformkit/ingame/baseline_four_arm.py line 58 supplies the same
selected population to all four arms. Outcome labels never select a survivor.

> (c) The rule is applied BEFORE eligibility and before state-transition detection, so a dropped key never creates a transition.

Code: scripts/platformkit/ingame/baseline_four_arm_eligibility.py lines 71-85
classify complete groups before lines 95-112 evaluate eligibility. Lines 124-131
detect transitions only among retained eligible rows. The scorer applies the
same selection at baseline_four_arm.py line 58 before its transition at line 78.
Integrity checks still inspect ALL input rows at eligibility.py lines 43-70.
baseline_four_arm_features.py lines 39-47 separate duplicate-state-field
integrity from eligibility, preserving this refusal even on conflicting keys.

> (d) A game where more than 10 pct of its keys are conflicting is reported in the census as high_conflict_game (it stays in the
> population; the census makes it visible so the prereg can name a threshold before sealing).

Code: scripts/platformkit/ingame/baseline_four_arm_eligibility.py lines 77-81
count distinct keys and distinct conflicting keys. Line 144 applies the strict
comparison by integer arithmetic; lines 151-153 name the flagged games and
their denominators. This flag never removes a game. Exactly 10 pct is unflagged.

Denominators: ticks counts original parsed rows. duplicate_identical counts
collapsed surplus rows; conflicting_duplicate_key counts ALL excluded rows
of conflicting keys. Both appear in excluded_by_reason and explicit counters,
including explicit zeros, per file/game and at sport level. A retained identical
representative may separately fail eligibility. unique_keys/conflicting_keys
count distinct keys, independently of repeat multiplicity or eligibility.
First-tick dates continue to include excluded rows with parseable timestamps.
The unsealed r2 draft now states these rules and requests the duplicate census.
Manifest, sealed-prereg, committed-prereg and DATA_ROOT refusals are unchanged;
the inherited bars, seeds and verdict source remain unchanged.

FIX 1b verification, local Windows, n = 44 + 29 (CONSTRUCT):

```text
python -m pytest tests/platformkit/ingame/test_baseline_four_arm_eligibility.py -q -p no:cacheprovider
44 passed in 0.94s
python -m pytest tests/platformkit/ingame/test_baseline_four_arm.py -q -p no:cacheprovider
29 passed in 1.76s
```

The first scorer run had 28 passes and one failure: its old
test_duplicate_tick_refused expected the replaced abort. It is now
test_identical_duplicate_tick_collapses, asserting full prediction equality.
The eligibility file's old duplicate-abort parameter was also replaced by
constructs for canonical nested-field equality across files, unused-field and
timestamp-alias conflicts, conflicting groups containing identical members,
reversed input order, all-arm exclusion, absence of artificial transitions,
pre-eligibility duplicate counting, and both sides of the strict key threshold.
Outcome, close-time and duplicate-state-field inconsistencies still raise inside
conflicting groups. The CLI census test forbids all fitting and scoring calls
while checking the duplicate counters and high_conflict_game output.

Final self-check: exit 0, PASS for ASCII, LOC, Q6 scan, unchanged bars,
unsealed draft and memo. Contract preflight: exit 0, all nine checks PASS
over the seven Files for lane_commit paths, using --base master and
--spec docs/evidence/tracking/specs/S355_spec.md. The threshold check reports
no explicit THRESHOLD/BAR/ACCEPTANCE RULE lines; the self-check independently
compares the draft's inherited bar lines to the unchanged GATE A0 source.
No git commit was attempted; the candidate remains on disk for lane_commit.

## FIX 1c

Amendment 2 replaces the nonexistent MLB occupancy inputs. Its real-corpus
failure counts are orchestrator-supplied; this lane used synthetic inputs only.
The prior before-condition and FIX 1b results above are historical lane records.
The following references use worktree-relative paths and current line numbers.

> (e) MLB declared features are: score_diff (home_score minus away_score), inning, half (top = 0, bottom = 1), outs (0, 1, 2), and
> BASE AS A ONE-HOT OVER ITS EIGHT VALUES 0..7 (seven indicator columns, value 0 as the reference). No bit order is assumed and
> none is decoded: the one-hot is encoding-agnostic. A base value outside 0..7, or a non-integer, makes the tick ineligible with
> reason missing_state:base. The fields bos, re, count, pitch_count and tto are NOT features in this baseline (re is itself a
> model output); the memo lists them as available-but-excluded.

Code: scripts/platformkit/ingame/baseline_four_arm_features.py lines 9-12,
72-93 declare base_1 through base_7 and validate categorical codes without bits.
Available-but-excluded: bos, re, count, pitch_count and tto. They do not enter
the feature vector or create state transitions; re is itself a model output.
baseline_four_arm_eligibility.py lines 123-124 projects the complete declared
vector for the census, matching parse_state and the scorer's C/D feature lists.

> (f) Scores arrive as decimal strings such as 2.0; parse them as numbers and require them finite.

Code: scripts/platformkit/ingame/baseline_four_arm_features.py lines 57-79
parses numeric scores, explicitly checks both component scores are finite,
then checks the difference. Nonfinite values retain nonfinite_value exclusions.
The existing direct score_diff input remains supported.

> (g) Soccer declared features stay score_diff and minute; the red-card inputs stay optional exactly as drafted (absent -> zero with
> indicator zero). MEASURED soccer keys: 2,524 rows {home_score, away_score, minute}; 1,134 with half as well; 696 without minute;
> 4,649 state-less. half is NOT required for soccer.

Code: scripts/platformkit/ingame/baseline_four_arm_features.py lines 13-14,
94-99 retain the optional counts and presence indicators without reading half.
tests/platformkit/ingame/test_baseline_four_arm.py lines 271-285 check decimal
scores, MLB's missing-half exclusion, and soccer eligibility with or without half.

> (h) The census must show the eligible-tick and eligible-game counts AFTER this change on synthetic fixtures shaped like the real
> strings above; the orchestrator re-runs it on the real corpora.

Code: scripts/platformkit/ingame/baseline_four_arm_eligibility.py lines 145-149
reports counts after selection. tests/platformkit/ingame/test_baseline_four_arm_eligibility.py
lines 97-131 runs the actual census CLI for both sports without a prereg and
with loss, fitting and scoring functions patched to raise. Each construct has
11 input rows, 3 games, 8 eligible ticks and 3 eligible games: one surplus
identical repeat and both rows of one conflicting key are excluded.
The exact MLB example and every base category are checked in the scorer test;
invalid categories, missing half and nonfinite component scores are enumerated.
All inputs are generated in test memory or pytest temporary directories;
the CLI provenance reports exact synthetic paths, byte sizes and hashes.

The r2 draft stays UNSEALED, lists the amended features, and requires a sport
with fewer than 30 eligible pre-seal games to be declared UNDERPOWERED in the
sealed text and reported descriptively only. Amendment 1 is unchanged.
The manifest, sealed-prereg, committed-prereg and DATA_ROOT refusals remain;
the inherited bars, seeds and verdict rule were not edited. The self-check now
applies the 300-line limit to every deliverable, including both documents.

FIX 1c verification, local Windows, n = 45 + 53 (CONSTRUCT):
- Eligibility test file: 45 passed in 1.29s.
- Scorer test file: 53 passed in 2.17s.
Both used the exact per-file pytest commands above with -p no:cacheprovider.
Self-check: exit 0, PASS for ASCII, all-file LOC, Q6, inherited bars and UNSEALED.
Contract preflight: exit 0, all nine checks PASS over the seven lane_commit
paths with --base master and --spec docs/evidence/tracking/specs/S355_spec.md.

## NOT VERIFIED

- Real-corpus eligibility counts, missing-state concentration and date coverage.
- Real-corpus duplicate handling, conflict rates and counts supplied by the orchestrator.
- Revision-3 corpus regeneration, manifest identity and model timestamp provenance.
- Calibration performance, independent corpus validation or any scored conclusion.
- Preregistration sealing, trial charge, committed-byte identity in a real launch.
- Runtime on the pod, deployment, integration outside the two requested test files.
- Git commit creation or landing by lane_commit.
