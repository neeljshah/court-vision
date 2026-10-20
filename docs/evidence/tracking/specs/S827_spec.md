# S827 -- a missed night D-1 leaves night D's scoreboard with a bare --history (2026-10-20)

Row: docs/evidence/HARNESS_GAPS_2026-09-03.md `| S827 |` (allocated 2026-10-19 by paper-desk-improve).
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B and Q. PAPER ONLY; calibration
language only. Night-side files only; no seal / identity file is touched.

## 1. Premise (fresh reads, master 6ad349cf2, Q8)

Night 2026-10-16 receipt, docs/evidence/forward/nights/2026-10-16.json, step `scoreboard` (lines 386-437):

- argv ends `"--as-of", "2026-10-17T06:00:00Z", "--history"` (no path after `--history`);
- `"history_refused": 0`, `"history_refusal_reason": null`, `"step_status": "RAN"`, `"exit_code": 0`,
  `"training_label": "A_ONLY"`, `"no_fitted_arm": true`, `"wall_s": "25.656"`.

The rows on disk in the forward scoreboard training dir at 15:45Z 10-20: 2026-10-10, 10-11, 10-13, 10-14,
10-15, 10-17 (manifests under docs/evidence/forward/scoreboard/training/ for 09-30 .. 10-17 with gaps at
10-02, 10-12, 10-16). Night 10-15 never ran, so training/2026-10-16.jsonl was never written; the newest
file before 10-16 was training/2026-10-15.jsonl. PREMISE HOLDS.

Second live occurrence: night 10-19 (pid 5348, started 15:37:10Z 10-20) runs with no training/2026-10-19
(nights 10-17 / 10-18 never ran). Its receipt is recorded in section 8 once it exists.

### Code (master)

scripts/platformkit/execution/paper_night_steps.py:274-300 (pre-S827):

```
def scoreboard_step(root, day, as_of, sports, p, raw):
    """List only this consuming night's manifest-validated training rows."""
    candidate = _local(root, raw["training_rows"].format(date=day))
    history, refusal = [], None
    try:
        config = None
        if candidate.is_file() and manifest_path(root, day).is_file():
            ... config = history_config(day, cumulative_lookback(day, int(p["history_lookback_days"])),
                                        POLICY["fit"]["embargo_days"], sha256(prereg))
        pair = validate_pair(candidate, manifest_path(root, day), config)
    except (ValueError, OSError) as exc:
        pair, refusal = None, ...
    if pair is not None:
        history.append(candidate.relative_to(root).as_posix())
    ...
    return dict(..., history_refused=int(refusal is not None), history_refusal_reason=refusal)
```

validate_pair (scoreboard_history_store.py:252-255): `if not rows.exists(): return None` -- an absent own
file is neither a pair nor a refusal, hence history_refused 0 / reason None and a bare `--history`.

paper_night_inputs.py:76-82 (the planner) walks `for offset in range(1, int(p["history_lookback_days"]) + 1)`
and collects every existing training/<D-offset>.jsonl, but paper_night.py:97-98 overwrites it:
`plan["history"] = own["argv"][own["argv"].index("--history") + 1:] if own else []`, so the consuming step
decides alone. The planner list is never consumed.

Receipt path: paper_night.py:101 `s.update({k: v for k, v in own.items() if k.startswith("history_refus")})`
and :128 (inside `_run`, byte-pinned by S489 C22) `row.update({k: v for k, v in step.items() if
k.startswith("history_refus")})`. The receipt therefore whitelists step keys by the PREFIX `history_refus`;
paper_night.py stays untouched, so every new field carries that prefix (section 3).

## 2. RULING on (b) -- ACCEPT (the fallback is consistent with the S766 text)

S766 text, docs/evidence/harness/CONSOLIDATED_SEAL_2026-10-06.md line 15 (verbatim):

> HISTORY = dict(start='2026-09-22', max_games_per_sport=120): the history for night D is every served night
> from 2026-09-22 (the first served maker_forward schedule; capture archive starts 09-21) through D-4; embargo
> unchanged (3 days: ticks and settlement strictly before D-3 00:00Z, applied by the producer boundary AND
> again by the scorer); admission by settlement (a game enters only with a real 0/1 outcome and close before
> the boundary); at least the newest 120 settled games per sport are kept ...

Clause (f) (same file, section 5): "Old-night failures do not stick: for consuming night N, a night at or
before N-5 whose schedule is invalid ... is recorded (incomplete ...), contributes no rows, ... and the pair
is still published (exit 0) from the remaining nights, subject to the floor". Clause (i) of the S766 row
(the per-night population slice) concerns step e's read volume and does not bear on this question.

The deciding sentence is the embargo clause: "ticks and settlement strictly before D-3 00:00Z, applied by
the producer boundary AND again by the scorer". The causal guarantee of the history is the boundary, and the
boundary is re-applied for night D by the scorer itself, whatever file it is handed:

- producer: scoreboard_history.py:38 `boundary = _instant((day - timedelta(days=embargo)).isoformat() +
  'T00:00:00Z')` and :86 `if _instant(t['ts']) >= boundary or close >= boundary: raise
  ValueError('boundary_violation')`;
- store, every validate_pair: scoreboard_history_store.py:175 refuses any settled census game with
  `g['close_ts'] >= cfg['boundary']`, and :231 `if not row['ts'] <= row['close_ts'] <
  artifact['config']['boundary']: raise ValueError('corrupt_artifact:schema')`;
- scorer for night D: ingame_scoreboard.py:131 `boundary = _instant(day + 'T00:00:00Z') - 3*86400*1_000_000`
  and :135 `if _instant(r['ts']) >= boundary or _instant(r['close_ts']) >= boundary: continue`, plus :152
  drops any training game that is also one of tonight's test games.

A pair for consuming night d < D validated against history_config(d, ...) has boundary d-3 00:00Z, strictly
before D-3 00:00Z, so nothing in it settled on or after D (nor on or after D-3). Its content is "every served
night from 2026-09-22 through d-4", a causal subset of the D target. Today's behaviour on the same night is
the EMPTY history (zero nights), a strictly smaller subset of the same target; clause (f) already accepts a
pair with nights missing (skipped old nights contribute no rows) as a valid S766 history. HISTORY, the
embargo, the 120-game cap and TRAIN_FLOOR_GAMES are unchanged and are applied by the sealed scorer
unchanged. The fallback is therefore a degraded-but-causal input inside the S766 definition, not a policy
change; it needs no seal. It is labelled in the receipt (history_refusal_source_day != D) so a reader can
tell a stale history from the specified one.

Bounds the ruling attaches: (1) the fallback runs ONLY when the own rows file is absent; an own file that is
present but refused (config_mismatch, corrupt, legacy_nba_pair, ...) keeps today's fail-closed refusal and
never falls back; (2) candidates are d = D-1 .. D-L with L = int(p["history_lookback_days"]) (7 in the live
budget), the planner's own bound -- at most 7 nights stale; (3) each candidate validates against ITS OWN
day's config (history_config(d, cumulative_lookback(d, L), embargo, sha256(prereg))) with the same prereg
path as night D, so a pair produced under another prereg refuses config_mismatch and is skipped; (4) a belt
check refuses a validated pair whose recorded `config.boundary` is not strictly before night D's own
boundary (`boundary_not_before_night`).

## 3. The change

New companion module scripts/platformkit/execution/paper_night_history.py (<= 300 LOC): `_attempt` (the
pre-S827 try-block moved verbatim, the S766 comment with it) and `history_rows(root, day, p, raw)`.
paper_night_steps.py: scoreboard_step calls history_rows and returns `**fields`; net -13 lines (300 -> 287);
no assertion or AMENDMENT comment is removed (the 2(a) dedup comment stays on its line). The companion calls
scoreboard_history_store via the module (store.validate_pair), never edits it.

Step-dict fields (also in the night receipt via the existing `history_refus` prefix copy; additive, B2):

| field | value | meaning |
|---|---|---|
| history_refused, history_refusal_reason | unchanged | the OWN pair's refusal, exactly as before |
| history_refusal_own_absent | 0 / 1 | 1 when training/<D>.jsonl is absent (night D-1 did not publish) |
| history_refusal_source_day | D, d < D, or None | the day whose pair is on the argv |
| history_refusal_fallback_skipped | {reason: n} | refusal reasons of fallback candidates passed over; `absent` = no rows file |

The task named these history_source_day / history_absent_prior_night / history_fallback_skipped; the prefix
is forced by paper_night.py:101 / :128 (the `_run` body is byte-pinned), recorded here as the decision.
The chosen file goes on the argv exactly as the own path does (`--history <training/<d>.jsonl>`), so the
receipt's argv names it too.

Readers (A5): the issue scanner (scripts/platformkit/ops/paper_desk_issue_checks.py:129-160) reads only a
step's name, step_status, reason and started_utc; night_coverage_census.py:128-129 reads step_status and
reason; nothing reads history_refus* except tests and s580_evidence prose. The scanner therefore does
nothing with the new fields today; turning history_refusal_own_absent 1 into an issue is a follow-up row,
not in scope.

Test pin: tests/platformkit/ops/test_s485_baseline_contract.py S746_REPIN carries the LF sha256 of
paper_night_steps.py; re-pinned to the S827 bytes (S746 fix-round precedent).

## 4. Acceptance (one runnable check each, tests/platformkit/execution/test_s827_history_fallback.py)

Pairs are written by the REAL producer (scoreboard_history.main through the `native` fixture of
test_scoreboard_history.py) under the S766 start 2026-09-22.

- (i) own file present: argv and every pre-S827 field byte-identical to the pre-S827 scoreboard_step, which
  the test executes from the committed bytes of master 6ad349cf2 (`git show`); also for an own file that is
  unmanifested, an own pair with config_mismatch, and an absent own file with no candidate.
- (ii) own absent, training/<D-1> valid: argv `--history training/<D-1>.jsonl`, source_day D-1,
  own_absent 1, history_refused 0.
- (iii) own absent, no valid candidate: bare `--history`, own_absent 1, history_refused 0, skipped
  {absent: 7}.
- (iv) a candidate failing config_mismatch (pair produced under another prereg sha) is skipped and counted
  ({config_mismatch: 1}); the next older valid pair is used.
- (v) the chosen manifest's `config.boundary` (night 10-08: 2026-10-05T00:00:00.000000Z) is before night
  10-09's boundary and every row's close_ts is before it; a validated pair whose boundary is tampered to
  reach night D's boundary is refused `boundary_not_before_night`.
- bound: with L = 7, a pair at D-7 is used and a pair at D-8 is never read.
- mutations: a candidate newer than D is never a candidate; an empty unmanifested rows file is skipped
  (corrupt_unmanifested_rows); a CRLF manifest validates (JSON whitespace; the rows commit binds the pair),
  CRLF rows refuse corrupt_artifact:rows_sha256.
- receipt: the three new fields reach nights/<D>.json through night.main; paper_night.py carries exactly two
  `if k.startswith("history_refus")` copies.

## 5. Non-goals / follow-up

- S809 live_shadow_fit.py:106-109 reads training/<D> alone; it stays dark after a missed night (follow-up).
- The scanner raises nothing on history_refusal_own_absent 1 (follow-up row if wanted).
- A present-but-refused own file never falls back (fail closed by design).

## 6. Tests (one process per file, run_files.py)

New file plus every existing test file importing paper_night_steps or paper_night_inputs (section 7 of the
memo lists counts), plus test_s485_baseline_contract.py (re-pin).

## 7. Tiers

CONTRACT (A/B/Q against this spec; its own ruling on (b)) then ADVERSARIAL (probes + mutations), one Opus
subagent at a time, verdicts under C:/Users/neelj/AppData/Local/Temp/claude/s827/.

- CONTRACT (Opus, 2026-10-20 ~16:50Z): ACCEPT, no corrections; own ruling on (b): consistent with S766
  (deciding sentence: the embargo clause, boundary applied by the producer AND again by the scorer).
  Notes N1-N4 (N3: a fallback night now takes the full scored path; watch its wall_s against 3,600 s).
- ADVERSARIAL (Opus, ~17:15Z): ACCEPT WITH CORRECTIONS; 19 of 20 mutants killed. F1: a fallback candidate
  resolving outside the root raised through the planner -> now counted `path_outside_root` and skipped.
  F2: a directory at the own rows path (the surviving `is_file()` mutant) -> new `directory` case in the
  pre-S827 byte-identity parametrize. Both applied; the new file re-run 18 passed.

## 8. Live occurrences

- night 2026-10-16: bare `--history`, history_refused 0, A_ONLY (section 1).
- night 2026-10-19 (receipt nights/2026-10-19.json, run 15:37Z-16:31Z 10-20, night status PARTIAL from a
  qualification child_nonzero_exit, not this row): scoreboard argv ends with a bare `"--history"` (line 261),
  `"history_refused": 0`, `"history_refusal_reason": null`, `"step_status": "RAN"`, `"exit_code": 0`,
  `"training_label": "A_ONLY"`, `"no_fitted_arm": true`, `"wall_s": "65.531"`. Second live occurrence,
  premise reproduced. Its history step wrote training/2026-10-20.jsonl (seen on disk at 16:31Z), so night
  10-20 should consume its own pair (history_refusal_source_day 2026-10-20, history_refusal_own_absent 0).
