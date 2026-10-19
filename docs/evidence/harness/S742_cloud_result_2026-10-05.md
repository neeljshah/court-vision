# S742 cloud result 2026-10-05 -- RULE half: opt-in live-concurrency served subset (default OFF)

Row: S742 (ALL-SPORTS block), one-off cloud run with the owner override: the RULE half of S742. The row's
status cell records that the measurement was already done. Read with S531 (soccer) and S624 (NFL), which
keep their rows and landings. Branch `cloud/S742-2026-10-05` (pushed). Trunk is untouched, nothing was
landed, and neither the register nor DESK_STATE was edited.

PAPER ONLY. Coverage language only: this row changes WHICH games the capture is asked to focus on, nothing
else. PORTABLE: yes (pure code plus tests on Ubuntu). Adoption is WINDOWS (recorder config, see below).

Spec: `docs/evidence/harness/S742_spec_2026-10-05.md` with AMENDMENT 1 (19 critic items).

## Verdicts

Codex was not used. Every review tier was an INDEPENDENT Opus sub-agent that did not write the code.

| Tier | Verdict |
|---|---|
| Pre-build critique (astra role) | REVISE, 19 items. All 19 were folded in as AMENDMENT 1 before the build. |
| CONTRACT (VERIFIER_CONTRACT A/B/Q + amended spec) | ACCEPT WITH CORRECTIONS (2). (1) The default-path byte test did not pin the capacity-note bytes; this was fixed in corrections 1 (50c8a249). (2) The per-day table for both rules belongs in this memo; it is below. The verifier reproduced the 10-04 headline and every per-day count with its own independent greedy and sweep. |
| ADVERSARIAL (31 mutants + probes) | ACCEPT WITH CORRECTIONS. 4 survivors mattered for the spec: M16 (validator rule compare dropped), M17b (bogus flag value), M18b (row marks stripped) and M21 (duration table ignored). All 4 are killed by test-only corrections 2. M07, M22 and M25 are reported equivalent (no difference on 20k random days). Probes: zero crashes; overlap > G 0 times in 4,000 random days; zero floor-bar breaches. The default path matches origin/trunk on 3,000 random unmarked days (sha256 equal). |

Correction rounds were test-only; production code is unchanged since 9ec6ed21. The builder re-ran the four
survivors on a scratch copy after corrections 2, and all four are KILLED:
- M16: 1 failed, 4 passed (s742 file)
- M18b: 1 failed, 4 passed (s742 file)
- M17b: 1 failed, 4 passed (s742 file)
- M21: 1 failed, 24 passed (served_concurrency file)

No REJECT was returned, so no second verification round was owed.

## The rule (served_concurrency.py)

**Live window.** A served game's live window is [scheduled_start, scheduled_start + typical duration). The
duration comes from `kalshi_series_scope.TYPICAL_DURATION_SEC`; a sport absent from the table uses
`DEFAULT_TYPICAL_DURATION_SEC`. That is 9000 s for nfl, 12600 s for mlb and 7500 s for soccer.

**Focus game capacity G.** G is derived at import from the capture's own constants, never a literal:
`forward_capture_profile.json` (validated against the same expected dict as capture_schedule_loader:15)
with anonymous_rate_ceiling 3 x focus_tick_s 5 = 15 requests per tick, x SHARES[0] 45 // 100 = 6 tickers,
// 2 book tickers per game = 3. A test asserts that `plan_tick(rate 3)` focuses exactly 2G tickers and G
games.

**Selection.** Greedy, in today's order (scheduled_start, game_id, ticker). A row is admitted only if, at
every instant where counts can change (its start plus every start and end of any selected row inside its
window), both of these hold:
- the open served windows + 1 <= G;
- the per-sport floor of 1 holds:
  - when the sports with a selected game live number n and n <= G, a slot stays reserved for each other
    live sport;
  - when n > G, each sport is limited to one slot.

**Recording.** Every unserved row is listed in the capacity note under `unserved` with
`cause: cap_concurrency`, `limit: total|floor`, `at`, and `reserved_for` on floor refusals. The note also
carries `capacity_rule`, `focus_game_capacity`, `floor_per_sport`, `live_duration_sec` and
`max_live_overlap`. Its `rule` text names the rule. The old note keys `served`, `not_served` and `rule` are
kept.

**Opt-in.** The option is `schedule_d1 --capacity-rule live_concurrency`; the default is
`starts_per_hour`, i.e. today. Every row of an option run carries `capacity_rule: live_concurrency`, on both
the full and served rows, so `served` stays an equality subset of `full` for schedule_recovery:227 and
paper_desk_evidence:50.

**Wiring (the five places the old rule lived).**
- capture_scheduler.schedule_rows:113. With no declared row the old expression is unchanged. With any
  declared row, the unmarked rows keep the old rule and all rows together must fit G. The refusal text is
  identical ("schedule exceeds two games per hour"), so schedule_pointer._admit_capacity still matches it.
  The file stays at 300 lines and imports the module lazily, only when a row is declared.
- paper_desk_schedule.validate. Allowlists the flag and recomputes subset, rule and unserved under the
  declared rule. It refuses a bogus value, stripped marks or a wrong rule.
- schedule_revise. Refuses `capacity_rule_unsupported` on a day published under the option.
- schedule_pointer is unedited and covered by the mixed-list rule. Both transitions are tested.

## Served counts, both rules, every committed day (no superset claim)

| Day | Selected | Old rule served (max overlap) | live_concurrency served (max overlap) |
|---|---|---|---|
| 09-22 | 6 mlb | 3 (3) | 3 (3) |
| 09-23 | 6 mlb | 3 (3) | 3 (3) |
| 09-24 | 4 mlb | 4 (3) | 4 (3) |
| 09-25 | 6 mlb | 3 (3) | 3 (3) |
| 09-26 | 6 mlb | 6 (**4**) | 5 (3) |
| 09-29 | 2 mlb + 1 nfl | 3 (2) | 3 (2) |
| 09-30 | 3 mlb | 3 (2) | 3 (2) |
| 10-04 | 13 nfl (rebuilt, see below) | 5 (2) | **7** (3) |

The 10-04 row:
- **Rebuilt input.** The 13 rows are rebuilt from the committed S624 slate fixture (S613 alias on;
  `S624_serving_probe.rows_for`). The 10-04 schedule files themselves are not committed to the repo.
- **Old rule.** It serves 5: 13:30 IND@WSH, 17:00 ARI@NYG, 17:00 DAL@HOU, 20:05 MIA@MIN, 20:25 DEN@SF.
  This equals the landed result.
- **New rule.** It serves 7: 13:30 IND@WSH; 17:00 ARI@NYG, DAL@HOU, GB@TB; 20:05 MIA@MIN; 20:25 DEN@SF,
  KC@LV. The six unserved games are JAC@CIN, LAR@PHI, NE@BUF, NYJ@CHI, TEN@BAL and LAC@SEA, each with
  cause cap_concurrency.
- **Modeled duration.** The 7 assumes the table default of 9000 s for nfl, which is modeled; at 12600 s the
  same rule serves 4.

On 09-26 the old rule had four live windows open at once against a focus capacity of three. The new rule
gives up one MLB game that day.

## Tests (one file per process; `python3 -m pytest <file> -q -p no:cacheprovider`)

New files:
- tests/platformkit/ingame/test_served_concurrency.py: 25 passed
- tests/platformkit/execution/test_schedule_d1_s742.py: 5 passed

Re-run, unchanged:
- test_schedule_d1 46/46
- test_schedule_revise 31/31
- test_schedule_revise_e2e 22/22
- test_capture_schedule_pointer 35/35
- _1c 11/11
- _1d 7/7
- startup_union_1e 3/3
- test_schedule_pointer_bootstrap_seed 8/8
- test_local_state_capture_schedule 367/367
- test_paper_desk_schedule_ack 34/34
- test_schedule_recovery 9/9
- test_loc_rail_scope 1/1

Red on BOTH this branch and origin/trunk, identical, so not caused by this row (CONTRACT tier checked):
- test_capture_scheduler 150/151 (`test_fix1b_*` needs a `master` ref the clone lacks)
- startup_union 22/23
- startup_union_1c 4/5
- startup_union_1d 1/6
- test_paper_desk_evidence 19/20

Failing on old code (scratch worktree with trunk's four files): the capture, pointer-union and all
end-to-end tests fail. The selection tests compare against the old rule inline: 10-04 5 -> 7, the floor
case starves mlb under the old rule, and the old rule overlaps > 3 on a two-per-hour day.

## Enabling it (NOT VERIFIED here)

Enabling the option on the recorder is a paper-desk config change for a LAPTOP session. Two steps are
needed:
- add `--capacity-rule live_concurrency` to the tick's schedule_d1 invocation;
- restart the capture so it loads the new capture_scheduler (06:00Z-16:00Z, between games).

Nothing here flips a flag ON. It is NOT VERIFIED on the recorder.

## NOT VERIFIED

- Recorder adoption, a live heartbeat or a capture tick under the option.
- Whether focus holds beyond the first hour. The capture focuses a scheduled game only inside
  [start-120, start+3600), so "served" means focus priority in that hour; every live window contains it
  (asserted).
- The true NFL game length. The 10-04 count of 7 rests on the 9000 s table default.
- G=3 is a ceiling. The AIMD limiter starts at 2.0 req/s (2 games) and floors at 0.5.
- Cross-midnight concurrency. schedule_d1 sees day D only; the capture catches the overlap only via
  pointer_capacity_refused.
- The 10-04 schedule files themselves (not committed); the input is the S624 slate rebuild.

## NEW GAP lines (for the orchestrator; no id allocated here)

- NEW GAP: schedule_recovery republishes under the default rule even for a day first published under
  live_concurrency. This is fail-safe, but the day silently changes rule (critic 16).
- NEW GAP: rule_from_argv does not parse `--capacity-rule=value`. The S500 allowlist refuses that form
  (fail-safe); this is untested.
- NEW GAP: 8 per-file reds already on trunk (list above) need their own fix row.
- NEW GAP: measure the real per-sport live duration (nfl has no table entry) before relying on the
  modeled 7.

## Laptop round (2026-10-05, after the cloud run)

Commit fdc86e802: the live-window durations now come from served_concurrency.LIVE_DURATION_SEC (the pre-S561
kalshi_series_scope values), not from kalshi_series_scope.TYPICAL_DURATION_SEC, because S561 changed that table
into start-to-expected-expiration offsets (nba 21600 s). The rule text above is superseded on that one point by
spec AMENDMENT 2. Test-only: committed schedule bytes are compared with CRLF folded to LF on a Windows checkout.
