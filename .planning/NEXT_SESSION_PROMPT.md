# DAY SESSION PROMPT -- written 2026-07-06 ~09:45 local by the night watchman
Copy-paste for the DAY session. Supersedes the 2026-07-06 ~05:55Z night prompt
(that session executed everything; ledger in .planning/NOW.md, entries
"NIGHT WATCHMAN STARTUP DUTIES DONE" + "WAKE-2"). NOTE: from 07-07 the
STANDARD RAILS apply ($10/day, 8 wakes/day per AUTONOMY_CHARTER).

## WHAT THE NIGHT DID (real counts, all ledgered + pushed private)

1. RESUMED sport-grid rollout wf_5bab3431 to completion:
   - tennis config committed e700f85f; GENERATED tennis_p1_match_context
     1,312 + tennis_p2_match_context 1,346 claims, ALL verified, 0 mismatch,
     indexed (.index.jsonl on disk).
   - soccer GENERATED soccer_intl_team_travel_rate 1,458 verified / 0
     mismatch, indexed (index reported stale again by HQ3 -- refresh is a
     one-call build_index if needed).
   - Counts are honest floors-applied numbers (well below the 10-20k rough
     estimates; floors excluded 3,976+5,016 tennis / 510 soccer cells).
2. ASK-ROUTER FIX COMMITTED a0c42694: entity-type gate + metric-synonym map
   as DATA + longest-alias-match + UNANSWERABLE-over-wrong-answer in BOTH
   fast/slow paths; test_ask 36/36 + test_ask_index 15/15 green; Opus
   APPROVE. Regression pinned: "top 5 nba players by free throw percentage"
   -> PLAYER ft_reliability, never team pts/game.
3. HISTORICAL QUANT SWEEP wf_9a13ee78 COMPLETE (docs under
   docs/research/depth-program/, gitignored-local):
   - HQ1 CALIBRATION_HISTORY VERIFIED (byte-identical independent re-run).
     Honest BEHIND cells: MLB generic-vs-tuned +0.00362 Brier; vs-close
     freshness gaps NBA totals +1.058 RMSE (2025-26-only odds corpus), MLB
     totals +0.2777 RMSE, ATP +0.0149 Brier. Disk limits: NBA odds =
     2025-26 only; MLB games+odds end 2021-11-02. NAMING TRAP: calibration
     "soccer" = data/domains/soccer; data/domains/soccer_intl is used by NO
     calibration/benchmark harness.
   - HQ2 CLOSE_BACKFILL_FEASIBILITY: honest NOT-WORTH-A-BUILD (0/1,981
     backfillable via real attach_true_close; widened ceiling 220 rows =
     only 19 distinct events; blockers = capture cadence + missing
     team_total market_type). Verifier caught false headline reasoning
     (30 moneyline-shaped 1X2 rows exist, not 0: 24 cadence-miss + 6 fail
     two-way devig on a 3-way market) + 618-vs-638 stat; doc CORRECTED in
     place, sha256=3a5f929955b693f5b175a976b9ba6e955f720f44ec5321d5a30186e
     15359c24e (227 lines).
   - HQ3 INTEL_ORG_AUDIT VERIFIED: 0 deleted-producer orphans; 28/43
     verdict files ask()-unreachable; verdict_coverage_report's own
     universe missing 14 on-disk verdict files; WNBA/KBO/NPB have ZERO
     reject-ledger footprint; fast-path indexes exist for only a few
     families.
4. MLB CLAIMS VALIDATION GAP (kill landed between generate and validate):
   mlb_team_rate CLOSED this morning -- 186/186 VERIFIED, 0 mismatch, 1.6s,
   index built. mlb_batter_rate + mlb_pitcher_rate (~11,886 claims, 560MB +
   296MB jsonl) DEFERRED: validate_claims_file_batched's _load_claims reads
   the WHOLE file into memory (several-GB peak) and the box has ~2GB free
   -- running it is exactly what glitched the machine. See day queue (g).
5. FLEET RESTARTED 08:57-08:59 local by the user (attended). This ARMED m38
   (autoloop_runner --interval 86400 now supervised) and the queued reaper
   fix. Post-restart fresh reads: freshness overall GREEN n_red=0 (22 NA =
   first-tick pending), feed_health GREEN all 5 providers (kalshi 5-sport
   HTTPErrors cleared). The night's 7-RED scout report was pre-restart
   staleness -- premise-check caught it, no false fix applied.

## BLOCKED / WATCH

- m13 props_snapshot: root-caused earlier (every tick times out at 240s +
  timeout path never writes the fallback snapshot); its fix chain
  wf_d89026f0 was KILLED mid-flight and NOT resumed by the night (out of
  night scope). The restart may mask the symptom for a while. CHECK m13
  freshness during the day; if RED again, resume wf_d89026f0
  (resumeFromRunId) rather than re-deriving the fix.
- 22 freshness rows NA: count is CONSTANT (22 at 09:20, 10:06, 11:03)
  while the short-interval daemons in the NA set are all running -- so
  this is a freshness-runner MAPPING gap (names with no table entry;
  the report's own note: NA = unknown, never GREEN), NOT stale daemons.
  Pre-existing. Day-queue nit: extend the runner's name->output table
  (code change, Sonnet lane + Opus review). Do not chase NA rows as
  outages.
- Transient single-probe feed_health HTTPErrors observed (kalshi/mlb at
  10:06 self-cleared by 11:03; pinnacle/soccer at 11:03) -- one-off probe
  failures are noise; only investigate a provider+sport RED that persists
  across consecutive 600s cycles.

## DAY QUEUE (standing + new)

(a) defender-dims family prereg (2 SHIP-at-gate candidates; home_sot
    precedent binding: 1-of-N SHIPs are artifacts until replicated).
(b) consolidated reclaim gate-bars amendment (tennis-meta / mlb-inning /
    player-adv).
(c) RT1 soccer HT/referee re-scope to domains/soccer/.
(d) tennis/wnba shadow promotion adjudication (evidence ripens ~07-07;
    shadow-history accrual as of last scout: mlb 2 files, tennis 2, wnba 1).
(e) m38 arming -- DONE (armed by the 08:57 attended restart). Verify its
    first supervised cycle report instead.
(f) sweep-doc follow-ups, now concrete: (i) fix verdict_coverage_report's
    file universe (+14 missing files); (ii) decide soccer_intl's place in
    calibration harnesses (wire or document-as-unused); (iii) WNBA/KBO/NPB
    reject-ledger densification.
(g) DONE ~15:30 07-06: streaming validator shipped (98cb5b3b, Opus PASS)
    and both stores validated+indexed with it -- pitcher 4,434/4,434 +
    batter 7,452/7,452, all VERIFIED, 0 mismatch, RSS bounded 207-379MB.
    MLB rate families now fully ask()-servable.
(h) index densification: fast-path .index.jsonl for remaining ask()-
    reachable families (one build_index call per family; soccer_intl_team_
    travel_rate needs a refresh).

## BINDING RAILS (unchanged)
Never push origin (private OK). Never write data/registry/. Never flip a
flag. Never edit src/ kernel/ api/ scripts/team_system/ intel/. <=300
LOC/file. ASCII stdout. Per-file tests ONLY. No $-edge claims -- honest
REJECT = success. Targeted git adds (git add -f only for .planning/NOW.md).
Probe the stop flag by READING .bot_state/live_status.json. Ledger every
fix in NOW.md + push private at wake close.
