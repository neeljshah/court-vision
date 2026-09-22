# S367 late-game cohorts -- PREPARE ONLY

The construct test file passes: 108 cases. No archive was opened or scored.
Vocabulary follows contract Q6; automated scan required.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h25, CPU only,
because this row builds an in-memory selector and synthetic fixtures.
The pod is OFF. No network, data-directory access, activation, or deployment.

## Binding before-condition

Before creating files, `ls scripts/platformkit/ingame/late_game_cohorts.py`
exited with code 1. Its output was:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h25\scripts\platformkit\ingame\late_game_cohorts.py' because it does
not exist.
```

## Frozen behavior and input contract

Source: docs/evidence/tracking/specs/S367_spec.md;
docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md section 3 and section 6 row 8;
docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.

`build_cohorts(pairs)` takes only (state mapping, contemporaneous mid) pairs.
Required common fields: sport (`mlb` or `nfl`), game_id, tick_ts,
mid_side=`home`, home_score and away_score. MLB requires inning; NFL requires
quarter and time_remaining_s, explicitly remaining regulation seconds.
The caller must supply an already matched contemporaneous book and home-side
orientation. No market resolver or archive adapter is added by this row.

- MLB: inning >= 7 and absolute score difference <= 3. Extra innings included.
- NFL: quarter == 4, regulation clock from 0 through 600 seconds, absolute
  score difference <= 8. Overtime excluded.
- Inclusive home-side bands: [0.05, 0.20] and [0.80, 0.95]. No side flipping.
- Each state cell plus band is a distinct cell. Select its first eligible
  parsed tick per game. Sort inputs internally; output order is deterministic.
- Count distinct games separately in all four cells, including empty cells.
  Below 50 games: DESCRIPTIVE_ONLY. At the floor: MINIMUM_MET, which is only
  a population-count label and conveys no statistical conclusion.

Missing or malformed required values are ineligible and counted. Numeric
parsing imports the landed local_capture_runner_row.number; numeric validation
uses math.isfinite. This module takes no sizes or quantities. All venue times
use scripts.platformkit.execution.venue_time.parse_venue_time.

Same-game, same-time observable conflicts exclude that tick and count all its
rows. Equivalent duplicates coalesce. Conflicting optional expected-time
metadata becomes absent and is counted without changing membership.
Expected expiration is optional tick-vintage metadata, never an eligibility
condition or realized duration. Administrative close_time is never read or
used as a fallback. No field outside the documented observables is inspected.

Output contains membership rows, per-sport/cell/band counts and sorted game
IDs, plus input, invalid, conflicting, duplicate, eligible and ineligible
counts. Input accounting conserves all rows. Eligible ticks include later
ticks after first membership; diagnostics can record multiple issues per row.
No residual, correction, calibration statistic, fill or markout is computed.

## Reproduction and self-check

All fixtures live in tests/platformkit/ingame/test_late_game_cohorts.py;
there is no dependency on a gitignored fixture. No external input files or
video inputs are opened; input byte sizes and video resolution do not apply.

```text
python -m pytest tests/platformkit/ingame/test_late_game_cohorts.py -q -p no:cacheprovider
108 passed
python -m scripts.platformkit.ingame.late_game_cohorts --help
Exit 0; describes the in-memory API.
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/late_game_cohorts.py tests/platformkit/ingame/test_late_game_cohorts.py docs/evidence/harness/S367_late_game_cohorts_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S367_spec.md
```

Automated contract scan: 9 PASS, 0 FAIL (vocabulary, line endings, LOC,
additive schema, sampling, spec thresholds, proposed patch, removed artifacts,
and duplicate rows). Both Python files remain below 300 lines.

The 108 construct cases cover hidden-field blindness, first-tick selection,
inclusive bands, missing state, extra innings, regulation and overtime,
non-finite and malformed values, score and phase domains, fractional venue
timestamps, expected-time provenance, distinct-game floors for each band,
duplicates, same-time conflicts, input permutations, and conserved counts.

B self-check: only new files; no schema change, moved threshold, existing
reader change, archive sampling, fitted statistic, claim loop or deployment.
Absent required state is explicitly ineligible as the spec requires.
Q self-check: frozen cells and floor; construct-only cases. No scored trial,
preregistration claim, ledger charge, OOS claim or comparison across corpora.
Both residual signs and any joint correction belong to a later scored study.

## NOT VERIFIED

- Real archive schema adaptation, game linkage and contemporaneous pairing.
- Truth of caller-supplied home-side orientation and tick-vintage state.
- Real game counts, capture coverage or the distinct-game floor on any corpus.
- Calibration, residual hypotheses, multiple-testing correction or stability.
- Any fill or markout behavior, production integration or pod operation.
- Master-tree verifier reproduction, commit creation and lane landing.
