# Owner brief 2026-09-30 (written ~05:3xZ by O12 while the owner was asleep)

This is paper-only calibration work. Nothing here places an order or measures money.
Facts marked (fleet 05:00Z) were verified by the cleanup fleet at about 05:00Z on 09-30.
Everything else was read from .planning/NOW.md (the STOPPING PLACE 2026-09-30 block),
docs/evidence/harness/FIVE_HOUR_PLAN_2026-09-30.md ("Needs the owner") and the relaunch script headers.

## What is running (and how to check in 60 s)

- Capture supervisors state2, books and polymarket are up since about 14:11Z 09-29 with 0 restarts (fleet 05:00Z).
  Check: the files data/cache/capture_supervisor/supervisor_*.heartbeat.json should have an mtime within the last 60 s.
- Windows task \CourtVisionPaperDesk is Ready, runs every 30 min and at logon, WakeToRun is OFF (fleet 05:00Z).
  Check from PowerShell: `schtasks /query /tn CourtVisionPaperDesk /v`, then read data/cache/paper_desk/status.json (tick_ok).
- Desktop Claude scheduled tasks (these run only while the Claude app is open), no failed or stuck runs (fleet 05:00Z):
  paper-night-2026-09-29 one-shot 06:10Z 09-30; paper-desk-morning 12:50Z; paper-desk-improve 14:06Z;
  paper-desk-gametime 17:21Z then every 2 h; paper-night-2026-09-30 one-shot 06:10Z 10-01.
  Check: list_scheduled_tasks from any Claude session.
- Session one-shots that DIE if the Claude app closes or this session ends: 07:57Z state2 restart and 08:37Z S561 books landing (fallbacks below).

## Today's timeline (UTC, with local ET = UTC minus 4 h)

| UTC | ET | What |
|---|---|---|
| 05:59Z 09-30 | 01:59 | Weekly usage resets (it was 83 pct). |
| ~06:05-06:10Z | 02:05-02:10 | Paper night 09-29 runs. Expected findings listed under Expected-not-faults. |
| 07:57Z | 03:57 | Session one-shot: state2 restart via relaunch_state2_s535_2026-09-29.ps1 (adopts S490, S494, S535, S606). The earlier 04:37Z attempt never fired. |
| 08:37Z | 04:37 | Session one-shot: S561 landing (cherry-pick c4bd924c4) plus the books relaunch. |
| 12:50Z | 08:50 | paper-desk-morning. |
| 14:06Z | 10:06 | paper-desk-improve (the S502 fix is queued here). |
| 16:00Z | 12:00 | The by-hand restart window closes. |
| 17:21Z | 13:21 | paper-desk-gametime, then every 2 h. |
| before 18:00Z | before 14:00 | Deadline to start the live shadow recorder. |
| 18:00Z / 21:00Z | 14:00 / 17:00 | Served games: PHI@ATL, CWS@HOU. |
| ~06:05Z 10-01 | 02:05 10-01 | Paper night 09-30, the first fitted night; it needs about 2.7 GB free RAM. |

## Do these yourself (deadline, exact command)

All PowerShell commands run from C:\Users\neelj\nba-ai-system.

1. Start the live shadow recorder before 18:00Z 09-30, with free RAM >= 2 GB. It is paper only (no venue client, no order path). Dry run first:
   `powershell -NoProfile -File docs\operations\relaunch_live_shadow_2026-09-29.ps1 -DryRun`
   then the same line without `-DryRun`. Stop later by creating data\cache\capture_supervisor\STOP_live_shadow.
2. Keep the Claude app open and the laptop awake through 08:37Z 09-30. If either one-shot did not run, use the fallbacks.
   Fallbacks are valid ONLY between 06:00Z and 16:00Z, with no live game in any captured sport, and free RAM >= 1.5 GB.
   - state2 fallback (script is on master):
     `powershell -NoProfile -File docs\operations\relaunch_state2_s535_2026-09-29.ps1`
   - S561 fallback (Git Bash, then PowerShell):
     `cd /c/Users/neelj/nba-ai-system && git cherry-pick c4bd924c4d884a04d71d76c918d23e6076d1f1a3`
     (the pick was rebased in /c/Users/neelj/nba-harness-h232 and is predicted clean; if it conflicts, run `git cherry-pick --abort` and stop.)
     `cd /c/Users/neelj/nba-ai-system && git rev-parse HEAD` (copy the full 40-hex sha)
     `powershell -NoProfile -File docs\operations\relaunch_books_s561_2026-09-30.ps1 -s561Sha <that full sha>`
     The script refuses if the sha is not 40 hex or not an ancestor of HEAD. Do the relaunch right after the pick: landing S561 means adopting it.
3. Approve or decline S593 (MLB gameday push socket, a new long-running process; MLB state lag about 22 s down to about 7 s).
4. Log codex back in before 10-05 09:56 local. Codex is down; all verification is Opus-only until then.
5. Leave about 2.7 GB of RAM free around 06:05Z 10-01 for the first fitted night (S501 defers the night otherwise; the tick retries).
6. Optional: archive the 9 finished scheduled-run sessions.
7. Optional: prune worktrees, but ONLY those on the SAFE TO PRUNE list in docs/evidence/harness/WORKTREE_INVENTORY_2026-09-30.md
   (O1 was still writing it; it did not exist yet when this brief was written). Never prune h232, h300, h261, h320 or h322 on memory alone.
8. Optional (from the five-hour plan): set sleep = never on AC and/or WakeToRun for the tick.

## Expected-not-faults

- Paper night 09-29 (~06:05-06:10Z 09-30) will show scoreboard amendment_mismatch and arm E config_not_effective (exit 0). Both are by design.
- A night can exit 4 with a low-RAM deferral (S501, below about 2700 MiB free). The next 30-min tick retries it.
- Every non-MLB state row has a null scheduled_start. Cause: venue_instant() at
  scripts/platformkit/ingame/local_state_capture_dates.py:89 rejects ESPN minute-precision dates such as "2026-09-30T04:00Z".
  This is a known bug, not new breakage. The S502 fix is queued for the improve run; it must land (plus a state2 adoption) before TNF
  (NOW.md says TNF 10-01; the fleet facts say 10-02 -- kickoff is Thursday 10-01 ET, which is 10-02 UTC).
- S492 commit B (h300 2aee65757) is intentionally NOT landed. It lands only after the 09-30 night receipt
  (docs/evidence/forward/scoreboard/2026-09-30.json), after S503's parser fix, and after a rebase (h300 conflicts on .gitattributes).
- The identity freeze on the 6 scoreboard identity files holds until about 07:00Z 10-01.

## Where the truth lives

- .planning/NOW.md, the top "STOPPING PLACE 2026-09-30" block: what runs, one-shots, the pending seals chain, worktrees.
- The S-register: docs/evidence/HARNESS_GAPS_2026-09-03.md (row status for S490, S492, S502, S503, S561, S593 and the rest).
- The outcome scorecard for the five-hour plan: docs/evidence/harness/FIVE_HOUR_PLAN_2026-09-30_OUTCOME.md (44 rows; approximate counts LANDED 25 / PARKED 6 / SPEC ONLY 7 / NOT STARTED 3; the table is the authority).
- docs/evidence/harness/FIVE_HOUR_PLAN_2026-09-30.md, "Needs the owner".
- This brief: docs/evidence/harness/OWNER_BRIEF_2026-09-30.md.
