# Q6 LANGUAGE-RAIL AUDIT -- 2026-09-03

VERDICT: **PASS -- 0 CLAIM rows.** Every money/edge token and every retracted figure in the
audited set is rule-text, retraction-context, an honest-negative framing, a shell `$`, or a
non-monetary word ("unit" = corpus unit, "units" = CLV series unit, "edge" only inside a ban).

## Method

Linter: `governance/honesty_linter.py` + `governance/policy.py` (`BANNED_NUMBERS`,
`BANNED_TOKENS`, `RETRACTION_MARKERS`, `find_banned_numbers`, `is_retraction_context`).
Neither module exposes a CLI for arbitrary files, so a 40-line scratch driver
(`<scratchpad>/q6_scan.py`, not committed) imported `governance.policy` and reused its
token lists verbatim, running them line-by-line over the audited files. The retracted
figures are matched by policy's whole-token regexes (`_num_pattern`, which refuses a match
embedded in a longer number), so the two retracted-artifact tokens `0.119` and `8.94` cannot
fire as substrings of an unrelated number.

Money/claim words beyond the policy list -- `dollar(s)`, `$`, `roi`, `profit*`, `edge`,
`bankroll`, `pnl`, `unit(s)` -- were matched with word boundaries, plus a "beats the
close/market/line" sentence regex and a follow-up grep for
`beat|outperform|alpha|profitab|positive ev|tradeable|kelly edge`.

Audited in full (checks a+b+c): `docs/evidence/HARNESS_GAPS_2026-09-03.md`,
`docs/evidence/RESULTS_LEDGER_SYSTEM.md`, `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
`docs/evidence/harness/*.md` (2 files), `docs/evidence/tracking/specs/S*_spec.md` (17 files),
and the 5 named plans under `docs/research/organization-sprint/`.
Retracted-figure check only: `README.md`, `docs/JOB_EVIDENCE_PACKET.md`.

## Findings

Repeated boilerplate is collapsed to one row per line; the `token` column lists every token
matched on that line.

| File | Line | Token(s) | Verdict | Replacement wording |
|---|---|---|---|---|
| docs/evidence/HARNESS_GAPS_2026-09-03.md | 5 | dollar, roi, edge | rule-text | -- (the register's own ban) |
| docs/evidence/HARNESS_GAPS_2026-09-03.md | 98 | dollar, roi, profit, edge | rule-text | -- (Q6 statement) |
| docs/evidence/HARNESS_GAPS_2026-09-03.md | 100 | 18.38, 0.119, 54, 78.11, 8.94, 54.57 | retraction-context | -- (enumerated as "outside an explicit retraction") |
| docs/evidence/HARNESS_GAPS_2026-09-03.md | 101 | edge | honest-negative | -- ("Accuracy is not edge; an honest REJECT ... is a success") |
| docs/evidence/RESULTS_LEDGER_SYSTEM.md | 4 | dollar, roi, profit, edge | rule-text | -- (ledger header ban) |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 27 | unit | rule-text | -- ("the metric's unit is recycled", B9; not money) |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 38 | dollar, roi, profit, edge / 18.38, 0.119, 54, 78.11, 8.94, 54.57 | rule-text + retraction-context | -- (Q6 clause itself) |
| docs/evidence/tracking/specs/S01_spec.md | 17 | dollar, roi, profit, edge | rule-text | -- ("Calibration language only: no dollar, ROI, profit or edge word.") |
| docs/evidence/tracking/specs/S02_spec.md | 21 | dollar, roi, profit, edge, unit | rule-text | -- (same rail; "per-unit" = corpus unit) |
| docs/evidence/tracking/specs/S03_spec.md | 14, 16 | unit, units | rule-text | -- ("both unit rates", "two corpus units"; not money) |
| docs/evidence/tracking/specs/S03_spec.md | 17 | dollar, roi, profit, edge, unit | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S04_spec.md | 23 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S05_spec.md | 17 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S06_spec.md | 24 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S11_spec.md | 22 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S12_spec.md | 25 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S13_spec.md | 17 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S14_spec.md | 20 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S15_spec.md | 22 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S16_spec.md | 18 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S17_spec.md | 22 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S20_spec.md | 7 | dollar, roi, profit, edge, units | rule-text | -- ("Units only. No dollar, ROI, profit or edge word in code, JSON keys, or memo text."); "beat rate" on the same line is a defined CLV-series statistic, not a result |
| docs/evidence/tracking/specs/S20_spec.md | 17 | dollars, roi, edge, units | rule-text | -- ("Language rail (Q6): a CLV SERIES in units, never dollars, ROI or edge.") |
| docs/evidence/tracking/specs/S23_spec.md | 17 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/tracking/specs/S27_spec.md | 8, 9 | edge, roi | rule-text | -- (edge/ROI-language *probes* that must return `refused`) |
| docs/evidence/tracking/specs/S27_spec.md | 22 | dollar, roi, profit, edge | rule-text | -- (same rail) |
| docs/evidence/harness/S20_premise_2026-09-03.md | 40, 49 | (bankroll) | rule-text | -- `m1_bankroll` / `paper.bankroll_daemon` are running-process identifiers in a PID census, not a claim; excluded by the word-boundary rule and recorded here for completeness |
| PLAN_HARNESS_EXECUTION_2026-09-03.md | 26, 71, 75 | units, unit | rule-text | -- (corpus units / per-unit rates) |
| PLAN_HARNESS_EXECUTION_2026-09-03.md | 145 | dollars, roi, edge | rule-text | -- ("Language rail: a CLV SERIES, never dollars/ROI/edge.") |
| PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md | 4 | dollar, roi, edge | rule-text | -- (plan header ban) |
| PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md | 65, 67 | units | honest-negative | -- ("AHEAD/PAR/BEHIND the devigged close by X units median, n=..., CI ..."): a verdict template in CLV units, no result asserted |
| PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md | 68 | dollars, roi, edge | rule-text | -- ("No dollars, ROI or 'edge' -- the honesty linter runs on the readout before commit.") |
| PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md | 100, 106 | edge, roi | rule-text | -- (edge/ROI probes must return `refused` citing no-edge-claims.md) |
| PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md | 135, 136, 138 | $ | rule-text | -- shell variable expansion (`$f`, `$FILES`), not currency |
| PLAN_AI_ENGINEERING_2026-09-03.md | 6 | edge | rule-text | -- ("Nothing here claims an edge.") |
| PLAN_AI_ENGINEERING_2026-09-03.md | 75, 77-84, 86, 115, 127, 135-141 | $ | rule-text | -- shell variable expansion in the `codex-sport` diff sketch and the usage snippet, not currency |
| MASTER_ROADMAP_2026-09-03.md | 25 | dollar, roi, edge | rule-text | -- ("No dollar, ROI or edge language, ever") |
| MASTER_ROADMAP_2026-09-03.md | 26-27 | edge / 18.38, 0.119, 54, 78.11, 8.94, 54.57 | retraction-context | -- ("the retracted ... figures are never printed as current"), cites `no-edge-claims.md` |
| MASTER_ROADMAP_2026-09-03.md | 93 | unit | rule-text | -- (`corpus_unit`, ATP/WTA) |
| MASTER_ROADMAP_2026-09-03.md | 130 | dollar, roi, edge | rule-text + honest-negative | -- S18 row: "a sizing haircut derived from calibration error, not a claim that any advantage was realized"; ends "LANGUAGE RAIL: no dollar, ROI or edge framing anywhere in this row's artifacts." |
| MASTER_ROADMAP_2026-09-03.md | 134 | dollars, roi, edge | rule-text + honest-negative | -- S20 row: "this produces a CLV SERIES, not an edge; nothing here is quoted in dollars or ROI"; measured state stated as "maker pool EMPTY, 0 settled forward CLV rows" |
| MASTER_ROADMAP_2026-09-03.md | 266 | dollars | rule-text | -- ("no claim is in dollars, ever") |
| MASTER_ROADMAP_2026-09-03.md | 354 | edge | honest-negative | -- ("reported as a CLV series, never as an edge") |
| MASTER_ROADMAP_2026-09-03.md | 360 | edge | honest-negative | -- ("Accuracy is not edge. The market is efficient; we match the close") |
| docs/JOB_EVIDENCE_PACKET.md | 227 | 18.38 | retraction-context | -- "debunked his own flagship '+18.38% ROI'"; explicit debunk framing (the linter's per-line marker list misses the verb "debunked", so it reads BARE -- see NOT VERIFIED) |
| docs/JOB_EVIDENCE_PACKET.md | 256 | 18.38 | retraction-context | -- inside the "Do-not-claim list" table, "Market-follow artifact" |
| docs/JOB_EVIDENCE_PACKET.md | 258 | 54, 78.11, 54.57 | retraction-context | -- same table, "A model-quality ceiling, not a tradeable result" |
| docs/JOB_EVIDENCE_PACKET.md | 259 | 8.94 | retraction-context | -- same table, "Circular ... No real Pinnacle-close CLV exists yet" |
| docs/JOB_EVIDENCE_PACKET.md | 266 | 54 | (false positive) | -- "~54% carry a Claude co-author trailer": an unrelated percentage that matches policy's context-gated `54` pattern. Not a retracted figure; no change |

No sentence in any audited file asserts the system beats the close or the market pregame.
The regex sweep for `beat(s) the close/market/line`, `outperform`, `alpha`, `profitab*`,
`positive EV`, `tradeable` and `kelly edge` returned zero matches across the 27 fully
audited files. The only claim-shaped sentence about the close is
`MASTER_ROADMAP_2026-09-03.md:360` -- "we match the close" -- which is the sanctioned
calibration framing from `.claude/rules/no-edge-claims.md`.

## Totals per file

| File | Retracted-figure hits | Money/claim-word hits | CLAIM rows |
|---|---|---|---|
| docs/evidence/HARNESS_GAPS_2026-09-03.md | 6 (all retraction-context) | 8 | 0 |
| docs/evidence/RESULTS_LEDGER_SYSTEM.md | 0 | 4 | 0 |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 6 (all retraction-context) | 5 | 0 |
| docs/evidence/harness/S20_premise_2026-09-03.md | 0 | 0 (2 process-name `bankroll` mentions) | 0 |
| docs/evidence/harness/S28_prepush_guard_2026-09-03.md | 0 | 0 | 0 |
| docs/evidence/tracking/specs/S01..S17,S19,S23 (15 files) | 0 | 4-7 each (60 total) | 0 |
| docs/evidence/tracking/specs/S20_spec.md | 0 | 9 | 0 |
| docs/evidence/tracking/specs/S27_spec.md | 0 | 8 | 0 |
| PLAN_HARNESS_EXECUTION_2026-09-03.md | 0 | 6 | 0 |
| PLAN_SIGNAL_FACTORY_2026-09-03.md | 0 | 0 | 0 |
| PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md | 0 | 14 (3 are shell `$`) | 0 |
| PLAN_AI_ENGINEERING_2026-09-03.md | 0 | 20 (19 are shell `$`) | 0 |
| MASTER_ROADMAP_2026-09-03.md | 6 (all retraction-context) | 14 | 0 |
| README.md (figures only) | 0 | n/a | 0 |
| docs/JOB_EVIDENCE_PACKET.md (figures only) | 7 (6 retraction-context, 1 false positive) | n/a | 0 |
| **TOTAL** | **25 occurrences, 0 live** | **148** | **0** |

Denominators: 27 files fully audited (a+b+c) + 2 files figure-only = 29 files.
`docs/evidence/tracking/specs/S19_spec.md` (20 lines) has zero hits of any kind.

## NOT VERIFIED

- Whether every hit's surrounding paragraph (as opposed to its own line) preserves the
  retraction framing. Classification was line-scoped, matching `policy.is_retraction_context`,
  with manual paragraph reads only for the JOB_EVIDENCE_PACKET rows and the four
  MASTER_ROADMAP/S20/S27 rows whose lines exceeded the 200-char excerpt.
- `governance/honesty_linter.py` was not executed as a program over these files -- it has no
  file CLI. Its token lists were imported and applied by the scratch driver; the driver's
  own correctness was not unit-tested.
- The extended money-word list (`dollar`, `profit`, `edge`, `unit`, `bankroll`, `pnl`) comes
  from the Q6 clause and `predict_service/honesty_mw.py:_FORBIDDEN_MONEY_KEYS`, not from
  `governance/policy.BANNED_TOKENS` (a 15-entry list of hard claim phrases -- read it there;
  the phrases themselves are never quotable, even in a retraction). Zero `BANNED_TOKENS`
  matches occurred anywhere in the audited set.
- `docs/research/organization-sprint/PLAN_TRACKING_RESEARCH_2026-09-03.md` exists but was not
  in this lane's scope and was not audited.
- `README.md` was checked for retracted figures only; its ~31 lines containing money-adjacent
  words were not classified, per the lane's scope.
- No audited file was edited. This memo is the lane's only write.
