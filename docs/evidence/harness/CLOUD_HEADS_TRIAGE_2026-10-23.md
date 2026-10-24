# Cloud heads triage 2026-10-23 (read-only; nothing landed, no tests run)

PAPER ONLY. Written 2026-10-23 ~20:00Z after `git fetch private --prune` (full fetch; checkout is not shallow). Analysed at master == private/trunk == d091bc086; master then advanced to 0e96ab158 (public-tree merge, 68 webapp/docs files): re-checked, it touches no file of any head and the 28 ancestors are unchanged.
Method: git only (rev-list, diff, merge-base, merge-tree preview, cat-file) plus reading memos with git show; no checkout, merge, pick or test run. Every claim is static.
Refs are private/cloud/<name>. Memos: git show private/cloud/<ref>:docs/evidence/harness/<ROW>_cloud_result_*.md (and _cloud_verify_*.md). Pinned = the lander list (src kernel api
team_system intel, baseline_four_arm*, walkforward, ingame_scoreboard*, scoreboard_history*, paper_night*, venue_time, PREREG_*).
Verdicts: LAND-FIRST = verified, additive, no pinned path, clean or one trivial conflict, useful now. LAND-LATER = verified but unwired, stacked, low urgency or docs. NEEDS-REVIEW = HOLD, REJECT, red on trunk, conflict, competing builds or pinned. SKIP = landed, superseded or no-op.

## Counts
- 234 cloud heads = 169 build/verify/critique/sweep heads + 65 noqual (no-op) heads. 28 are already ancestors of master. 206 are not.
- Unread (newest commit 10-21 or later): 22, ALL noqual-run46..run67 = docs-only "no qualifying row" memos. No build/verify/critique head is newer than 10-17 (sweep-2026-10-17).
- The 141 non-noqual unmerged heads collapse to 100 frontier heads (verify heads contain their build heads); every head is assigned below through its frontier head.
- Verdicts over the 141 non-noqual unmerged heads: LAND-FIRST 9 heads (5 rows), LAND-LATER 66, NEEDS-REVIEW 40, SKIP 26. The 65 noqual heads are SKIP.
- Pinned/gated path touches: 3 heads (S756 build, verify-S756 -> paper_night.py + paper_night_deferral.py; rehearse-S492B -> scorer identity files). S532 edits live_board.py, which the unsealed S782 draft prereg hashes.
- Already in master: 28 ancestors (section D1). Not ancestors but content already on master (cherry-picked): S564 S640 S642 S740 S741 S743 (section D2).

## A. Unread heads (10-21 or later): the 22 noqual-run heads
| ref | tip | date | row | files d/t/c | +/- | pinned | tier memo | what | verdict |
| noqual-run46..run67 (22 heads, 1 commit each) | see A2 | 10-21..10-23 | none | 1/0/0 each | +25..+42 each | no | no (nothing built) | each says: no qualifying PORTABLE row, trunk unchanged, "pause or slow this routine" | SKIP: identical template, no code |
A1. Two carry facts worth knowing: run58 re-checked 15 cloud/S* build heads by file presence and found only two S746/S747 memos missing from trunk (see S746-S747 row); run59 lists S831/S832 (b) as laptop-owned.
A1. CAUTION: run59 says ingame_scoreboard_amendment.py is "unpinned" and suggests a cloud spec for it. Under the S825 freeze it is on the lander identity list: do NOT write that spec.
A1. Recommendation repeated by the routine itself (64 empty runs): pause or slow desk-improve until a PORTABLE row names it. The 43 older noqual heads (run3..run45) say the same.
A2. tips: run46 0c71e0cf6, run47 c7d51a824, run48 082c919d8, run49 c34ca365b, run50 6b8ce577d, run51 fa734db47, run52 36cde6977, run53 2cc2d8a59, run54 a415393ae, run55 9e3083708, run56 7aa705bf8
A2. tips: run57 30fc9534c, run58 eb25ffeed, run59 d883bad04, run60 0795022e4, run61 f8c103681, run62 786527dae, run63 0f9aaf7b7, run64 cc0d5e59e, run65 3211593df, run66 18ec44e2b, run67 b2c099979

## B. Older heads with OPEN or unlanded rows (one line per tip; stacked heads shown with their container)
| ref (+ other refs it carries) | tip | date | row | d/t/c | +/- | pinned | tier memo | what | verdict: reason |
| S532-2026-10-05 (+v-S532-2026-10-11) | 49c76369b | 10-05 | S532 | 2/3/1 | +218/-12 | n* | y | NBA live_board: 5-min OT elapsed minutes + S.s clock parse (OT game read 55.0 min, now 48.0) | LAND-FIRST: NBA live since 10-20; must land BEFORE the S782 seal hashes live_board.py; 2 tiers + round 2 ACCEPT; its 3 files untouched on master since base |
| S730-2026-10-04 (+v-S730-2026-10-09) | 0c960847f | 10-04 | S730 | 2/1/2 | +306/-6 | n | y | arm-E receipt check made off-day aware; schedule counts in the flag; misfiled for_night flagged | LAND-FIRST: 10-23 daily links two open registry_e P2 issues (10-21, 10-22) to S730; round 2 ACCEPT (25/25 mutants); ONE import-line conflict; real receipts NOT VERIFIED |
| verify-S791-2026-10-12 (+S791-2026-10-08) | d299c3bed | 10-12 | S791 | 3/1/0 | +272/-0 | n | y | test-only: tick low-RAM deferral test made hermetic (stop paths mapped under tmp_path) | LAND-FIRST: removes the likely cause of the red (live STOP_* paths leak into the fixture; simulated on Linux, not reproduced on Windows); no production file; round 2 ACCEPT; test file untouched on master |
| critique-S782c-2026-10-13 | ea1b8f127 | 10-13 | S782c | 1/0/0 | +115/-0 | n | y | pre-build critic of the S782c publication + timestamp witness spec: REVISE, 3 blocking | LAND-FIRST: S782 seal is not before 10-24 and S782b/c join at seal; fold the blockers before any build; docs only |
| verify-S799-2026-10-12 (+S799-2026-10-10) | 79f8439c7 | 10-12 | S799 | 3/1/0 | +266/-0 | n | y | test-only guard: recovery oracle vs mixed int/str game_key; premise FALSIFIED (0 of 2,109 divergent) | LAND-FIRST: closes S799 as a measured reject at zero risk; oracle pin commit 6edce1f9 is on master; no production file |
| verify-S769-2026-10-11 (+S769-2026-10-06) | f162580f4 | 10-11 | S769 | 3/1/1 | +555/-0 | n | y | tick schedule recovery: transient refusals back off instead of burning the 3-try cap | LAND-LATER: live tick path; found by verifier tiers, no measured incident; land after commit B settles; hand-merge with S771 |
| verify-S772-2026-10-11 (+S772-2026-10-06) | afc0d1a2b | 10-11 | S772 | 3/1/2 | +352/-12 | n | y | recovery child passes the tick --config to schedule_recovery | LAND-LATER: no effect on the default config; text-merges clean with S769/S770/S771; land with S769 |
| verify-S771-2026-10-11 (+S771-2026-10-07) | 094979368 | 10-11 | S771 | 3/1/2 | +548/-6 | n | y | missed-date queue pruning + tomorrow completion | LAND-LATER: text conflicts with S769/S770 in paper_desk_recovery.py (1 and 3 hunks); hand-merge after S769 |
| verify-S773-2026-10-12 (+S773-2026-10-08) | eb95f8148 | 10-12 | S773 | 3/1/1 | +568/-0 | n | y | capped issue-scan wrapper (RSS cap for the morning scan) | LAND-LATER: unwired module; 13 of 20 new mutants survive (corrections listed, not applied) |
| verify-S783-2026-10-09 (+S783-2026-10-08) | e12c2d77a | 10-09 | S783 | 3/2/2 | +480/-12 | n | y | books restart preflight: artifact refusals fixed | LAND-LATER: four kill tests applied; manual restarts only, no live trigger now |
| verify-S757-2026-10-12 (+S757-2026-10-08) | e5b038cdb | 10-12 | S757 | 4/1/1 | +664/-0 | n | y | superseded-attempt events module + PROPOSED receipt field | LAND-LATER: module inert; wiring is a paper_night.py edit (human-gated); 5 test corrections listed, not applied |
| verify-S758-2026-10-14 (+S758-2026-10-13) | ce82ee486 | 10-14 | S758 | 3/1/1 | +373/-5 | n | y | night attempt counter travels with evidence_push | LAND-LATER: edits evidence_push.py (push path); matters when the recorder moves; adversarial ACCEPT 11 of 13 mutants |
| verify-S759-2026-10-14 (+S759-2026-10-14) | d65223fdb | 10-14 | S759 | 3/5/0 | +380/-3 | n | y | re-pin M2/S439 must_not_move (landing-only) + tests | LAND-LATER: 3 doc/test corrections owed by the lander; meanwhile never set S544_LANDING=1 (pins are stale) |
| verify-S575-2026-10-06 (+S575-2026-10-03) | f2b49a170 | 10-06 | S575 | 3/1/2 | +459/-10 | n | y | MLB umpire gate reads archived gumbo_live | LAND-LATER: register: research path, low priority; 2 test-only corrections proposed |
| verify-S588-2026-10-10 (+S588-2026-10-09) | d4af089c2 | 10-10 | S588 | 3/1/4 | +722/-2 | n | y | scripted C5 fault matrix (4 ops modules) | LAND-LATER: 5 mutant survivors listed; waits for RAM windows; dev tooling, not wired into the tick |
| verify-S646-2026-10-07 (+S646-2026-09-30) | cacabd636 | 10-07 | S646 | 3/11/7 | +3978/-0 | n | y | R1 markout predictability kit (7 modules) | LAND-LATER: register: PARKED, no seal, no scored look; 165 passed on the cloud |
| S685-2026-09-30 (+v-S685-2026-10-06) | 95b572738 | 09-30 | S685 | 3/1/7 | +10720/-0 | n | y | Dixon-Coles soccer oracle (dev-only, library pin) | LAND-LATER: 17 of 25 new mutants survive; add/add on oracles/__init__.py (S686 landed); soccer low priority |
| verify-S691-2026-10-01 (+S691-2026-09-30) | e05f77ef6 | 10-01 | S691 | 4/6/8 | +2543/-0 | n | y | AUTOMATED-DESK base: event core, order journal, blotter | LAND-LATER: shared base of S692/S696/S699/S700/S702/S707; one-line fix proposed (F-A1 non-str tag); unwired |
| verify-S692-2026-10-02 (+S692-2026-09-30) | c5754d330 | 10-02 | S692 | 6/8/11 | +3529/-0 | n | y | desk replay client + S551 parity | LAND-LATER: on S691; third tier 0 blocking; merges clean with S696/S702/S700 |
| verify-S696-2026-10-02 (+S696-2026-10-01) | 899900e2e | 10-02 | S696 | 6/10/10 | +3788/-0 | n | y | startup reconciliation of paper state | LAND-LATER: on S691; two tiers ACCEPT WITH CORRECTIONS (test gaps); merges clean |
| verify-S702-2026-10-03 (+S702-2026-10-01) | 38408060f | 10-03 | S702 | 6/10/10 | +3869/-0 | n | y | ordered risk gate (three states) | LAND-LATER: on S691; round-2 hold logic checked; S707 sits on it and is on HOLD |
| verify-S668-2026-10-05 (+S668-2026-09-30) | bd68b2ed8 | 10-05 | S668 | 3/4/5 | +1758/-0 | n | y | risk breakers + kill switch | LAND-LATER: adversarial REJECT (load_state RecursionError) fixed, re-verify ACCEPT |
| verify-S671-2026-10-05 (+S671-2026-09-30) | b4332a249 | 10-05 | S671 | 4/3/4 | +1489/-0 | n | y | venue order rules + incident fixtures for paper fills | LAND-LATER: 33 of 46 mutants killed, 8 real test gaps; overlap with landed S693 venue_rules noted |
| verify-S703-2026-10-08 (+S703-2026-10-01) | 059460eeb | 10-08 | S703 | 5/1/2 | +9693/-0 | n | y | target-vs-live quote reconcile arm | LAND-LATER: result is an honest FAIL on the fill bar; 9.7k lines of fixtures |
| sweep-2026-10-17 (+sweep-2026-10-15) | b59e703c2 | 10-17 | - | 2/0/0 | +214/-420 | n | y | per-file test sweep of the last 417 files (263 green, 148 Linux-only, 6 real) + no-row memo | LAND-LATER: docs; rewrites TEST_SWEEP_TRIAGE (unchanged on master since 09-29); supersedes the 09-30/10-01/10-02 sweeps |
| S746-S747-2026-10-05 | 488a339b0 | 10-05 | S746 S747 | 8/0/0 | +831/-0 | n | y | cloud memos for S746/S747 | LAND-LATER: code landed (consolidated seal, commit B 5904b1033); only 2 cloud memos absent from master (run58 finding); copy those 2 files, do not cherry-pick |
| verify-S798-2026-10-14 (+S798-2026-10-14) | 4f4dc5613 | 10-14 | S798 | 3/1/1 | +459/-3 | n | y | state shard recovery handle held open during the yield (Windows) | LAND-LATER: capture-path change with a Windows-only cause; run test_s798_recovery_handles.py on Windows first; adoption needs a state2 restart |
| verify-S756-2026-10-11 (+S756-2026-10-08) | db0524797 | 10-11 | S756 | 3/1/3 | +404/-7 | Y | y | admission declaration identity in night audit/deferral | NEEDS-REVIEW: edits paper_night.py + paper_night_deferral.py (pinned): not before the freeze lifts; tiers ACCEPT WITH CORRECTIONS |
| S523-2026-10-04 (+v-S523-2026-10-07) | 48269b67c | 10-04 | S523 | 2/1/1 | +325/-1 | n | y | tick journal: peak RSS per child | NEEDS-REVIEW: conflicts with trunk in paper_desk_process.py; resolution diff is in the verify memo |
| S731-2026-10-04 (+v-S731-2026-10-09) | b9bb5a5c9 | 10-04 | S731 | 2/1/2 | +475/-1 | n | y | issue re-read of open unreadable subjects | NEEDS-REVIEW: verify owes a one-line fix (S718 read-cap drift keeps cap-opened issues open) |
| S760-2026-10-06 (+v-S760-2026-10-10) | bc8327103 | 10-06 | S760 | 2/1/0 | +330/-0 | n | y | C22 pin test for the paper_night _run wrapper | NEEDS-REVIEW: built head is RED on trunk after S711 (4 failed); the verify head carries the PROPOSED rebase |
| verify-S770-2026-10-11 (+S770-2026-10-06) | d425f1185 | 10-11 | S770 | 5/2/3 | +1066/-2 | n | y | off-day recovery attention noise (45 rows per off day) | NEEDS-REVIEW: verify reproduced 2 false-proof paths via the D-1 journal; fix round recommended before landing |
| verify-S822-2026-10-14 (+v-S822-2026-10-13, S822-2026-10-12) | f6f2581de | 10-14 | S822 | 3/2/2 | +733/-5 | n | y | polymarket props re-poll cadence | NEEDS-REVIEW: adversarial REJECT 10-14 (held prop keeps a mixed game eligible, core fetched 9x vs 3x): do not land as built |
| S674-2026-09-30 (+v-S674-2026-10-05) | e7e415205 | 09-30 | S674 | 8/1/3 | +1256/-0 | n | y | model cards + inventory index | NEEDS-REVIEW: verify found coverage fail-open and a tautological test; symlink fix still open |
| verify-S699-2026-10-04 (+S699-2026-10-01) | 53bb64a0e | 10-04 | S699 | 6/11/12 | +3998/-0 | n | y | per-family paper accounts + attribution | NEEDS-REVIEW: HOLD: @ key collision, PENDING_SUBMIT test gap, sync cost about O(n^3) |
| verify-S700-2026-10-11 (+S700-2026-10-01) | 20cb7803c | 10-11 | S700 | 9/15/15 | +5417/-0 | n | y | version registry + challenger slots | NEEDS-REVIEW: sits on S699 (HOLD); two competing builds (10-01 and 10-07) |
| verify-S707-2026-10-03 (+S707-2026-10-01) | 51de7857e | 10-03 | S707 | 9/12/11 | +4951/-0 | n | y | tick step error-rate breaker | NEEDS-REVIEW: HOLD: quarantine-preservation item not met |
| verify-S698-2026-10-07 (+S698-2026-09-30) | 753df5a85 | 10-07 | S698 | 4/2/1 | +884/-0 | n | y | stage policy file + gate | NEEDS-REVIEW: HOLD pending AMENDMENT 3: adversarial REJECT on P29 under landed S670 (owner decision); two builds |
| S701-2026-10-01 (+v-S701-2026-10-05) | fff8de684 | 10-01 | S701 | 3/4/4 | +1797/-0 | n | y | calibration decay monitor | NEEDS-REVIEW: HOLD for one test-only pass (ECE direction, K=5 boundary, first-ts order) |
| S683-2026-09-30 (+v-S683-2026-10-06) | 83d727dd3 | 09-30 | S683 | 3/1/2 | +1066/-0 | n | y | cross-interpreter determinism check (3.10 vs 3.11) | NEEDS-REVIEW: verify: NOT LANDABLE AS-IS (3 new PREREGs unruled; 18 of 28 mutants survive) |
| verify-S695-2026-10-02 (+v-S664-2026-10-04, S664-2026-09-30, S695-2026-09-30) | 2a168276f | 10-02 | S664 S695 | 7/3/4 | +1880/-0 | n | y | clock offset journal + clock guard | NEEDS-REVIEW: S695 third tier 0 blocking, but S664 verify owes 4 corrections before landing |
| verify-S689-2026-10-09 (+S689-2026-10-06, S689-2026-09-30) | ef9ff0db2 | 10-09 | S689 | 4/2/6 | +1339/-0 | n | y | consensus baseline + close-relative paired scoreboard | NEEDS-REVIEW: two competing builds (consensus_baseline/ vs eval_gate/consensus_scoreboard.py); pick one; real census INSUFFICIENT_INPUTS |
| verify-S690-2026-10-08 (+v-S659-2026-10-15, S659-2026-09-30, S690-2026-09-30) | ddc7e54de | 10-08 | S659 S690 | 6/9/7 | +3132/-0 | n | y | recorder adopt step + evidence allowlist push (spare-laptop move) | NEEDS-REVIEW: 2 stale tests red on trunk (S690) and a time-coupled relaunch-name pin red (S659); fix before landing |
Pinned column: n = no pinned path edited; n* = edits live_board.py, which the unsealed S782 draft prereg hashes (land before that seal); Y = edits paper_night*.

B2. Grouped heads (tip shas in section E):
- G1 critiques [8 heads] LAND-LATER: docs-only pre-build critics, one memo each (109-196 lines), zero conflict; land as one docs batch when the spec is built
- G2 verify memos of rows already LANDED [13 heads] LAND-LATER: docs-only second-tier memos (S667 and S678 also add 1 mutant-killing test); some list follow-up gaps (S660 Windows guards, S684 holes)
- G3 gap review + landings review [2 heads] LAND-LATER: docs; GAP_REVIEW_cloud_2026-09-30.md is ALREADY on this laptop untracked and byte-identical (a cherry-pick would refuse; just git add it)
- G4 landed or superseded [17 heads] SKIP: register LANDED (local or composed landing): S564 S640 S642 S740 S741 S743 identical or present on master; S504 S742 S802 S816 S824 S653/S656 evolved; verify-S794/S814/S815/S817 verified builds that were replaced by local landings
- G5 rehearsal [1 head] SKIP: S492B rebase rehearsal touching scorer identity files (ingame_scoreboard*, baseline_four_arm_features*, scoreboard_history_store): superseded by landed commit B 0d2d5a196; NEVER land
- G6 env report + old sweep [2 heads] SKIP: smoke = cloud environment report; sweep-2026-10-02 is superseded by sweep-2026-10-17

## C. LAND-FIRST, ranked (none edits a pinned file; tests per file, never the full suite; (n) = cloud pass count on Linux py3.11, the laptop run is what counts)
Ranges: master..ref = the commits unique to the branch (checked for these five: linear, 0 merges). Among unlanded heads only S532 edits a file hashed by the unsealed S782 draft prereg.
Quiet window tonight: CLE-PHI focus hour 22:55Z-00:05Z (NOW.md): no pytest/pick in it. Land each before or after S825 commit B, never inside its commit; S782 seal is not before 10-24.
1. S532 (deadline: before the S782 seal) -- git cherry-pick master..private/cloud/S532-2026-10-05   (4 commits, clean) ; optional memo: git cherry-pick master..private/cloud/verify-S532-2026-10-11
   The S782 draft (PREREG_FORECAST_LOG_PROPOSED_2026-10-06.json) pins live_board.py sha256 350f4deb... = master today; S532 changes it, so land first or regenerate that hash at the seal.
   tests: tests/platformkit/ingame/test_s532_nba_ot_elapsed.py (48), tests/platformkit/ingame/test_nba_season_type.py (45), scripts/platformkit/frontend/test_live_board.py (22), tests/platformkit/test_loc_rail_scope.py
2. S730 -- git cherry-pick master..private/cloud/S730-2026-10-04   (3 commits; private/cloud/verify-S730-2026-10-09 is the same tip). Expect a conflict in paper_desk_issue_checks.py (net merge preview: one import-line hunk; it may repeat on the next commit):
   keep master's `refusal_keys` import line AND make the offday import `off_day, produced_fact`.
   tests: tests/platformkit/ops/test_paper_desk_issue_registry_s730.py (32), test_paper_desk_issue_checks.py (67), test_paper_desk_issue_checks_fix.py (21), test_paper_desk_issue_offday.py (63), test_paper_desk_issues.py (61), tests/platformkit/test_loc_rail_scope.py
   Caveat: the stale landing-only pin on paper_desk_issue_checks.py (s544 fixture) moves again; do not set S544_LANDING=1. Whether the open registry_e P2s clear depends on off-day proofs (NOT VERIFIED).
3. S791 -- git cherry-pick master..private/cloud/verify-S791-2026-10-12   (4 commits, clean). tests: tests/platformkit/ops/test_paper_desk_tick.py (expect 24), test_s709_desk_root.py (36), test_paper_desk_s754_recovery.py (9). Windows run is the owner check.
4. critique-S782c -- git cherry-pick master..private/cloud/critique-S782c-2026-10-13   (1 commit, docs). Read before any S782b/S782c build or the S782 seal.
5. S799 -- git cherry-pick master..private/cloud/verify-S799-2026-10-12   (4 commits, clean). tests: tests/platformkit/ingame/test_s799_mixed_game_key.py (5), test_local_state_recovery.py (18), test_s789_recovery_io.py (5).
After landing: write the register cell LANDED <sha> for S532 S730 S791 S799 (say the cloud head is superseded) and the ledger line (DESK_STATE: the cloud-lander desktop task has been disabled since 10-01, so nothing else will land these).
Next wave once commit B has settled: S769 then S772 (S771 by hand), then S773/S783/S758. Do NOT land S756 (pinned) or S822 (REJECT). The S691 stack is a separate compose job.

## D. Prune candidates (already contained in master)
D1. ancestors of master (git merge-base --is-ancestor = true), 28: S530-2026-10-02 91c6333, S594-2026-09-30 b02aefd, S631-2026-09-30 7f189d1, S637-2026-10-02 eb25d07, S641-fix-2026-09-30 3d0311a, S658-2026-09-30 bfa8619, S660-2026-09-30 5284dff, S663-2026-09-30 8d82081, S666-2026-09-30 38812e7, S667-2026-09-30 767a5f9, S669-2026-09-30 c25dac3, S670-2026-09-30 0d7bb1b, S672-2026-09-30 f0fbd92, S675-2026-09-30 6b808fe, S676-2026-09-30 d3e2656, S677-2026-09-30 9bea2f3, S678-2026-09-30 3594e3e, S679-2026-09-30 89546f2, S682-2026-09-30 86273f6, S684-2026-09-30 cc5cc73, S686-2026-09-30 f9461c7, S687-2026-09-30 d6922c9, S688-2026-09-30 f8333af, S693-2026-09-30 f016f04, S694-2026-09-30 59f44f9, S697-2026-09-30 d679d4d, S705-2026-09-30 e9377f8, S709-2026-09-30 821ead8
D2. not ancestors but every file is identical on master or its added lines are already there (cherry-picked): S564-2026-10-05, S640-2026-09-30, S642-2026-09-30, S740-2026-10-05, S741-2026-10-05, S743-2026-10-05.
D3. duplicate ref: private/cloud/S730-2026-10-04 and private/cloud/verify-S730-2026-10-09 are the same commit 0c960847f.
D4. all 65 noqual heads are docs-only no-op memos, mostly template copies (runs 43, 44, 58, 59 carry a few specifics). Deleting a remote ref is the owner call; its commits are lost unless landed or kept.

## E. Tips for grouped heads
- G1: critique-S407 a8b14c8a, critique-S408 da67b4cb, critique-S593 74756acf, critique-S596 f327baf2, critique-S762 4ebd5e24, critique-S763 62d3d02c, critique-S764 fb9e2718, critique-S776 d490e0fd
- G2: v-S640 06b1d33a, v-S660 81247be6, v-S663 8cbc1772, v-S666 5a4150ef, v-S667 0504ee32, v-S676 eb88df7d, v-S678 f85f55a0, v-S679 fcff7e8d, v-S684 df0a6231, v-S693 a0aebb3e, v-S694 61ad30ab, v-S697 ebfb0664, v-S705 b18c79e3
- G3: gapreview 712ae71e, review-landings 1588d6b5
- G4: S504-S641 b8a7b9a7, S564 a81ef75e, S640 7e1e9002, S642 7e40af7c, S653-S656-fix baedd735, S740 26ab753b, S741 41f4c5d7, S742 82bb5ff8, S743 aa2243d7, S802 d5c32c3d, S816 034e3c7b, S824 7197c0a8, v-S794 a261e7e3, v-S814 3e1a7691, v-S814 ad8d9212, v-S815 184ddb28, v-S817 33237e9c
- G5: rehearse-S492B 4aa7697d
- G6: smoke e103fd6a, sweep eedd411a
