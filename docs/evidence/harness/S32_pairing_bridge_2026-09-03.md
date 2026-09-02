# S32 -- pairing bridge diagnosis: 0 paired rows in 36.6 h (2026-09-02 04:30-05:10 UTC)

Lane: S32 diagnosis (Fable). Pod READ-ONLY throughout (ssh reads + bounded GETs only;
nothing killed, started, scp'd, or written there). Calibration language only.
Repro script (offline, real tickers, assert-gated): scratchpad s32_bridge_repro.py --
all 4 checks pass locally; every load-bearing claim below is a pod read or a local run.

## ROOT CAUSE (one sentence)
The pairing bridge is NOT broken: 0 paired rows because data/domains/mlb/games.parquet
is ABSENT on the pod, so MLBPredictor.__init__ raises FileNotFoundError
(domains/mlb/predictor.py:91), registry.active_sports() returns [] (predict_service/
registry.py:150-161, verified [] live on the pod), the m1_producer scheduler loops
forever with due=[] never running a cycle (predict_service/scheduler.py:243-256;
boot-beat cycle_count=0 since 08-31 19:53:47, wchan=hrtimer_nanosleep), so
data/frontend/predict_service/mlb/latest.json never exists, live_p0 returns
p0=None/BASE_FALLBACK (live_p0.py:119-143), mlb_home_prob returns None on p0=None
(mlb_live_model.py:103), and _process_game exits reason="no_model_prob"
(inplay_capture_loop.py:846-848) BEFORE _dt.on_tick (:869) -- so
capture_pair_once has never once been reached.

## Evidence chain (each hop measured this session)
1. ls_fn wiring: the runner injects NO live_state_fn (inplay_capture_runner.py:120-153
   passes only mlb_deep/kbo_deep/depth_capture_fn defaults); poll_once defaults
   ls_fn = lambda s,g: _ls.live_state(s,g) (inplay_capture_loop.py:621). live_state
   keyed by a Kalshi ticker misses by construction; the ONLY bridge is
   _scan_live_by_legs (:452-497) over _ls.live_states(sport).
2. ESPN reachable from the pod (running process AND fresh interpreter): bounded pod run
   of live_states("mlb") returned the one in-progress game (401816772, LAD vs STL,
   Bot 9th) with p0=None p0_source=BASE_FALLBACK. The 380 settle rows (finals path,
   same ESPN host, settled_finals.py:32) landed during the live window -- fetch works.
3. The bridge WORKS: pod heartbeat 2026-09-02T04:54:17Z, denominator 88 games:
   no_live_state 84 (tennis 61, mlb 17, kbo 4, npb 2), no_model_prob 4 (npb 3, mlb 1),
   paired 0. The 1 mlb no_model_prob row IS the live game, bridged to its ESPN state
   and refused at the model step -- the failure observed in the act.
4. p0 store: data/frontend/predict_service/ on the pod contains ONLY _heartbeat.json
   (202 B, "boot-beat ... first cycle not yet complete", cycle_count 0, mtime 08-31
   19:53). No per-sport dir has ever existed. m1_producer .out/.err both 0 bytes.
5. Predictor: pod registry.build_predictor("mlb") -> None in 6.0 s;
   direct MLBPredictor() -> FileNotFoundError "/workspace/nba-ai-system/data/domains/
   mlb/games.parquet"; refreshed_predictor() -> same. Pod data/domains/ holds only
   kbo + soccer_intl. Pod registry.active_sports() -> [] (all sports).
6. Model gate: mlb_home_prob returns None when p0 is None (mlb_live_model.py:100-104);
   local repro: same state with p0=None -> None, with p0=0.55 -> 0.0440. So every live
   mlb tick dies at no_model_prob and on_tick/capture_pair_once (:869, live_grade.py:125)
   never runs -- matching grep -l model_prob data/cache/ingame_grade/*/*.jsonl = 0.

## Hypotheses: falsified / confirmed
- FALSIFIED "every game no_live_state" (register S32 wording): measured 84/88
  no_live_state + 4/88 no_model_prob; live games show no_model_prob. The no_live_state
  majority are liquid markets for not-currently-live games (tomorrow / finished) --
  correct behavior, not the defect.
- FALSIFIED "ticker->game join broken": local repro on real labels
  ({"St. Louis","Los Angeles D"} vs ESPN "St. Louis Cardinals"/"Los Angeles Dodgers")
  aligns yes_home/yes_away correctly (_team_in_legs/_align_home_yes,
  inplay_capture_loop.py:337-369).
- FALSIFIED "UTC/ET date boundary blocks live games": ticker fragment is the ET date
  (verified: BOTH KXMLBGAME-26SEP012210STLLAD and -26SEP022210STLLAD exist on Kalshi;
  legs -LAD/-STL). The guard's yesterday-grace (:484-487) keeps a post-midnight
  still-live game bridgeable. Fetches do not need two dates: live_states carries no
  date parameter at all (scoreboard default board).
- FALSIFIED "Kalshi 429 at discovery causes no_live_state": a 429'd series contributes
  no ticks, so the game never enters legs_by_game (:665-672) and gets NO row at all;
  no_live_state requires a liquid leg to exist. Heartbeat: n_requests_total 19,
  n_429_total 1. Discovery and live-state are independent paths.
- CONFIRMED root cause: p0 starvation from the absent pod corpus (chain above).
- CONFIRMED NEW side defect (live-verified, would fire once p0 is fixed): after ET
  midnight the NEXT ET-day's twin market of a same-team series binds to yesterday's
  still-live game: at 04:54Z the SEP02 STLLAD ticker (game starts 22:10 ET Sep 2)
  bridged to the Sep-1 live game 401816772, because game_date==today passes :484-487.
  Local repro reproduces all three verdicts (pre-midnight reject, post-midnight
  mis-bind, correct SEP01 bind). Today it was masked by no_model_prob; unmasked it
  would write a misaligned pair (a pregame price against a live state) into the grade
  series -- the exact corruption the 2026-07-10 date guard was built to stop.

## PROPOSED fix (not applied; inplay_capture_loop.py is shared/live -- PROPOSED only)
FIX A (the actual unblock -- data/ops, no code; pod-write owner account, not this lane):
  1. Land the corpus (local file exists: data/domains/mlb/games.parquet, 343,723 B):
     scp -F ~/.ssh/config.pod data/domains/mlb/games.parquet \
       pod:/workspace/nba-ai-system/data/domains/mlb/games.parquet
  2. NO restart needed: predictor cache TTL 3600 s (predictor_jd.py:53) and the
     scheduler re-reads active_sports() every 600 s loop (scheduler.py:243-249), so
     mlb becomes due and latest.json materializes within <=1 h. Accelerate with ONE
     bounded command: cd /workspace/nba-ai-system && \
       python -m predict_service.produce --sport mlb
FIX B (guard the twin mis-bind before pairs start flowing) -- PROPOSED diff:
    --- scripts/platformkit/ingame/inplay_capture_loop.py  (PROPOSED, do not apply)
    @@ top of file: add  import re  and:
    +from scripts.platformkit.paper.et_day import to_et as _to_et
    +_TICKER_START_RE = re.compile(r"-\d{2}[A-Z]{3}\d{2}(\d{2})(\d{2})[A-Z]")
    @@ _scan_live_by_legs, directly after the existing date check (:484-487)
    +            # S32 series-twin guard: a same-ET-day ticker whose embedded ET start
    +            # (e.g. ...26SEP022210... -> 22:10 ET) is still >30 min in the future
    +            # cannot be live; without this, tomorrow-night's twin binds to
    +            # yesterday's still-live game once the ET day rolls over (verified
    +            # 2026-09-02 04:54Z). Unparseable time -> no-op, behavior unchanged.
    +            m = _TICKER_START_RE.search(str(gid or "").upper())
    +            if m and game_date == today:
    +                now_et = _to_et(nowdt or datetime.now(timezone.utc))
    +                if (now_et.hour * 60 + now_et.minute + 30
    +                        < int(m.group(1)) * 60 + int(m.group(2))):
    +                    return None

## Replay plan (next live MLB window, 2026-09-02 evening ET, first pitch ~18:40 ET)
Precondition (after FIX A): pod stat of
  data/frontend/predict_service/mlb/latest.json -- exists, mtime < 1 h old.
During the window (read-only): read data/cache/ingame_grade/_capture_heartbeat.json
  on the pod and print as_of, n_pairs, and each mlb (game_id, reason).
PASS artifact: n_pairs > 0 with an mlb row paired=true/reason "ok", and
  grep -l model_prob data/cache/ingame_grade/mlb/*.jsonl | wc -l  flips 0 -> >0.
Guard-B check: after 00:00 ET with a west-coast game still live, the next-day twin
ticker must stay unbridged (no_live_state), while the correctly-dated ticker pairs.

## NOT VERIFIED
- Why the corpus never reached the pod (data/ is gitignored by design; deploy history
  not traced). Whether tennis/soccer/nba corpora are also absent (implied by
  active_sports()==[], per-sport error not enumerated beyond mlb).
- The Sep-1 live-window per-tick reason rows themselves (heartbeat is overwritten;
  data/cache/ingame_shadow_history/ does not exist on the pod because every shadow
  field was None) -- the live-window behavior is inferred from the 04:54Z in-the-act
  row + code path, not from a stored per-window artifact.
- Whether the SEP01 STLLAD ticker was in the liquid list earlier in its window (its
  pair-side row was never written anywhere by construction).
- Pod module drift (raw md5 pod vs local HEAD): ingame_live_state.py, live_p0.py,
  live_board.py DIFFER (mlb_live_model.py identical) -- S21 territory; not the root
  cause here (both versions read the same absent paths), but the replay should re-run
  the md5 sweep before attributing any residual delta to code.
