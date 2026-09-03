# S167 Connectivity Follow-ups - 2026-09-04

## Scope

This memo re-measures exactly four S160 connectivity findings. It is additive to
`docs/evidence/CONNECTIVITY_2026-09-04.md`; no landed row was edited. The completed
denominator is 4/4 follow-up rows.

## Before and after

| Link | Before | After | Verdict |
|---|---|---|---|
| L4 | FAIL before a proof corpus loaded because gitignored `src.prediction.bet_grades` was absent from this worktree. | After copying that one read-only file from the main repository, two corpora ran. All six V3 signal outcomes matched expected REJECT; V1 calibration failed in both, so the proof ended PARTIAL/FAIL, exit 1. | FAIL |
| L8 | FAIL because `scripts/mcp_server/tools.py` was an incorrect path. | `artifact_tools.harness_health({})` returned `status=no_data`; `tools._system_health({})` returned `status=ok`, both in process, exit 0. | PASS |
| L9 | PASS reported 23 Markdown-link occurrences. | The stated unique-path scope covers Markdown targets and slash-containing inline-code paths, expanding brace groups. 31 of 34 exist; three paths are absent. | FAIL |
| L2 | NOT TESTABLE HERE because the CLI hard-coded `write=True`. | The new additive `--no-write` flag called the same builder with `write=False`, printed all four scoreboard rows, and exited 0 without writing artifacts. | PASS |

## L2 printed calibration rows

- NBA: n=4,846; baseline ECE=0.02614; improved ECE=0.01755.
- TENNIS: n=9,006; baseline ECE=0.04951; improved ECE=0.01856.
- MLB: n=8,395; baseline ECE=0.01732; improved ECE=0.01379.
- SOCCER: n=25,834; baseline ECE=0.03294; improved ECE=0.03128.

## NOT VERIFIED

- No live-system probe was performed for L8; both handlers are read-only local calls.
- L9 does not infer the existence of `.claude/commands/workday-loop.md`,
  `data/intelligence`, or `data/nba_ai.db`.
- L4 does not turn the local V3 wiring check into a passing calibration claim;
  its observed V1 failures remain part of the final proof verdict.
- L4 V1 calibration failure was not independently reproduced by the verifier.

## Contract self-check

The four S167 rows are exhaustive (n=4 construct). No scored comparison,
threshold change, FWER-ledger action, `data/` write, or feature-flag change was
made. B1-B10 and Q1-Q9 are satisfied: no excluded failures, no changed bar, no
claim beyond the printed calibration/connectivity results, and no market language.
