# S07 forward primacy evidence

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q8.

## Result

ACCEPT. Metric: label correctness; denominator: four exhaustively constructed
cases. Before: 0/4 labelled. Bar: 4/4. After: 4/4.

## Step 0 premise

Command:

```powershell
git show HEAD:scripts/platformkit/ingame/forward_evidence_scoreboard.py
git show HEAD:scripts/platformkit/predictive_validity/validity_ladder.py
git show HEAD:scripts/platformkit/ingame/test_forward_evidence_scoreboard.py
# each piped to Select-String 'primacy|RETROSPECTIVE|provenance|claim_source'
```

Output: `NO_HITS`.

Pre-change real row:

```json
{"days_accruing": 61.20633448332176, "distance_to_decidable": "1163_DAYS", "forward_n": 1, "gate": "tail_H1_longshot_underpriced", "pre_registered_at": "2026-07-03T00:00:00Z", "source": "C:\\Users\\neelj\\nba-track-a10\\data\\domains\\mlb\\ingame_tail_verdict.json", "sport": "mlb", "verdict": "INSUFFICIENT_FORWARD"}
```

`CLAIM_NAMING_FIELDS=0`; therefore before is 0/4. The re-grep found two
field readers: `validity_ladder.py` (style reference only) and
`test_forward_evidence_scoreboard.py`; `scripts/FILE_INDEX.md` is only an
index. Both were checked before the additive field change.

## Constructed decision set

| Case | Forward | Retrospective | Selected provenance | Conflict |
|---|---|---|---|---|
| a | AHEAD | AHEAD | FORWARD | false |
| b | AHEAD | BEHIND | FORWARD | true |
| c | BEHIND | AHEAD | FORWARD | true |
| d | INSUFFICIENT, n=2/min_n=5 | AHEAD | RETROSPECTIVE | false |

All four cases are included. Case c prevents selecting the more flattering
retrospective result when a usable forward result disagrees.

## Live state and protected outputs

Command:

```powershell
python -c "from scripts.platformkit.ingame.forward_evidence_scoreboard import build_scoreboard; doc=build_scoreboard(); print(sum(row['forward_n'] == 0 for row in doc['rows']))"
```

Output: `12` of `17` rows have `forward_n == 0`. Every current scoreboard row
has `claim_label=RETROSPECTIVE`; pre-existing row keys retain their captured
value, verified by the focused test's label interception. `OUT_PATH`,
`COMPONENT`, all prior row values, `honest_note`, and the existing boolean
claim flag are unchanged. No evaluation threshold changed. The local
`data/cache/eval_gate/backtest_fwer.jsonl` file is absent in this worktree;
it was not written, and the S07 files contain no `_charge_ledger` call.

## Reproduction

```powershell
python -m pytest scripts/platformkit/ingame/test_forward_evidence_primacy.py -q
# ..... [100%]
# 5 passed in 1.69s
python -m pytest scripts/platformkit/ingame/test_forward_evidence_scoreboard.py -q
# ............. [100%]
# 13 passed in 1.66s
```

Reproduction is the S-row check: rerun both files and print one row from
`build_scoreboard()`; it contains both added label fields.

## Contract self-check

- B1: all four enumerated cases are scored; none excluded.
- B2: only `claim_provenance` and `claim_label` are added; reader test passes.
- B3: absent or insufficient forward input receives an explicit retrospective label.
- B4: selection is stateless and creates no repeat-claim path.
- B5: no deployment action occurred.
- B6: no module moved or retired.
- B7: this is exhaustive construction, with no render sampling.
- B8: no fitted residual is represented as independent evidence.
- B9: the denominator is four distinct, enumerated decisions.
- B10: no harness threshold changed.
- Q1: no empirical comparison is scored; this is a four-case construct.
- Q2: no trial is charged and no ledger metric is computed.
- Q3: bar remains 4/4.
- Q4: no OOS model or meta-learner is scored.
- Q5: no live AHEAD claim is made.
- Q6: calibration language only.
- Q7: n=4 (CONSTRUCT), and the table enumerates the complete decision set.
- Q8: the symbol and row-schema premise was re-measured before implementation.

## NOT VERIFIED

- No forward settled series exists yet.
- S20 has 0 settled rows.
- Every live claim is RETROSPECTIVE today; the FORWARD branch is exercised only by construction.
