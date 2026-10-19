# PLAN D -- per-sport readiness calendar and integration (Fable planner D, 2026-09-29 23:5xZ)
Window: 23:45Z 09-29 to 04:45Z 09-30. All times UTC. "Night D" runs at 06:05Z on D+1; the S500 tick writes D1(D) at 07:00 local (12:00Z) on D-1 (paper_desk_actions.py:90, day_after(local date)).
Verified this session: identity files on master equal PREREG_2026-09-30 and PREREG_2026-10-01 under the verifier's CRLF normalisation (ingame_scoreboard_amendment.py:60); state2 MLB heartbeat fresh 23:42Z (3 games tracked, 1 live); captures present at the 23:26Z tick; issue queue = 6 P1 + 1 P2, none new tonight.

## Per-night chain (every sport, every night)
captures present and fresh; D1 with --now + pointer (tick); books focus adoption; state live rows and finals; night at 06:05Z (RAM admission, S501 defers on low RAM); scoreboard under the night-dated seal (S484); history (S474); arm E; census D+2; issue scan.

## Dated calendar
- 09-30 04:37Z: state2 restart adopts S490 (six-league soccer) + S494 (NBA season_type). Session cron 073cf50f; dies if the app closes.
- 09-30 06:05Z: night 09-29. EXPECTED: scoreboard amendment_mismatch by design; E config_not_effective exit 0. Record this as expected; nobody should chase it.
- 09-30 08:37Z: S561 cherry-pick 5d89469c0 + books relaunch (cron; window 06-16Z). MLB live flag from first pitch, NBA live while played.
- 09-30 12:00Z: tick writes D1(10-01). The WC Game 3s are "if necessary", and this D1 is written before the Game 2s are played. NOT VERIFIED whether Kalshi/ESPN list them yet; this is a no-row risk.
- 09-30 00:00Z/18:00Z/22:00Z: MLB BOS@NYY, PHI@ATL G2, CWS@HOU G2 (D1 09-30 was hand-run by the owner; the tick flags it schedule_invalid, S520a, which does not affect scoring).
- 10-01 06:05Z: NIGHT 09-30 = first fitted MLB night (PREREG_2026-09-30), E effective, S551 first scored day. Its receipt scoreboard/2026-09-30.json gates S492 commit B.
- 10-01 12:00Z: D1(10-02) (TNF). 14:07Z improve run: S492 commit B (target). HARD STOP: before the night 10-03 run at 06:05Z 10-04, so NFL enters history for 10-04.
- 10-02 00:15Z: TNF. S561's nfl 10800 s is NOT VERIFIED against a feed; measure it here. Night 10-02 is the first NFL night under PREREG_2026-10-01 (A/B_lag only; no NFL fit yet).
- ~10-03 onward: MLB DS (dates NOT VERIFIED), LCS ~10-12, WS ~10-23. The MLB postseason totals about 40 games at most, so the 30-game floor lands late.
- 10-03 12:00Z: D1(10-04). NFL Sunday 17:00Z/20:05Z/20:25Z plus DS games compete under one global cap (at most 2 starts per rolling hour, capture_scheduler.py:113). My estimate is about 2 of the ~9 17:00Z kickoffs served (NOT VERIFIED).
- 10-05 06:05Z: first fitted NFL night (10-04), only if the 09-29 MNF final is admitted as history. SNF 10-05 00:20Z; MNF 10-06 00:15Z.
- by 10-07: S531 (cross-sport cap + three-outcome focus) and S535 (per-route deadline) landed and adopted, each in a 07-16Z restart window.
- 10-08 before 12:00Z: "soccer" in paper_desk_config sports, or no soccer D1(10-09). Soccer seal check: after commit B, 10-09 nights score under PREREG_2026-10-01, but the S490 dependency addendum binds PREREG_2026-09-30's sha. VERIFY whether it still covers the 10-01 seal; if not, re-bind in S534 scope with commit day < 10-09.
- 10-09..10-12: first soccer fixtures in the six leagues, and the first live proof of the league/home fields (no rehearsal is possible before then). S530 report afterwards.
- early Oct: NBA preseason on ESPN, not listed on Kalshi. This is a free rehearsal for season_type=preseason rows, the S564 play-by-play RAM/request measurement and S563 late-West finals.
- 10-19 before 12:00Z: S562 (nba in config + actions.py:83 + issue_capture.py:96). S564 adopted.
- 10-20/10-21: NBA nights (BOS@DET, PHI@NYK; OKC@SAS). A/B_lag from night 1, B/C ~10-24, D never. S532 before the first NBA OT. S482 after the first live-night census (10-22+).
- Tennis S493: BLOCKED on S469, S492 B, S502 and a D1 tennis lane (0 of 506 linked on 09-26). Earliest legal seal 10-02, realistic 10-05+.
- WNBA: deferred to 2027 (S491). Captures keep running for S563; no scoring work.

## Critical path
state2 adopt (09-30 04:37Z), then D1(10-01) and the MLB G2 captures, then NIGHT 09-30 SUCCESS (10-01 06:05Z), then S492 commit B (target 10-01 14:07Z, hard stop 10-04 06:05Z), then D1(10-04) under the cross-sport cap, then the first fitted NFL night (10-05), then soccer config + S531/S535 adopted (by 10-08 12:00Z), then S562 + S564 (by 10-19 12:00Z).
Slack: commit B has about 2.7 days after its gate. The binding risk is the 09-30 night itself (RAM, or an identity drift).

## Work packages (next 5 h), ranked. Executor L-R = NEW Opus readiness lead (4.25 h); DSP = dispatcher heartbeat (0.75 h).
R1 P0 Commit-B pre-flight [S492; prep only, the improve run lands]. L-R, 1.5 h, starts first.
  Build a rebased candidate in a NEW worktree; never touch h141 (its candidate is uncommitted there).
  Merge the test_s485_baseline_contract.py re-pin with BOTH S501 0914898a0 AND S496 27ae6b756 edits. S496 also touched that file after the checklist was written; this is new.
  Check the 7 identity hashes (CRLF-normalised) against d507296d7, and seal selection on master (09-30 -> PREREG_2026-09-30; 10-01/10-02 -> 10-01).
  Done: the owned files are green per file; `git apply --check` is clean on HEAD; a "COMMIT-B READY <branch>" line is posted under FOR paper-desk-improve. RAM: per-file pytest < 400 MB.
R2 P1 Cross-sport served capacity + if-necessary games [S531 input; new]. L-R, 1.25 h, read-only.
  Apply the committed cap rule to dated ESPN schedules + Kalshi listings for 10-01..10-06 (WC G3, DS, TNF, NFL Sunday, SNF, MNF): served vs excluded per sport per day.
  Answer whether G3/DS "if necessary" tickers exist at D1 time.
  Hand the table to the soccer-readiness lead, so S531's acceptance includes "no MLB/NFL displacement". If D1 timing drops games, open a row from the soccer-readiness lead's block.
  Done: the table with every estimate labelled, and a register note. RAM < 150 MB, a few HTTP GETs, no archive reads.
R3 P1 Early D1 rehearsal for soccer + nba [S562 + soccer config; the improve run's files]. L-R, 0.75 h.
  Run schedule_d1 --sports mlb,nfl,soccer,nba for 10-01..10-03 into a scratch root with no pointer write.
  Prove per-sport isolation (a soccer/nba source failure must not fail the mlb/nfl D1) and that there are 0 soccer/nba rows before fixtures.
  Post the exact config / allowed-tuple / monitored-sports diff under FOR paper-desk-improve, advising landing 10-02..10-05 (after D1(10-02), not before).
  Done: scratch receipts, an isolation verdict, the diff posted. RAM: schedule cap 512 MB.
R4 P1 Capture-adoption calendar [S502, S535, S563, S564, S531, S561]. DSP, 0.5 h.
  Batch every pending capture-code landing into restart windows: W1 10-01 08-16Z, W2 10-03 07-15Z, W3 10-07/08.
  Gate each restart on free RAM >= 2.1 GB. The 04:37Z cron gates at 1.5 GB (per NOW.md) but the supervisors refuse children below 2,000 MB, so raise it now. Also require no served game within 60 min.
  Verify after every restart: a fresh child heartbeat within 5 min, and max tick gap < 30 s over 30 min.
  Done: the calendar is in NOW.md and the 04:37Z gate is raised.
R5 P1 Seal-drift + night-outcome watch [no code]. DSP, 0.25 h.
  Each heartbeat until commit B: run verify_amendment for the 09-30 and 10-01 seals on master. Any mismatch = stop the line and revert before 06:05Z.
  Log the night 09-29 amendment_mismatch as EXPECTED. Done: the heartbeat prompt carries both.
R6 P2 Tennis go/no-go [S493, S469, D1 tennis lane]. L-R, 0.5 h, read-only.
  On one real day, count Kalshi tennis tickers vs ESPN keys the writer could link, plus the October tournament days left.
  Fable rule: GO only if >= 20 linkable matches/day AND S469 has a builder by 10-03; else DEFER S493 to 2027 like S491. Done: a decision line on S493.
R7 P2 NBA preseason rehearsal hand-off [S494, S563, S564, S532, S482]. L-R, 0.25 h.
  Put the preseason checklist (first ESPN game date, season_type on live rows, history exclusion, play-by-play cost) into the capture-latency lead's next package, and name an S482 owner for 10-21.

## Not owned by any running lead
- S469: blocks tennis. It must land after commit B with its own new seal, because it changes identity files.
- S482: the sport-coverage lead is DONE.
- The S493 build and the D1 tennis lane: no row exists for the lane.
- S518 (live shadow for NFL/soccer/NBA): orchestrator 4 is DONE.
- The WC/DS if-necessary D1 timing: no row.
- The tick side of S582 (a zero-game day reruns schedule_d1 24 times): only suggested to the improve run.
- The historical P1s (schedule_missing 09-27/09-28, night_noncanonical_as_of 09-24/09-25): they keep every tick "refused", which masks new faults.
- The improve run's queue (S492B S520 S521 S495 S562 soccer-config S585 S586 S587 S582-tick) is about 10 rows at <= 2 landings/day. R1 and R3 cut its load.

## Needs the owner
1. Commit and run relaunch_live_shadow_2026-09-29.ps1 before 18:00Z 09-30 (PHI@ATL G2), with free RAM >= 2 GB.
2. Keep the app open and the laptop awake through 08:37Z 09-30 (session crons), or run the S490 and S561 relaunch scripts by hand in 04-16Z.
3. Leave RAM free for the night 09-30 run at 06:05Z 10-01 (01:05 local). The commit-B chain hangs on it. Only the owner may close Chrome.
4. Accept the 09-24..09-28 P1s as permanent history, or delegate that to Fable.
5. Re-login codex before 10-05 (the soccer/NBA verify tiers need it).

## Top 3 failure modes (tonight and the next games) and guards
1. NIGHT 09-30 fails, defers past the window, or an identity file drifts before it runs.
   Effect: no first fitted MLB receipt, S492 B stuck, NFL misses 10-04 history.
   Guard: R5 drift check every 30 min; S501 deferral + tick retry; owner item 3; R1 makes B a 10-minute cherry-pick. At the hard stop, Fable holds B for the receipt: TNF's B/C loss is small because NFL fitting starts 10-04.
2. A capture gap on a served game.
   Causes: a restart at 1.5-2.0 GB leaves the child waiting under the 2,000 MB supervisor floor; from 04:37Z six soccer routes share every state tick, and one 403 loop holds a tick about 1,590 s (S535); the tick showed books heartbeat child_timeout at 23:26Z.
   Guard: R4's 2.1 GB gate + 5-min heartbeat + 30-min tick-gap check; S535 pulled ahead of TNF 10-02 (soccer-readiness lead); the S500 tick relaunches absent supervisors; gametime checks.
3. Served-schedule starvation.
   Causes: D1(10-01) is written before the G2s; one global cap covers the 10-04 NFL cluster + DS; soccer 10-09 under the same cap can displace MLB/NFL.
   Guard: R2 measures before D1(10-04); S531's acceptance forbids displacement; R3 isolates per-sport D1 failure; the fallback is a pre-first-pitch D1 revision WITH --now (so S520a does not flag it).
