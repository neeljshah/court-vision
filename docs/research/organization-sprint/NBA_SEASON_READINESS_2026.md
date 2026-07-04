# NBA Season Readiness Audit -- 2026-07-04

Read-only audit for opening night (~Oct 21, 2026, master plan Phase 7/W13).
Cross-ref: `.planning/PLAN_SELF_IMPROVING_AI.md` lines 322-341 (Phase 7.1-7.4).

## 1. DATA -- mostly ready

`games.parquet` 4846 rows, 2022-10-18 to **2026-04-12** (last season through
playoffs); needs one incremental ingest once 2026-27 preseason starts (existing
`ingest_schedule.py`/`ingest_boxscores.py`, not rebuilt). `data/nba/gamelog_*
_2025-26.json` (28+ files) confirms in-season ingest already exercised.
`odds.parquet` (1317), `asof_features.parquet` (1299), plus `asof_box_extra/
asof_quarter_shape/asof_runvar/defender_matchup_states` all present. Signal
catalog wired: `signal_catalog.CATALOG_SIGNALS` imports clean, 8 signal classes
(the "85 signals" headline is the broader intelligence-layer manifest, grep-
only, not re-derived here). CV: `data/models/osnet_x0_25_imagenet.pth` (re-ID)
present; detection weights not re-verified (tracking=`src/**`, human-gated).

## 2. IN-GAME -- partially wired

- Kalshi pre-wired: `kalshi_series_spec.SERIES_SPEC["nba"]` = KXNBAGAME
  (moneyline) + KXNBASPREAD (spread), both probed live 2026-07-03, currently
  closed (offseason) not absent. Gap: no KXNBATOTAL entry (WNBA/MLB both have
  one) -- unprobed for NBA.
- ESPN live-state IS NBA-ready: `ingame_live_state._SPORTS["nba"]` =
  `{"path":"basketball/nba","kind":"clock","reg_sec":2880.0}` already present
  (WNBA's identical-shape entry is live-proven). No code change needed.
- Enrichment espn_wp arm NOT NBA-wired: `espn_wp_reference.SUPPORTED_SPORTS =
  {"mlb","wnba"}` -- NBA absent. Same `basketball/{sport}` shape as WNBA
  (verified `winprobability[]`, 361 pts/event) makes NBA the obvious next
  probe, but unverified today -- do not assume it works.
- m6_ingame_loop (repricer) already passes NBA in its ProcSpec argv (`--sports
  mlb,soccer,soccer_intl,nba,tennis`) -- reprices NBA today even in offseason.
- **GAP**: `inplay_capture_loop.DEFAULT_SPORTS = [mlb,soccer_intl,tennis,wnba,
  npb,kbo]` -- NBA absent, and `m2_inplay_capture`'s ProcSpec has no argv
  override, so it inherits this default. NBA ticks are NOT captured/graded
  today, only repriced. This is the central Phase 7.2 open item.

## 3. GATES

- Tail-multi gate excludes NBA: `ingame_tail_scan_multi.SPORTS =
  [tennis,soccer_intl,soccer,wnba,npb,kbo]` -- no "nba" entry (confirms the
  flagged gap). Same for `ingame_tail_gate_multi.PRE_REGISTERED_AT_BY_SPORT`.
  Needs an NBA row once forward capture exists -- must fix the m2 gap first or
  pre-registration sits at n=0.
- WNBA states-gate ports cleanly: `domains/basketball_wnba/states_gate.py`
  (+`_ci`/`_join`/`_runner`) is generic basketball logic (additive
  run_last_3min/in_bonus term on the anchored blend, cross-fit md5-half,
  `_MIN_N_PER_HALF` floor) with only `ANCHORED_K=0.63`/`ANCHORED_W0=1.0` and
  the 168-game CDN-backfill corpus as WNBA-specific. Straight port target for
  `domains/basketball_nba/states_gate.py` once a comparable NBA
  linescores/checkpoint corpus exists -- not confirmed on disk this pass.
- NBA outcome resolver does NOT exist: wnba/tennis/npb/kbo/soccer all have one;
  no `nba_outcome_resolver.py`. This is Phase 7.1, explicitly unbuilt.

## 4. GAPS -- ranked, with module pointers

1. **NBA outcome resolver (7.1)** -- build `scripts/platformkit/ingame/
   nba_outcome_resolver.py` mirroring `wnba_outcome_resolver.py` (KXNBAGAME
   ticker -> ESPN event id alias + final-score resolver). Blocks all labels.
2. **Add "nba" to `inplay_capture_loop.DEFAULT_SPORTS` (7.2)** -- one-line
   change (human-gated file, PROPOSED diff only) once 7.1 lands; without it
   m2 never captures/grades NBA even though m6 already reprices it.
3. **Add "nba" to `ingame_tail_scan_multi.SPORTS` + a
   `PRE_REGISTERED_AT_BY_SPORT["nba"]` stamp** -- pre-register BEFORE forward
   capture starts (AUTONOMY_CHARTER discipline) so evidence counts from game 1.
4. **Probe + wire KXNBATOTAL** in `kalshi_series_spec.py` -- 5-min live
   `/markets?series_ticker=KXNBATOTAL&status=open&limit=3` check, same pattern
   as the file's existing WNBA/MLB probes.
5. **Probe NBA on `espn_wp_reference.SUPPORTED_SPORTS`** -- verify
   `basketball/nba` summary has `winprobability[]` (near-certain given WNBA
   parity) before adding; unverified, do not wire blind.
6. **Port WNBA states_gate to NBA (7.3-adjacent)** -- needs a comparable NBA
   corpus to WNBA's 168-game CDN-backfill; corpus existence is the real
   precondition (the module port itself is mechanical).
7. **NBA segment map (7.3)** -- confirm `ingame_segment_trust_multi.py`
   (currently scoped "soccer_intl/tennis/wnba" per header) and m25/m26 carry
   NBA's Q1-Q4+OT+L5 buckets with the EARLY-game lean (opposite MLB's late
   lean) -- not independently re-verified beyond the module header comment.
8. **m17 liquidity scan NBA extension (7.4)** -- daemon confirmed running
   (heartbeat/logs present); NBA market-type coverage not traced to source
   this pass (targeted grep of `kalshi_market_scan.py` found no bare
   "nba"/"SPORTS=" hits) -- re-check before opening night, do not assume covered.

## Already ready

Pregame NBA corpus current through last season; 8-signal catalog + broader
intelligence layer wired (grep-confirmed); OSNet CV re-ID model present; Kalshi
KXNBAGAME/KXNBASPREAD pre-wired + probed live; `ingame_live_state.py` NBA arm
code-complete (WNBA-proven template); m6 repricer already includes NBA.
