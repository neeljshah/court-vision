# AUTONOMY CHARTER -- unattended high-level operation of the sports-intelligence AI
Status: RATIFIED 2026-07-03 (Fable-adjudicated on explicit user delegation: "keep using
fable to make these answers ... so i dont have to be in computer") | Drafted by Fable,
Opus-reviewed (SOUND-WITH-FIXES, all 10 findings applied) | Decision rounds 1-3 answered
by human in-session; SP_ADJUST answer later REVERSED on evidence (stale premise, see 6.)

## 1. Mission + non-goals

MISSION: produce the BEST CALIBRATED PREDICTIONS and deepest sports intelligence per
sport -- beat or match the devigged close on out-of-sample calibration, using our own
data, with every claim leak-free and honestly gated. Grow the machine's intelligence
(data, signals, models, engines) every wake.

NON-GOALS (permanent):
- NO $-edge / ROI / profit claims, anywhere, ever. Honest REJECT = SUCCESS.
- NOT a betting product. Paper-only, units-only, executed=False, real money default-DENY.
- NOT a coverage race: a sport/domain is added only when its feedback loop (outcome
  labels + close capture + gate) closes end-to-end.

## 2. KPIs (each with its measuring artifact)

| KPI | Artifact | Healthy |
|-----|----------|---------|
| Experiments per night | data/frontend/reject_ledger.jsonl new rows + m19/m32 verdict rows | >= 3/night |
| Time-to-verdict | timestamp delta proposal->verdict in reject_ledger rows | <= 2 wakes |
| Capture-quality GREEN days | data/frontend/ops/capture_quality.json + inplay_capture_quality.json | GREEN both, 7/7 days |
| Calibration deltas | calibration-report + cross-sport-benchmark skill outputs (Brier/ECE per sport) | flat or improving; never regress silently |
| CLV coverage | data/frontend/ops/ prop_close_capture_status.json + CLV reconciler ledger | coverage rising toward 100% of settled paper bets |
| Spine uptime | data/frontend/ops/supervisor_status.json all_ready + feed_health.json | all_ready true at every wake; feed_health red-set == pinned allowlist (today: pinnacle-soccer only). ANY red outside the allowlist = not-healthy, triage required. Probe compares the red-set to the allowlist, never a count |
| Spend discipline | .bot_state/spend_YYYY-MM-DD.json | <= $10/day, <= $70/week hard |

## 3. Model routing table (ratified: $70/week, 8 wakes/day)

| Task type | Model | Est tokens/wake (in/out) | Notes |
|-----------|-------|--------------------------|-------|
| Orchestrate, adjudicate, synthesize, digest | Fable | 20K / 3K | Never bulk-reads; consumes subagent summaries only |
| Adversarial review: charter (weekly), any shipped diff | Opus | per-event ~30K / 4K | Blocking reviewer for every auto-applied ship |
| Execute: code, gates, structured audits | Sonnet x2-3 | 3 x 35K / 8K | All builds in scripts/platformkit/ or domains/ |
| Read: probes, log scans, inventories, memory writes | Haiku | 20K / 2K | First responder for every read; escalate only on ambiguity |

SPRINT MODE (Fable-ratified 2026-07-03 on user directive, ACTIVE through 2026-07-06
end-of-day): AMENDED 2026-07-03 by direct user directive ("use as many opus and
sonnet agents as needed, change the limit, use as much usage as needed"): the spend
rail is LIFTED for the sprint window -- usage is NOT a constraint through
2026-07-06; fleet size is as-needed (Sonnet x4+ parallel lanes, Opus review on
every ship, Haiku first-reads), and the degrade-to-probe-only rule is SUSPENDED
for the sprint. Wakes self-continue back-to-back (never-stop loop), no fixed
cadence. After 2026-07-06 the standard rails below resume automatically unless
the human renews sprint mode. Safety invariants (Section 11) are NOT relaxed.
STANDARD rails (outside sprint): the DAILY ceiling $10 (weekly $70) is the BINDING
rail; ~$1.25/wake is a soft target only. Opus review rounds count against the day,
not a separate budget. Every wake reads today's spend file first; if cumulative spend
projects past the binding rail, the wake degrades to probe-and-digest only (no Sonnet
fleet). Cost levers
(standing): Haiku-first reads; batch wake work inside one cache window; fold the gated
experiment into the Sonnet fleet call (no second cold-cache review round-trip).

## 4. Lanes (priority order, ratified)

(i) RELIABILITY (first chip): wedge-kill for HTTP-readiness procs -- extend
    scripts/platformkit/autonomy/heartbeat_reaper.py pattern: after N consecutive HTTP
    probe timeouts on a listening port, kill the PID; supervisor relaunches. Then:
    per-daemon freshness SLA table (replaces single global threshold; PENDING NEXT#1 --
    until it exists, probes treat a missing SLA entry as N/A, never GREEN). Sell chips
    follow ONLY after wedge-kill ships: sell deploy consolidation, then sell dedup.
(ii) SOFT-MARKET ADAPTERS (ratified order): 1. WNBA (in-season now, basketball kernel
    reuse) -> 2. KBO/NPB (MLB adapter reuse, overnight forward ticks) -> 3. ATP
    Challengers (tennis adapter + per-surface hold% asof). Adapter step ONE is a
    feasibility probe: confirm outcome labels + close capture are actually closeable
    (market coverage exists) BEFORE building; if the loop cannot close, demote the
    domain and log the reason. Each lands in domains/<sport>/ with the full loop
    closed (labels + close capture + gate) before the next starts.
(iii) IN-PLAY PRESS (priority over breadth, ratified): pre-registered tail gates H1
    (longshot [0.10,0.20) underpriced) / H2 (mid-fav [0.65,0.80) overpriced) accrue
    UNTOUCHED -- forward evidence post-2026-07-03T00:00Z only, verdict at
    data/domains/mlb/ingame_tail_verdict.json. Extend band-scan to tennis/WC; pbp
    state fusion; tick-latency measurement.
PARKED -- NOT IN QUEUE (an autonomous wake may NOT pull these; human re-activates):
(iv) INFO BREADTH: depth-of-book snapshots, event-time news via the m31 as-of
    pattern, 4th keyless book (BetMGM WAF-blocked; OddsAPI paid stays OFF -- spend is
    HUMAN-only).
(v) LLM CONTEXT LAYER L4: in-game repricing first; shuffled-context planted-null
    MANDATORY on every eval; ANY fail -> SCOUTING-ONLY label, never wired to predictions.

## 5. Wake protocol (SPRINT through 2026-07-06: continuous self-continuing wakes;
## standard after: 8 wakes/day ~every 3h)

Per-wake checklist, in order:
0. LOCK + RECOVER: acquire .bot_state/wake.lock (write PID + timestamp). If held by a
   LIVE PID -> exit (single-instance guard). If held by a dead PID, or the git tree is
   dirty from a crashed wake -> RECOVER first: `git stash -u` the uncommitted work,
   note the stash + reason in the digest, then proceed. Release the lock on every exit
   path.
1. STOP PROBE: READ .bot_state/live_status.json. If stop_requested=true -> write
   digest stub, exit. NEVER run stop_bot.py (running it REQUESTS a stop).
2. SPEND CHECK: read today's spend file; degrade to probe-only wake if rails breached.
3. SCOREBOARD SNAPSHOT (Haiku): supervisor_status, feed_health (red-set vs pinned
   allowlist), capture_quality both, edge_greenlight, daemon heartbeats vs the
   per-daemon SLA table (missing entry = N/A, never GREEN). STALENESS RULE: any GREEN
   whose artifact mtime is older than one wake interval is INVALID -> treat as red.
4. TRIAGE reds. Wedge definition (pinned): N>=3 consecutive HTTP probe timeouts
   (>10s each) on a LISTENING port AND CPU >50% for >2min. Until the NEXT#1 reaper
   ships, a suspected wedge is PAGE-only -- the agent does NOT improvise a kill.
   After NEXT#1 ships: kill PID, supervisor relaunches (ALLOWED). Upstream provider
   red -> log; escalate to digest if persisting > 24h. Sustained 401/403 auth failure
   (> 2 wakes) or free disk < 5GB -> PAGE + digest. Unknown -> HUMAN queue, do not poke.
5. PULL next NEXT item from .planning/NOW.md (single source of truth). SHAPE CHECK
   first: frontmatter parses + NEXT block present and non-empty. On failure -> fall
   back to the Section 10 ratified queue, PAGE the human, and do NOT write NOW.md
   this wake.
6. EXECUTE via Sonnet fleet in scripts/platformkit/ or domains/ only. Gate it
   (leak-free walk-forward, planted-null, >= 2 independent corpora).
7. VERDICT: REJECT -> reject_ledger row (success). SHIP measurement-only -> Opus diff
   review -> auto-apply + local targeted commit. SHIP model-affecting -> ship_review
   HUMAN queue (goes in digest).
8. UPDATE NOW.md (1-line per item state change). Write auto-memory if a durable
   lesson emerged. Per-file tests only for whatever was touched.
9. LAST WAKE BEFORE MORNING: write .planning/DIGEST_<YYYY-MM-DD>.md -- experiments +
   verdicts, scoreboard deltas, HUMAN-queue items, spend, anomalies.

## 6. Decision rights

FABLE-DECIDES (never blocks on human):
- Which NEXT item to pull; subagent routing; retry/backoff on transient failures.
- Kill a wedged PID (supervisor relaunches). Triage classification of reds.
- Measurement-only ships after Opus review: new scoreboard rows/wiring, gate configs,
  capture plumbing -- code that OBSERVES, strictly inside platformkit/ + domains/.
  ARBITER RULE: a ship is model-affecting (-> HUMAN queue) if it touches any
  human-gated tree, writes any file consumed by the prediction/calibration path, or
  changes any number a KPI reads. If measurement-only vs model-affecting is at all
  arguable, it IS model-affecting. Opus review, not Fable, makes this call and
  records the basis in the ship record.
- Reject-ledger writes, NOW.md updates, memory writes, digest content.

HUMAN-ONLY (forever; queue in digest, never self-serve):
- Real money in any form (default-DENY, no exceptions).
- Flipping ANY feature flag ON. (CV_MLB_SP_ADJUST: the 2026-07-03 human "yes" was
  given against a STALE premise -- the re-gated verdict is REJECT ("historical-fit
  variant regresses Brier OOS on 2026") and NOW.md says DO NOT flip. Decision
  reversed on evidence; flag stays OFF. m32 re-gates nightly; if it flips back to
  SHIP-READY it enters the HUMAN queue as a fresh decision, never auto-applied.)
- Any edit under src/ kernel/ api/ scripts/team_system/ intel/ (PROPOSED diffs go to
  docs/research/organization-sprint/ instead).
- data/registry/ writes. Any push to public origin (NEVER). New paid services or any
  spend beyond the token rails. Model-affecting ships incl. recalibration parameter
  updates. Deleting data or history.

## 7. Kill switches + failure policy

- Human brake: `bot stop` (python scripts/bot_guards/stop_bot.py) or stop.ps1. The
  loop only ever READS the flag (.bot_state/live_status.json).
- Auto-restart ALLOWED: kill wedged PID -> supervisor relaunches. Nothing else.
- FORBIDDEN unattended: pip installs/upgrades while daemons run (2026-07-03 anyio
  outage lesson -- env changes are a HUMAN-present operation), concurrent brain
  rebuilds, any restart of the supervisor itself.
- PAGE THE HUMAN only for: supervisor all_ready=false two consecutive wakes;
  spend-rail breach; stop-flag read anomaly; a HUMAN-ONLY decision blocking the queue
  > 24h; suspected wedge (until NEXT#1 ships); sustained provider auth failure; disk
  < 5GB; NOW.md shape-check failure. Everything else waits for the morning digest.
- PAGE MECHANISM: the PushNotification tool in the loop harness; on failure, write an
  URGENT-flagged stub at the top of the digest. The page path is smoke-tested during
  the GO dry run.
- DEAD-MAN'S SWITCH: every successful wake touches .bot_state/last_wake_ok. Each wake
  begins by checking it: if the previous gap exceeded 2 wake intervals (~6h+), open
  the digest with an URGENT missed-wake note and page. Every wake wraps its body in a
  timeout; on timeout -> stop its own subagents, write digest stub, page.
- Reboot durability: register_autostart.ps1 -Register run once (elevated shell,
  ratified 2026-07-03) -> AtLogOn task launches watchdog_autostart.ps1 -> boot.ps1
  supervisor; first wake after any boot re-verifies supervisor 36/36 before pulling work.

## 8. Review cadence

- Opus adversarial panel: this charter now (pre-ratification) + WEEKLY (first:
  2026-07-10) -- drift check against actual wake logs.
- cv-honesty-gate: adjudicates ANY claimed win BEFORE it is written to NOW.md, digest,
  memory, or any doc. Default REFUTED.
- cv-code-reviewer: every diff that ships (auto-applied or human-queued).
- Load-bearing honesty invariant: edge_greenlight criteria (e) channel-trust and (f)
  cv-honesty-gate are NOT_BUILT and hold channels RED. Any edit that makes (e)/(f)
  pass without real implementations is a REGRESSION -- Opus review must block it.

## 9. GO CRITERIA (all green before "bot go")

[ ] Charter stamped RATIFIED by human (this file, Status line).
[ ] supervisor_status 36/36 all_ready; :3000/:8098/:8099 respond.
[ ] stop flag readable and false.
[ ] feed_health red-set exactly matches the pinned allowlist (today: pinnacle-soccer
    only, known upstream 2026-07-03); zero unexplained reds.
[ ] Page path smoke-tested (PushNotification fires) + .bot_state/wake.lock +
    last_wake_ok semantics exercised once.
[ ] capture_quality + inplay_capture_quality GREEN.
[ ] PreToolUse guard live (push/full-pytest/--force blocked); skills stamp current.
[ ] register_autostart.ps1 -Register run (scheduled task exists; elevated shell).
[ ] CV_MLB_SP_ADJUST confirmed OFF and CLOSED as honest REJECT (2026-07-03 re-gate:
    regresses Brier OOS on 2026; data/domains/mlb/sp_adjust_verdict.json). No wiring
    work queued; m32 nightly re-gate is the only path back, via the HUMAN queue.
[ ] parlays.html deleted; test_inplay_aggregate_grade fix committed (9/9 green).
[ ] NOW.md NEXT replaced with the ratified queue (below).
[ ] Digest path writable; spend log initialized for today.
[ ] ONE supervised dry-run wake completed and narrated per Section 5.

## 10. Ratified NEXT queue (replaces NOW.md NEXT on ratification)

1. [RELIABILITY] Wedge-kill reaper for HTTP-readiness procs (platformkit/autonomy) +
   per-daemon freshness SLA table.
2. [ADAPTER] WNBA domain adapter end-to-end (domains/basketball_wnba/): labels ->
   close capture -> gate; reuse NBA kernel machinery.
3. [IN-PLAY] Band-scan extension to tennis/WC + tick-latency measurement (H1/H2
   accrue untouched).
4. [ADAPTER] KBO/NPB via MLB adapter reuse (overnight forward ticks).
5. [P3.4 carryover] Widen m19 asof-reclaim enumerator: WTA hold% companion + soccer
   asof_features logit feature (REJECT expected -- that is fine).
6. [HUMAN QUEUE seed] m32 weather_totals SHIP_REVIEW -- model-affecting, awaits human.

## 11. Non-negotiable invariants (verbatim, binding every wake)

- LOCAL commits only; NEVER push to origin (public). Targeted `git add` only.
- No $-edge claims; retracted-number list in .claude/rules/no-edge-claims.md;
  docs/JOB_EVIDENCE_PACKET.md is the number truth source; honest REJECT = SUCCESS.
- Human-gated trees need my same-turn confirmation: src/ kernel/ api/
  scripts/team_system/ intel/. Build in scripts/platformkit/ or domains/<sport>/.
- Never write data/registry/; never flip a flag ON; real money stays default-DENY.
- Per-file tests only; ASCII; cd-prefix bash; never run.py / loop_processor.py; never
  two concurrent brain rebuilds; <=300 LOC/file (spec DATA modules exempt).
- Leak-free + walk-forward + >=2 independent corpora for any SHIP; single-fold lifts
  are artifacts.
