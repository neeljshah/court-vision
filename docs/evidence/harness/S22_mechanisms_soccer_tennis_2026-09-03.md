# S22 -- soccer + tennis mechanism wiring against the devigged close (2026-09-03)

Lane M (main repo). Register row S22: "soccer 0/15 and tennis 0/23 mechanisms
wired, blocked only by the close join". Both are now **15/15** and **23/23**.

DESCRIPTIVE_ONLY throughout. Calibration language only (Q6). **No ledger trial
was charged** -- this is mechanism WIRING (corpus infrastructure plus NULL /
CONFIRMED_LOCAL descriptive effects), not an AHEAD trial.

## Premise check (Q8) -- re-measured, not assumed

`mechanism_exposure.parse_mechanisms` on the two ledgers returns exactly 15
soccer and 23 tennis CONFIRMED/REPLICATED sections. The on-disk
`out/mechanism_exposure.json` BEFORE this lane reported
`soccer {wired: 0, not_wired: 15}` and `tennis {wired: 0, not_wired: 23}`
(NBA 27, MLB 22). Premise TRUE.

Two parse quirks found and recorded rather than hidden: soccer section 2
(state-conditioned shot model) and tennis section 8 (double-fault by set 3) are
both REJECTED rows that parse as confirmed because their status strings contain
the substrings "REPLICATED" / "CONFIRMED_LOCAL". They are wired like any other
row, with the quirk named in the row's own reason.

## What the close join actually delivers

| sport | gate corpus | states with a devigged close | outcome `y` | corpus_units |
|---|---|---|---|---|
| soccer | 25,834 rows 2015-08-07..2026-05-24 | **16,322** (2019-08-02..2026-05-24) | over 2.5 total goals | E0 E1 D1 F1 I1 SP1 |
| tennis | 41,886 rows 2015-01-04..2025-12-17 | **33,685** | p1 win | ATP, WTA (never pooled) |

Vintage **SYNTHETIC** (S34) is carried into every artifact row and into the
top-level `vintage` field of both JSONs.

## S50 ordering (coordinator note, audited both sports)

- **tennis: confirmed.** The concatenated gate frame is NOT globally
  chronological -- one backward jump, at row 30,616 exactly, where ATP
  (rows 0..30,615, 2015-01-04..2025-12-17) gives way to WTA (rows
  30,616..41,885, 2015-01-19..2025-11-01). Each unit is internally monotonic.
- **soccer: no such defect.** `event_date` on `gate_corpus_soccer.parquet` is
  globally monotonic with **0** backward steps; the six `div` corpus_units are
  date-interleaved (E1 starts at index 0, I1 at 117, SP1 at 87) and each unit is
  itself monotonic. Nothing to fix on the soccer side.
- Every measurement here is taken INSIDE one `corpus_unit` and each unit's own
  date range is printed in the artifact; no measurement crosses the boundary.

## Effect definition (identical for both sports)

For a mechanism whose declared column(s) exist in the scored corpus:
`residual = outcome - devig_close_prob`; within each `corpus_unit`, split the
trigger at its own median and report
`effect = mean(residual | high) - mean(residual | low)`, `p` from a two-sided
Welch t-test, and `n` per unit. Bars are the soccer/tennis mechanism ledgers'
own house convention, copied not invented and never lowered:
**|effect| >= 0.02 AND p < 0.01**, minimum coverage 0.25 of the scored rows,
minimum 30 rows a side. A mechanism is CONFIRMED_LOCAL only if EVERY scored
corpus_unit clears both bars with the same sign; otherwise NULL_LOCAL. A
declared column absent from the corpus is NOT_TESTABLE **with the column named**.

## Result

| sport | wired/defined | with trigger | CONFIRMED_LOCAL | NULL_LOCAL | NOT_TESTABLE |
|---|---|---|---|---|---|
| soccer | **15/15** | 0 | 0 | 0 | 15 |
| tennis | **23/23** | 3 | 0 | 3 | 20 |

`out/mechanism_exposure.json` after the rebuild: `soccer wired 15 not_wired 0`,
`tennis wired 23 not_wired 0`, `basketball_nba 27` and `mlb 22` unchanged.

### The three tennis rows that reached a measured effect

| mechanism | trigger | verdict | ATP | WTA |
|---|---|---|---|---|
| serve-tier x return-tier pairing | `(p1_hold_pct_asof - p2_hold_pct_asof) * diff_return_won_asof` | NULL_LOCAL | n=25,115 eff=+0.001945 p=0.7300 | n=0 |
| serve advantage erodes on clay | `p1_hold_pct_asof - p2_hold_pct_asof` masked to `surface == 'Clay'` | NULL_LOCAL | n=7,582 eff=-0.001788 p=0.8627 | n=1,804 eff=+0.045021 p=0.0280 |
| break-point-save differential | `diff_break_pct_asof` | NULL_LOCAL | n=25,115 eff=+0.011585 p=0.0398 | n=0 |

All three are NULL_LOCAL. Nothing here is or claims to be a beat of the close;
a NULL is the expected and honest outcome for a single as-of column against the
strongest available forecast.

### Second measured finding: two as-of columns are ATP-only

`diff_return_won_asof` and `diff_break_pct_asof` are non-null on 29,179 and
29,181 of the 30,616 ATP rows and on **0 of the 11,270 WTA rows** of
`gate_corpus_tennis.parquet`. Both rows above are therefore labelled
`single_corpus_unit: true` with the WTA unit NOT_TESTABLE for the stated reason
("the declared trigger column is entirely null in this corpus_unit"), never
silently pooled into an ATP-only number wearing a tennis-wide n.
`p1_hold_pct_asof` / `p2_hold_pct_asof` / `surface` ARE populated for WTA, which
is why the clay row carries both units.

### Why soccer reaches 0 triggers

`gate_corpus_soccer.parquet` carries eleven feature columns, all pregame
shots / shots-on-target as-of aggregates, and scores an over-2.5-total-goals
label. Every CONFIRMED soccer mechanism's own ingredient is StatsBomb
event-grain (score state, possession id, shot type, PPDA, goal-kick height,
tactical shift), or lives on `data/domains/soccer_intl/results.parquet` (neutral
venue, competition type), or is an xG as-of column (`diff_xg_supremacy_asof`).
None is a column of the scored corpus. Each of the 15 rows names its own absent
column or artifact; that is a wired state with a measured data reason, not a gap.

## What was built

- `scripts/platformkit/analytics_showcase/mechanism_wiring_soccer.py` -- 15
  declared rows (DATA module), same contract as `mechanism_wiring_mlb.py`.
- `scripts/platformkit/analytics_showcase/mechanism_wiring_tennis.py` -- 23
  declared rows, 3 with a trigger (`expr`, `columns`, optional `mask`, `note`).
- `scripts/platformkit/analytics_showcase/mechanism_close_effect.py` -- the
  descriptive effect engine + CLI. Writes
  `out/mechanism_wiring_prereg_<sport>.json` BEFORE any effect is computed and
  embeds that declaration's SHA-256 (`prereg_sha256`) in the result artifact.
- `mechanism_wiring.py` -- `WIRING_BY_SPORT` gains `soccer` and `tennis`
  (additive; NBA `WIRING` and the MLB rows untouched).
- `mechanism_foundry.py` -- `FOUNDRY_SPORTS = ("basketball_nba", "mlb")` gates
  both the `--sport` choices and `prereg_rows`, so the NBA-`game_id`-keyed
  corpus machinery can never be handed a soccer/tennis row.
- `test_mechanism_close_effect.py` -- 15 tests, fixture-only.

## Verification (all run in MASTER, per-file only)

```
python -m pytest scripts/platformkit/analytics_showcase/test_mechanism_close_effect.py -q  -> 15 passed
python -m pytest scripts/platformkit/analytics_showcase/test_mechanism_wiring.py -q        -> 16 passed
python -m pytest scripts/platformkit/analytics_showcase/test_mechanism_exposure.py \
       scripts/platformkit/test_atlas_exposure_join.py \
       scripts/platformkit/eval_gate/test_close_join_soccer.py \
       scripts/platformkit/eval_gate/test_close_join_tennis.py -q                          -> 18 passed
python -m scripts.platformkit.analytics_showcase.mechanism_close_effect --sport soccer     -> 15 NOT_TESTABLE
python -m scripts.platformkit.analytics_showcase.mechanism_close_effect --sport tennis     -> 3 NULL_LOCAL, 20 NOT_TESTABLE
python -m scripts.platformkit.analytics_showcase.mechanism_exposure                        -> soccer 15 / tennis 23 wired
```

A2 reproduction (recomputed independently of the module, from
`gate_corpus_states` + `load_gate_corpus` directly): ATP break-point row
`n=25115 eff=0.011585 p=0.039808`, byte-identical to the artifact.

Ledger untouched: `data/cache/eval_gate/backtest_fwer.jsonl` is 14 lines,
md5 `b1b1253821b06bbf501ecb8f19937c9c`, mtime 2026-09-02 00:42:37 -- nine hours
before this lane ran. `mechanism_close_effect.py` never imports
`backtest_runner` and has no ledger code path at all.

## The register bar this lane did NOT meet, and why

MASTER_ROADMAP section 2's S22 line asks for "AHEAD / BEHIND / NOT_TESTABLE".
Both of those verdicts come from a CHARGED `run_backtest` trial (the NBA lane
charged 9, moving cumulative K from 2 to 11). This lane is instructed not to
charge, so the verdict vocabulary here is the descriptive
CONFIRMED_LOCAL / NULL_LOCAL / NOT_TESTABLE instead. **Scoring these three
tennis triggers as AHEAD/BEHIND requires a charged trial (S12 T2)** and is not
done here. The MLB lane's own pattern is also NOT replicated in one respect: it
runs `mechanism_foundry --dry-run`, whose charged path exists; this lane's
engine has no charged path to disable.

## What is NOT verified

- No walk-forward, no purging, no embargo, no CPCV. The effect is a
  whole-corpus median split, so **Q4's leak contract does not apply to it and it
  cannot be read as an out-of-sample result**. It is a descriptive property of a
  frozen corpus, nothing more.
- The close carries a SYNTHETIC vintage (S34): its `state_ts` is constructed, so
  no timestamp evidence separates the close from the features. Any leak check
  over these states passes by construction.
- No prereg was SEALED in the S12/Q1 sense (no sealed artifact predating a
  scored metric). `prereg_sha256` seals this lane's own declaration file written
  before its own effects; it is not a registered prereg and no scored claim
  rests on it.
- The 15 soccer and 20 tennis NOT_TESTABLE reasons are disk-state claims as of
  2026-09-03. They say the ingredient is absent from the SCORED corpus -- not
  that the mechanism is false, and not that it could never be tested if the
  column were built at corpus grain.
- The three tennis triggers were measured ONCE each, on one frozen corpus, with
  the trigger rendering declared in each row's `note` (the serve x return
  pairing is a differential rendering of a per-player tercile cell, not the
  ledger's original cell construction).
- The MCP `courtvision.mechanism_exposure` tool was not called before or after;
  the before/after `per_sport` counts come from the on-disk artifact.
- No edits to `src/`, `kernel/`, `api/`, `intel/`, `eval_gate/`, the register, or
  `data/registry/`. No feature flag flipped. Nothing copied to the pod.
