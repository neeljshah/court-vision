"""scripts.platformkit.ingame.inplay_capture_loop -- MEASUREMENT-ONLY in-play capture daemon (W4).

The thin live daemon that closes the in-play measurement loop end-to-end by WIRING the four
in-game pieces together -- it adds NO new prediction / pricing / sizing math, it only
ORCHESTRATES the existing, tested chain on a cadence:

  per LIVE game, per tick:
    1. live state  -> ingame_live_state.live_state(sport, gid) returns
       (state_diff, frac_elapsed, p0) where p0 is AUTO-SUPPLIED from the leak-free pregame
       snapshot (P1 wire) -- so the served / paired model_prob CARRIES THE PROVEN PRIOR
       instead of silently degrading to BASE.
    2. model prob  -> model_fn(sport, state) wraps predictor.predict_live (read-only),
       returning P(home win) computed from state-as-of-this-tick (leak-free).
    3. live price  -> inplay_kalshi.fetch_inplay(sport) (W2: series_ticker=KX<league>GAME)
       gives the LIQUID per-game YES(home)/YES(away) implied probs; an illiquid / untraded
       market emits NOTHING (is_liquid gate) so we never pair against a fake price.
    4. pair+decide -> inplay_daytrader.on_tick: ALWAYS captures the (model_prob, devigged
       price) pair via live_grade.capture_pair_once -> data/cache/ingame_grade/<sport>/
       <game_id>.jsonl, and paper-decides enter/hold/exit in UNITS (idempotent).
    5. on FINAL    -> settle_stamp.stamp_final appends the held-out binary home_win LABEL
       (W3) so inplay_aggregate_grade's OUTCOME arm can fire once >=5 games settle.

Each tick writes a HEARTBEAT envelope (stale-never-green: an operator can see liveness; a
down feed yields zero live games + a clean heartbeat, never a fabricated game). Error
ISOLATION: one bad game's failure never stops the others; one bad tick never stops the loop.

HONESTY (binding): MEASUREMENT ONLY. PAPER / UNITS / probability -- there is NO $ / roi /
pnl / stake$ field anywhere; edge_claimed is always False; executed is always False (the
real-money gate is a SEPARATE human flip, DEFAULT-DENY). The daemon NEVER executes real
money, NEVER flips a flag, NEVER arms autostart. It is supervised-READY (heartbeat) but NOT
auto-armed -- the supervisor manifest wiring ships as a PROPOSED diff only. Bounded runs
ALWAYS stop (max_ticks / clock injected in tests). LEAK-FREE: p0 is pregame; model_prob is
as-of-tick; the close is the held-out yardstick; the outcome is a label stamped only at FINAL.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network
at import; no data/registry write, no flag flip, no autostart; never edits
ingame_live_state / inplay_daytrader / settle_stamp / inplay_kalshi / predict_service /
domains / src / kernel (all REUSED through injectable callbacks).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_capture_loop.py -q
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import inplay_daytrader as _dt
from scripts.platformkit.ingame import ingame_live_state as _ls
from scripts.platformkit.ingame import ingame_segment_trust as _segment_trust
from scripts.platformkit.ingame import settle_stamp as _settle
from scripts.platformkit.odds_provider.kalshi_series_spec import ticker_game_date as _ticker_game_date
from scripts.platformkit.paper.et_day import now_et_day as _now_et_day

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/inplay_capture_loop.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_HEARTBEAT = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "_capture_heartbeat.json"

# Sports that have BOTH a KX<league>GAME/MATCH in-play series (W2) and a predict_live
# model. tennis (KXATPMATCH/KXWTAMATCH, wired WAKE-34) and wnba (KXWNBAGAME, wired
# wave 1) ADDED 2026-07-03 -- kalshi_series_spec.SERIES_SPEC already carries both (see
# scripts/platformkit/odds_provider/kalshi_series_spec.py); this was the only place
# still gating them out of capture. tennis_outcome_resolver now supplies the outcome
# label tennis previously had no way to grade. Additive: mlb/soccer_intl unchanged.
# A running daemon only picks this up at its already-pending restart.
#
# npb/kbo ADDED 2026-07-06 (LANE 3, CAPTURE-ONLY): kalshi_series_spec.SERIES_SPEC
# already carries KXNPBGAME/KXKBOGAME (verified live 2026-07-04) so this was again
# the only remaining gate. NEITHER sport has a predict_live model wired into
# live_board.live_model_home_prob (_default_model_fn's only production caller) --
# that function's dispatch has no npb/kbo branch, so model_fn(sport, state) returns
# None for every npb/kbo tick (see _default_model_fn / live_model_home_prob), which
# _process_game's "row['reason'] = 'no_model_prob'; return row" honors as a clean,
# poison-safe skip: NO placement, NO on_tick call, NO paper bet -- ticks + venue
# prices still accrue every restart via the fetch+legs+deep-state path so the tail
# gates + grading-multi corpus start filling from the moment of restart. This is
# CORRECT and DELIBERATE (no live model exists yet), mirroring the same None-safe
# convention ingame_sp_shadow.py documents for its shadow probe.
# nba ADDED (live-board-nba-branch lane): live_board.live_model_home_prob now has an nba
# branch (domains/basketball_nba/ingame_shadow's predictor served for real), so nba ticks
# reach book pairing + on_tick/capture_pair_once instead of the permanent no_model_prob
# early exit. model_prob_nba_shadow (this same predictor, kept as the shadow field) becomes
# a byte-identical duplicate of model_prob for nba from this wave forward -- both stay
# wired; the shadow column is now redundant-but-harmless, not removed here.
DEFAULT_SPORTS: List[str] = ["mlb", "soccer_intl", "tennis", "wnba", "npb", "kbo", "nba"]

# Sports with a REAL live in-game model wired (_default_model_fn -> live_board.
# live_model_home_prob's actual dispatch) -- these are the only sports whose tick can
# reach a placement decision; tennis/wnba/npb/kbo are capture-only (always
# reason="no_model_prob"). Order = processing priority (mlb pinned first, per season).
_MODEL_SPORTS: Tuple[str, ...] = ("mlb", "soccer_intl", "nba")


def _priority_sports(sport_list: List[str],
                     pos_map: Dict[str, Dict[str, Any]]) -> List[str]:
    """Stable-reorder *sport_list* so decision-relevant sports process first this tick.

    Priority (highest first): (1) a sport with an OPEN paper position (needs its exit
    check every tick), (2) a sport with a live model wired (_MODEL_SPORTS, mlb first),
    (3) everything else, in its original relative order (stable sort). Pure; never
    raises -- an unreadable pos_map key is simply not counted as an open position."""
    open_sports = set()
    for k, v in pos_map.items():
        if v:
            open_sports.add(str(k).split("/", 1)[0])

    def _key(s: str) -> Tuple[int, int]:
        sl = str(s).lower()
        has_pos = 0 if sl in open_sports else 1
        model_rank = _MODEL_SPORTS.index(sl) if sl in _MODEL_SPORTS else len(_MODEL_SPORTS)
        return (has_pos, model_rank)

    return sorted(sport_list, key=_key)

# RELAXED in-game EV floor per sport (opt-in): the strict pre-registered floor (policy tier C
# = +0.02 EV, +0.01 proxy = +0.03) rarely fires in-game because the calibrated model tracks
# an efficient market. A lower floor surfaces genuine smaller divergences (e.g. right after a
# goal, before the market fully re-prices) as LOWER-CONFIDENCE, honestly-CLV-graded paper
# bets -- NOT an edge claim. None/absent -> strict floor. Soccer/WC = +1% EV.
# Opt-in relaxed in-game EV floor per sport (paper/measurement; CLV grades the truth, never
# a $ edge claim). In-game model-vs-market divergences are small, so the strict pre-registered
# +2%/+3% policy floor rejects almost everything -> the channel placed ~nothing. A modest
# relaxed floor surfaces the marginal in-game edges (tier C) so the CLV corpus actually fills.
# MLB added 2026-06-29 (was soccer-only) so in-game places across sports, not just the WC.
_INGAME_RELAXED_EV_FLOOR: Dict[str, float] = {
    "soccer_intl": 0.01, "soccer": 0.01, "mlb": 0.01,
    # wnba ADDED 2026-07-19 (evidence-throughput lever, same declared rationale
    # as mlb/soccer above): the walk-forward-validated WNBA blend serves live,
    # but the strict floor almost never fired -> the paper CLV corpus could not
    # fill. PAPER measurement only; the breaker + divergence gate bound it.
    "wnba": 0.01}

# Phase-aware cadence (seconds): poll fast while in-play games are live, slow when quiet.
LIVE_INTERVAL_SEC = 20.0
IDLE_INTERVAL_SEC = 120.0

# ENV-TUNABLE live cadence (default stays LIVE_INTERVAL_SEC=20 -- a tunable, not a flip).
# Governor math (kalshi_rate_governor DEFAULT_RATE_SHARES["capture"]=0.35 * BASE_RPS=15
# = 5.25 tokens/sec): the widest current slate (DEFAULT_SPORTS' 19 series requests/cycle,
# kalshi_series_spec.SERIES_SPEC) demands ~0.95 req/s at the 20s default and ~1.9 req/s at
# a 10s cadence -- both well under the capture caller's own 5.25 tok/s share (10s uses
# ~36%), so CV_INPLAY_LIVE_INTERVAL=10 is arithmetically safe to opt into without
# starving the governor's other callers or tripping its own bucket.
_ENV_LIVE_INTERVAL = "CV_INPLAY_LIVE_INTERVAL"


def _live_interval_sec() -> float:
    """LIVE_INTERVAL_SEC, overridable via the CV_INPLAY_LIVE_INTERVAL env var (seconds).
    Absent/invalid/non-positive -> the unchanged 20.0 default. Never raises."""
    raw = os.environ.get(_ENV_LIVE_INTERVAL, "")
    try:
        v = float(raw)
        return v if v > 0 else LIVE_INTERVAL_SEC
    except (TypeError, ValueError):
        return LIVE_INTERVAL_SEC


def _idle_interval_sec() -> float:
    """IDLE_INTERVAL_SEC, overridable via CV_INPLAY_IDLE_INTERVAL (seconds) --
    bounds how late the loop notices a slate going live. Same contract as
    _live_interval_sec: absent/invalid/non-positive -> unchanged 120s default."""
    raw = os.environ.get("CV_INPLAY_IDLE_INTERVAL", "")
    try:
        v = float(raw)
        return v if v > 0 else IDLE_INTERVAL_SEC
    except (TypeError, ValueError):
        return IDLE_INTERVAL_SEC

# LANE 4b (depth capture, OPTIONAL, OFF by default): order-book depth changes far more
# slowly than top-of-book price, so the hook fires only every Nth tick instead of every
# tick. At the live cadence (20s) this is ~5 minutes; at idle cadence (120s) it is ~30
# minutes -- both acceptable since depth is a slow-moving accrual asset, not a decision
# input. Ticks-based (not wall-clock) so the bounded/injected-clock test path stays
# deterministic (no real time.time() dependency).
DEPTH_CAPTURE_EVERY_N_TICKS = 15

# Injectable callbacks (all default to the real chains; tests inject offline stubs so the
# tested path needs NO network / NO predictor corpus / NO venue):
#   live_state_fn(sport, gid) -> dict | None   (ingame_live_state.live_state; p0 auto-supplied)
#   model_fn(sport, state)    -> float | None  (predict_live P(home win) as-of this tick)
#   inplay_fetch_fn(sport, stats=None) -> [tick,...] (inplay_kalshi.fetch_inplay liquid YES
#                                        ticks; the optional 2nd positional/keyword *stats*
#                                        dict is LANE 1's request/429 counter passthrough --
#                                        a 1-arg test stub is still accepted, see _call_fetch)
#   finals_fn(sport)          -> [game,...]    (settled_finals.settled_since-style FINAL games)
LiveStateFn = Callable[[str, str], Optional[Dict[str, Any]]]
ModelFn = Callable[[str, Dict[str, Any]], Optional[float]]
InplayFetchFn = Callable[..., List[Dict[str, Any]]]
FinalsFn = Callable[[str], List[Dict[str, Any]]]
# LANE 4b: DepthCaptureFn(sports) -> summary dict (odds_provider.depth_capture.run_capture_pass
# shape). OPTIONAL -- default None means the hook never fires (zero behavior change).
DepthCaptureFn = Callable[[List[str]], Dict[str, Any]]


def _call_fetch(fetch_fn: InplayFetchFn, sport: str,
                stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Call *fetch_fn* passing the per-cycle *stats* dict if it accepts one.

    LANE 1: existing/test fetch stubs are 1-arg (sport only) -- calling them with
    a stats kwarg would TypeError. We try the 2-arg form first (production
    _default_inplay_fetch and any pacing-aware stub) and fall back to the legacy
    1-arg call on a TypeError, so every existing injected fetch_fn in the test
    suite keeps working unmodified. Never raises past this: any other exception
    propagates to poll_once's own per-sport try/except (unchanged behavior).
    """
    try:
        return fetch_fn(sport, stats=stats)
    except TypeError:
        return fetch_fn(sport)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prob01(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _default_inplay_fetch(sport: str, stats: Optional[Dict[str, Any]] = None
                          ) -> List[Dict[str, Any]]:
    """Default production fetch: inplay_kalshi.fetch_inplay (W2 per-game series). [] on error.

    *stats*, if given, is passed straight through to fetch_inplay's own *stats*
    param (LANE 1) so the caller can aggregate n_requests/n_429 across sports for
    the heartbeat. Explicitly opts IN to fetch_inplay's inter-series pacing
    (stagger_sec=REQUEST_STAGGER_SEC) -- fetch_inplay itself defaults stagger_sec
    to 0.0 (no pacing) so every OTHER caller/test is unaffected; only THIS
    production default fetcher (the real 6-sport/17-series fan-out) drips its
    requests instead of bursting them. Also passes governor_caller="capture" (the
    kalshi_rate_governor config-only identity for this daemon's fair rate share,
    distinct from inplay_snapshot_daemon's default "snapshot" share) so the two
    daemons' cross-process token buckets stay apportioned per
    kalshi_rate_governor.DEFAULT_RATE_SHARES.
    """
    try:
        from scripts.platformkit.odds_provider import inplay_kalshi as _ik
        if stats is not None:
            return list(_ik.fetch_inplay(sport, stats=stats,
                                          stagger_sec=_ik.REQUEST_STAGGER_SEC,
                                          governor_caller="capture"))
        return list(_ik.fetch_inplay(sport, stagger_sec=_ik.REQUEST_STAGGER_SEC,
                                      governor_caller="capture"))
    except Exception as exc:  # noqa: BLE001 -- a feed error is never fatal
        logger.warning("inplay_capture_loop fetch failed sport=%s: %s", sport, exc)
        return []


def _default_depth_capture(sports: List[str]) -> Dict[str, Any]:
    """Default LANE 4b depth capture: odds_provider.depth_capture.run_capture_pass.

    DATA CAPTURE ONLY (no model, no gate, no edge framing) -- snapshots the full Kalshi
    order-book ladder per sport to data/cache/depth_history/<sport>/<date>.jsonl. Bounded
    per-sport (max_tickers_per_sport) so one slate can never balloon this tick's cost.
    Never raises past this wrapper: any failure is caught by the caller (_maybe_capture_depth)
    too, but this local guard keeps the failure mode identical to the other _default_* fetchers
    in this file (log + empty summary, never propagate).
    """
    try:
        from scripts.platformkit.odds_provider import depth_capture as _dc
        return _dc.run_capture_pass(list(sports), max_tickers_per_sport=50)
    except Exception as exc:  # noqa: BLE001 -- depth capture must never affect the host cycle
        logger.warning("inplay_capture_loop depth_capture failed: %s", exc)
        return {}


def _default_finals(sport: str) -> List[Dict[str, Any]]:
    """Default FINAL-games provider: settled_finals.settled_since (carries home/away)."""
    try:
        from scripts.platformkit.ingame import settled_finals as _sf
        return list(_sf.settled_since(sport))
    except Exception as exc:  # noqa: BLE001 -- a dead feed -> no finals, never a crash
        logger.warning("inplay_capture_loop finals failed sport=%s: %s", sport, exc)
        return []


def _default_model_fn(sport: str, state: Dict[str, Any]) -> Optional[float]:
    """Default model: route predict_live through live_board's resolved predictor chain.

    READ-only on domains/<sport>/predictor.py. Returns P(home win) as-of this tick or None.
    The live in-game number this produces carries the pregame prior because the repricer is
    anchored to it (coherence) AND state['p0'] is the leak-free P1 prior. Network/corpus
    only here -- the tested path injects a stub instead.
    """
    try:  # pragma: no cover -- exercised only in the live smoke, never in the offline test
        from scripts.platformkit.frontend import live_board as _lb
        return _prob01(_lb.live_model_home_prob(sport, state))  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 -- no live model wired -> skip the pair cleanly
        logger.debug("inplay_capture_loop model_fn(%s) unavailable: %s", sport, exc)
        return None


def _yes_pair(ticks: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Group liquid Kalshi MONEYLINE ticks by game_id -> {home_yes, away_yes} implied probs.

    Each liquid moneyline tick is one team's YES(win) prob; we pair the two team markets of
    a game. The home/away label comes from the daemon's state match (the caller knows the
    home team), so here we just keep BOTH sides keyed by their side label tail for the caller
    to align. We return up to two probs per game; a single-sided game keeps just the one (the
    devig fills the complement). Never raises.

    MARKET_TYPE FILTER (binding): inplay_kalshi.fetch_inplay now ALSO returns total/spread/
    team_total ticks whose "prob" is P(over line) / P(covers), never a team win-prob. Mixing
    those into this win-prob pairing would silently corrupt model_prob-vs-price grading (the
    devig, the CLV ledger, the tail gate all assume a win-prob pair) -- so every row here is
    filtered to market_type=="moneyline" before pairing. A row missing market_type (older
    cached shape) is treated as moneyline for back-compat.
    """
    by_game: Dict[str, Dict[str, float]] = {}
    for t in ticks:
        if not isinstance(t, dict):
            continue
        mt = t.get("market_type")
        if mt is not None and str(mt) != "moneyline":
            continue
        gid = str(t.get("game_id") or "")
        p = _prob01(t.get("prob"))
        if not gid or p is None:
            continue
        slot = by_game.setdefault(gid, {})
        # Keep the first two distinct legs; the daemon aligns home/away via team names.
        side = str(t.get("side") or "yes")
        slot[side] = p
    return by_game


def _align_home_yes(home_name: str, away_name: str,
                    legs: Dict[str, float]) -> Optional[Dict[str, Optional[float]]]:
    """Pick the YES(home) / YES(away) implied probs from a game's liquid legs by team name.

    Matches each side label (e.g. 'NYY', 'Yankees') against the home / away abbreviation or
    name (case-insensitive substring, either direction). Returns {'yes_home','yes_away'} with
    yes_away possibly None (the devig fills the complement). None if neither leg matches home
    (we never guess the home side -- a misaligned pair manufactures fake CLV).
    """
    hn, an = home_name.strip().lower(), away_name.strip().lower()
    yes_home = yes_away = None
    for label, prob in legs.items():
        lab = str(label).strip().lower()
        if hn and (hn in lab or lab in hn):
            yes_home = prob
        elif an and (an in lab or lab in an):
            yes_away = prob
    if yes_home is None:
        return None
    return {"yes_home": yes_home, "yes_away": yes_away}


def _team_in_legs(team: str, legs: Dict[str, float]) -> bool:
    """True iff a team name aligns with some leg label (case-insensitive, either direction)."""
    t = str(team or "").strip().lower()
    if not t:
        return False
    return any(t in str(lab).strip().lower() or str(lab).strip().lower() in t
               for lab in legs)


def _ts_by_game(ticks: List[Dict[str, Any]]) -> Dict[str, str]:
    """Each game_id -> the ts of its OWN moneyline tick (first one seen), mirroring
    _yes_pair's per-game grouping + market_type filter.

    LATENCY/HONESTY FIX (signal-to-placement latency cut): poll_once used to stamp
    signal_ts from ticks[0] -- a single SPORT-WIDE value -- for every game that sport
    polled this tick, even after inplay_kalshi.fetch_inplay started stamping each
    series' ticks at their own real HTTP-response time (see inplay_kalshi.
    _fetch_one_series). Reusing an unrelated (possibly earlier-fetched) game/series'
    ts inflated placement_latency_ms for every game but the first. This gives each
    game its OWN observed-price ts instead. Measurement field only -- never touches
    a decision. Never raises."""
    out: Dict[str, str] = {}
    for t in ticks:
        if not isinstance(t, dict):
            continue
        mt = t.get("market_type")
        if mt is not None and str(mt) != "moneyline":
            continue
        gid = str(t.get("game_id") or "")
        ts = t.get("ts")
        if gid and ts and gid not in out:
            out[gid] = ts
    return out


def _src_ts_by_game(ticks: List[Dict[str, Any]]) -> Dict[str, str]:
    """Explicit venue quote clocks only; no capture-clock fallback."""
    out: Dict[str, str] = {}
    for t in ticks:
        if not isinstance(t, dict) or t.get("market_type") not in (None, "moneyline"):
            continue
        gid, value = str(t.get("game_id") or ""), t.get("src_ts")
        if gid and isinstance(value, str) and value and gid not in out:
            out[gid] = value
    return out


def _gumbo_event_ts(state: Dict[str, Any]) -> Optional[str]:
    """Latest MLB metaData.timeStamp from the GUMBO sidecar for this resolved game."""
    game_pk = state.get("game_pk")
    if game_pk is None:
        return None
    path = _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live" / ("%s.jsonl" % game_pk)
    try:
        import json
        last = next((json.loads(line) for line in reversed(path.read_text(encoding="utf-8").splitlines())
                     if line.strip()), {})
        value = last.get("ts") if isinstance(last, dict) else None
        return value if isinstance(value, str) and value else None
    except (OSError, ValueError):
        return None


def _cached_live_states(sport: str, cache: Optional[Dict[str, List[Dict[str, Any]]]]
                        ) -> Optional[List[Dict[str, Any]]]:
    """Lazily fetch+memoize _ls.live_states(sport) ONCE per sport per poll_once cycle.

    LATENCY FIX (biggest single win in this lane): _scan_live_by_legs previously called
    _ls.live_states(sport) -- a FULL ESPN scoreboard fetch -- for EVERY live game of a
    sport, every tick (on top of the ALSO-wasted per-game ls_fn(sport, gid) lookup,
    which misses by construction since gid is a Kalshi ticker, not an ESPN id -- see
    _scan_live_by_legs' own docstring). For a sport with N live games that is 2N serial
    ESPN round trips per tick. Caching the scan ONCE per sport (shared across that
    sport's games THIS tick) cuts it to N+1. *cache* is None -> old behavior (direct
    fetch every call, e.g. any caller that does not opt in); a caching caller passes
    the SAME dict across a poll_once cycle's games. Never raises: a fetch failure
    memoizes [] (matches _ls.live_states' own fail-open [] contract) so a bad sport
    doesn't retry-storm the feed for its remaining games this tick.
    """
    if cache is None:
        try:
            return _ls.live_states(sport)
        except Exception:  # noqa: BLE001 -- no cache path degrades to old direct-fetch safety
            return []
    if sport not in cache:
        try:
            cache[sport] = _ls.live_states(sport)
        except Exception:  # noqa: BLE001 -- a scan failure memoizes empty, never retried this tick
            cache[sport] = []
    return cache[sport]


def _scan_live_by_legs(sport: str, legs: Dict[str, float],
                       gid: Optional[str] = None,
                       nowdt: Optional[datetime] = None,
                       states: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Bridge a Kalshi-keyed game to its ESPN live state by TEAM.

    The capture loop keys games by their Kalshi ticker (e.g. KXWCGAME-26JUN22ARGAUT), which
    never equals the ESPN numeric event id -> live_state(sport, ticker) always misses. This
    scans every in-progress ESPN game and returns the one whose BOTH teams align with the
    legs' team-name labels. BOTH must match: a single shared team (e.g. a live ARG-AUT vs a
    future JOR-ARG market) would otherwise mis-bind two different games. No full match ->
    None (the caller skips; a misaligned pair manufactures fake CLV). Never raises.

    DATE GUARD (reject-only, mirrors pm_game_date_guard): an MLB series plays the SAME two
    teams on consecutive days, so team-only matching alone binds TONIGHT's live game to a
    market ticketed for TOMORROW too (confirmed live 2026-07-10: KXMLBGAME-26JUL111605MILPIT
    captured today's live MIL@PIT state against tomorrow's pregame price -- same for
    KXMLBGAME-26JUL111610BOSNYM). gid's own ET ticker date must be today or yesterday
    (yesterday allowed for a game still live just after ET midnight); a ticker dated
    tomorrow-or-later is rejected before the scan even runs. An unparseable/absent gid is
    honest no-info -- the guard is a no-op and behavior is unchanged.

    *states*: an optional pre-fetched _ls.live_states(sport) list (see
    _cached_live_states) -- the caller supplies this so N games in the same sport/tick
    share ONE ESPN scoreboard fetch instead of each triggering its own. None (default,
    every existing/test call site) -> fetches live directly, byte-identical to before.
    """
    try:
        game_date = _ticker_game_date(gid)
        if game_date is not None:
            today = date.fromisoformat(_now_et_day(nowdt))
            if game_date not in (today, today - timedelta(days=1)):
                return None
        for st in (states if states is not None else _ls.live_states(sport)):
            if not isinstance(st, dict):
                continue
            home = str(st.get("home_display") or st.get("home") or "")
            away = str(st.get("away_display") or st.get("away") or "")
            if _team_in_legs(home, legs) and _team_in_legs(away, legs):
                return st
    except Exception as exc:  # noqa: BLE001 -- a scan error is no match, never a crash
        logger.debug("inplay_capture_loop scan-by-legs(%s) failed: %s", sport, exc)
    return None


def _draw_leg(legs: Dict[str, float]) -> Optional[float]:
    """The draw/tie leg prob of a 3-way (soccer) market, or None for a 2-way market."""
    for label, prob in legs.items():
        lab = str(label).strip().lower()
        if lab in ("tie", "draw", "x") or "draw" in lab or "tie" in lab:
            return _prob01(prob)
    return None


def _fold_draw_into_field(pair: Dict[str, Optional[float]],
                          legs: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Soccer is 3-way (home/draw/away); the day-trader prices a 2-way home-WIN binary.

    Fold the draw leg into the not-home complement so yes_home + yes_field has a real
    overround and the 2-way devig yields the correct fair P(home win) = home/(home+draw+
    away). A 2-way market (no draw leg) is unchanged. Never raises."""
    draw = _draw_leg(legs)
    if draw is None:
        return pair
    yes_away = (pair.get("yes_away") or 0.0) + draw
    return {"yes_home": pair.get("yes_home"), "yes_away": yes_away}


def _build_tick(state: Dict[str, Any], model_p: float,
                pair: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Assemble the LiveTick the day-trader's on_tick consumes (UNITS only, no $).

    calibration_justified=True iff the live state carries the PROVEN prior (p0_source in
    {CALLER, PRIOR, PRIOR_TEAMS}) -- PRIOR_TEAMS is the SAME leak-free pregame prior, resolved
    by a unique team match when the live/snapshot ids differ. A BASE-fallback (no pregame
    snapshot) lean is NOT prior-justified, so it is captured for the grade series but NEVER
    traded. is_liquid=True (the price came from the is_liquid-gated fetch). model_prob is
    as-of this tick (leak-free).
    """
    p0_src = str(state.get("p0_source") or "")
    return {
        "model_prob": model_p,
        "yes_home_prob": pair.get("yes_home"),
        "yes_away_prob": pair.get("yes_away"),
        "calibration_justified": p0_src in ("CALLER", "PRIOR", "PRIOR_TEAMS"),
        "is_liquid": True,   # the price already cleared inplay_kalshi.is_liquid upstream
        "is_fresh": True,    # in-play ticks are fresh by construction; stale feeds emit []
        "clv_is_proxy": True,
        # opt-in relaxed floor for this sport (None -> strict policy floor in evaluate),
        # routed through the CROSS-CORPUS segment-trust gate: a segment PROVEN worse than
        # the venue price across independent corpora reverts to the strict floor (suppress
        # its marginal relaxed bets); trusted/neutral/unknown keep the relaxed floor. The
        # gate acts ONLY on replicated proof and is reversible (CV_INGAME_SEGMENT_TRUST=0),
        # so thin/unreplicated data changes nothing -- do-no-harm.
        "min_ev_floor": _segment_trust.floor_for_segment(
            str(state.get("sport") or "").lower(), state,
            _INGAME_RELAXED_EV_FLOOR.get(str(state.get("sport") or "").lower())),
        # Pass the FULL resolved state through to the grade row's state_summary: the score,
        # the segment fields (inning/half/period/minute/clock) AND the DEEP MLB base-out
        # (outs/base/bos/re/count, game_pk) the resolver merges in.  The old 7-key projection
        # dropped all of these -> every captured tick logged a bare "live".  These keys feed
        # ONLY live_grade._state_summary (the label); model/price/sizing read top-level tick
        # fields, so widening this is label-only and cannot change a decision.
        # score_home/score_away/base_state ADDED (kbo-alias-wire-soak lane): the KBO relay
        # wire's own field names for score/base-occupancy -- label-only, same discipline.
        "state": {k: state.get(k) for k in (
            "home", "away", "state_diff", "frac_elapsed", "status", "p0", "p0_source",
            "home_score", "away_score", "inning", "half", "period", "minute", "clock",
            "outs", "base", "bos", "re", "count", "pitch_count", "tto",
            "game_pk", "score_home", "score_away", "base_state") if k in state},
    }


def _maybe_capture_depth(depth_capture_fn: Optional[DepthCaptureFn], sports: List[str],
                         tick_counter: Optional[Dict[str, int]]) -> Optional[Dict[str, Any]]:
    """LANE 4b: fire *depth_capture_fn* at most once every DEPTH_CAPTURE_EVERY_N_TICKS ticks.

    OPTIONAL + FAIL-OPEN (binding rail): depth_capture_fn is None by default -> this is a
    no-op every call (zero behavior change to the existing price-pairing cadence). When a
    fn IS supplied, *tick_counter* (threaded by the caller across ticks, mirrors how
    *positions* is threaded) counts calls; the capture only actually fires on tick 1 and
    every Nth tick after, so depth's slower cadence never rides every fast live tick. ANY
    exception from depth_capture_fn -- import error, network failure, bad return shape -- is
    caught here and converted to a logged None: the host cycle (live pairing, paper
    decisions, settlement) must NEVER see or propagate a depth-capture failure. Returns the
    capture summary dict on a tick where it fired, else None (including on failure)."""
    if depth_capture_fn is None:
        return None
    counter = tick_counter if tick_counter is not None else {}
    n = counter.get("n", 0)
    counter["n"] = n + 1
    if n % DEPTH_CAPTURE_EVERY_N_TICKS != 0:
        return None
    try:
        return depth_capture_fn(sports)
    except Exception as exc:  # noqa: BLE001 -- depth capture must NEVER break the host cycle
        logger.warning("inplay_capture_loop depth_capture_fn failed (host cycle unaffected): %s", exc)
        return None


def poll_once(*, sports: Optional[List[str]] = None,
              live_state_fn: Optional[LiveStateFn] = None,
              model_fn: Optional[ModelFn] = None,
              inplay_fetch_fn: Optional[InplayFetchFn] = None,
              finals_fn: Optional[FinalsFn] = None,
              deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
              kbo_deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
              depth_capture_fn: Optional[DepthCaptureFn] = None,
              depth_tick_counter: Optional[Dict[str, int]] = None,
              grade_dir: Optional[Path] = None,
              ledger_path: Optional[Path] = None,
              heartbeat_path: Optional[Path] = None,
              positions: Optional[Dict[str, Dict[str, Any]]] = None,
              now: Optional[datetime] = None) -> Dict[str, Any]:
    """ONE measurement tick across *sports*: capture pairs, paper-decide, stamp finals.

    Reuses the existing chain end-to-end via injectable callbacks (default to the real ones).
    *positions* threads each game's open paper position across ticks (None -> fresh). Returns
    a heartbeat dict and writes it to disk (stale-never-green). UNITS only -- no $. Never raises.

    *kbo_deep_state_fn* (optional, mirrors *deep_state_fn*'s MLB-only role): a (kalshi_
    ticker)->dict enricher dispatched ONLY for sport=="kbo", chaining the ticker through
    kbo_capture_wire's alias->matcher->relay bridge to a descriptive as-of state row
    (inning/half/outs/base/score/count) -- NO model probability, NO dispatch change. None
    (default) -> zero behavior change (kbo ticks are captured exactly as before this
    wiring; the sport was already gated to "no_model_prob" upstream of this hook, so a
    missing/failing enricher can never remove a previously-working KBO capture path).
    """
    sport_list = list(sports) if sports else list(DEFAULT_SPORTS)
    ls_fn = live_state_fn or (lambda s, g: _ls.live_state(s, g))
    md_fn = model_fn or _default_model_fn
    fetch_fn = inplay_fetch_fn or _default_inplay_fetch
    fin_fn = finals_fn or _default_finals
    pos_map = positions if positions is not None else {}
    # LATENCY (decision-relevant sports first): within one poll_once cycle, sports are
    # processed serially (fetch -> per-game live-state/model/decide), so a sport late in
    # sport_list waits behind every earlier sport's full processing. A sport with an open
    # paper position (needs its exit check) or a live in-game model (mlb/soccer_intl/nba
    # -- the sports whose ticks can actually reach a placement decision, per
    # _default_model_fn's real dispatch) is decision-relevant; capture-only sports
    # (tennis/wnba/npb/kbo -- no model wired yet, always reason=no_model_prob) are not.
    # Reordering here changes only WHEN a sport is processed this tick, never what price/
    # model/decision it gets -- additive, zero change to any single game's outcome.
    sport_list = _priority_sports(sport_list, pos_map)
    nowdt = now or datetime.now(timezone.utc)
    cycle_start = time.monotonic()

    n_live = n_pairs = n_bets = n_settled = 0
    games_seen: List[Dict[str, Any]] = []
    # GRADE-WRITE LAG counters (LANE 2, wave-14 fix): every game with a liquid
    # moneyline leg this tick is a candidate grade-write; if _process_game did NOT
    # capture a pair, bucket it by reason so the freshness SLA can see per-game
    # grade-write lag distinctly from a genuinely dead/illiquid game (which never
    # appears in legs_by_game at all -- that case has no row here, by construction).
    grade_write_fail_by_reason: Dict[str, int] = {}
    grade_write_fail_games: List[Dict[str, Any]] = []
    # KALSHI PACING counters (LANE 1, wave-16 fix): aggregated across every sport's
    # fetch this cycle so an ops SLA can see request volume + throttle frequency
    # instead of a silent [] indistinguishable from a dead feed (see
    # inplay_kalshi.kalshi_pacing for the mechanics this counts).
    n_requests_total = n_429_total = 0

    for sport in sport_list:
        sport_stats: Dict[str, Any] = {}
        try:
            ticks = _call_fetch(fetch_fn, sport, sport_stats)
        except Exception as exc:  # noqa: BLE001 -- a feed error never sinks the tick
            logger.warning("inplay_capture_loop fetch error %s: %s", sport, exc)
            ticks = []
        n_requests_total += int(sport_stats.get("n_requests", 0))
        n_429_total += int(sport_stats.get("n_429", 0))
        # Batch ts fallback only (rare: a game with a liquid leg carrying no ts at all).
        # PER-GAME ts is the normal path now (_ts_by_game) -- see its docstring: each
        # game gets ITS OWN tick's ts (in turn each series' ts is stamped at ITS OWN
        # HTTP response time by inplay_kalshi._fetch_one_series), not one sport-wide
        # batch value shared by every game this sport polls this tick.
        batch_ts = ticks[0].get("ts") if ticks else None
        ticks_list = list(ticks) if ticks else []
        legs_by_game = _yes_pair(ticks_list)
        ts_by_game = _ts_by_game(ticks_list)
        src_ts_by_game = _src_ts_by_game(ticks_list)
        # DEEP enrichment: MLB gets the base-out resolver, KBO (capture-only, wave
        # kbo-alias-wire-soak) gets the relay state-row bridge; other sports pass through.
        sport_deep_fn = deep_state_fn if str(sport).lower() == "mlb" else (
            kbo_deep_state_fn if str(sport).lower() == "kbo" else None)
        # One ESPN team-bridge scan cache per sport per tick, shared by every game of
        # this sport below (see _cached_live_states) -- was previously one fetch PER GAME.
        live_states_cache: Dict[str, List[Dict[str, Any]]] = {}
        for gid, legs in legs_by_game.items():
            row = _process_game(sport, gid, legs, ls_fn, md_fn, pos_map,
                                grade_dir, ledger_path, nowdt, sport_deep_fn,
                                ts_by_game.get(gid, batch_ts), src_ts_by_game.get(gid),
                                live_states_cache)
            games_seen.append(row)
            if row.get("paired"):
                n_live += 1
                n_pairs += 1
            else:
                # A liquid moneyline leg existed this tick (the game IS live per the
                # venue) but no grade row was written -- this is exactly the wave-14
                # class of stall (per-game grade-write lag), isolated per tick: the
                # roster is rebuilt fresh from legs_by_game every poll_once call, so
                # a failure here NEVER permanently removes the game -- next tick
                # retries unconditionally. Counted here purely for observability.
                reason = str(row.get("reason") or "unknown")
                grade_write_fail_by_reason[reason] = grade_write_fail_by_reason.get(reason, 0) + 1
                grade_write_fail_games.append({
                    "sport": sport, "game_id": gid, "reason": reason})
            if row.get("bet"):
                n_bets += 1
        # FINAL stamps (W3): append the held-out home_win label so the OUTCOME arm can fire.
        try:
            finals = fin_fn(sport)
        except Exception as exc:  # noqa: BLE001 -- finals failure never sinks the tick
            logger.warning("inplay_capture_loop finals error %s: %s", sport, exc)
            finals = []
        for g in finals or []:
            if _stamp_final(sport, g, grade_dir, nowdt):
                n_settled += 1

    # LANE 4b: OPTIONAL, FAIL-OPEN depth-capture hook, fired at most once per cycle across
    # ALL sports (not per-sport, since depth_capture_fn itself fans out internally). None by
    # default (depth_capture_fn=None) -> zero behavior change to every existing call site
    # that doesn't pass it. See _maybe_capture_depth for the cadence-throttle + exception
    # discipline; a failure here can NEVER surface as a poll_once exception or missing
    # heartbeat -- it degrades to depth_capture=None on the heartbeat, same as any other
    # skipped-this-tick measurement.
    depth_summary = _maybe_capture_depth(depth_capture_fn, sport_list, depth_tick_counter)

    heartbeat = {
        "as_of": _utc_iso(), "sports": sport_list, "n_live": n_live,
        "n_pairs": n_pairs, "n_bets": n_bets, "n_settled": n_settled,
        "games": games_seen, "measurement_only": True, "executed": False,
        "edge_claimed": False, "units": "probability",
        # GRADE-WRITE LAG (LANE 2): per-tick counter of live-but-unpaired games, by
        # reason (e.g. "no_model_prob", "no_home_leg", "error:<ExcType>"). n_live/
        # n_pairs already tell you the aggregate; this tells you WHY a specific live
        # game's grade write is lagging so an ops SLA can page on a persistent count
        # for one game_id across ticks, distinct from ordinary per-tick noise.
        "grade_write_fail_by_reason": grade_write_fail_by_reason,
        "grade_write_fail_games": grade_write_fail_games,
        # KALSHI PACING (LANE 1, wave-16 fix): n_requests_total is the total Kalshi
        # /markets series calls this cycle made (across every sport); n_429_total
        # is how many of those hit a 429. cycle_duration_sec is this poll_once
        # call's own wall-clock cost -- an ops SLA can page when it approaches or
        # exceeds LIVE_INTERVAL_SEC (the cadence this cycle is meant to fit in),
        # which is the exact failure mode a 429 storm produced (n_live=0 cycles
        # were previously indistinguishable from a genuinely dead feed).
        "n_requests_total": n_requests_total,
        "n_429_total": n_429_total,
        "cycle_duration_sec": round(time.monotonic() - cycle_start, 3),
        # LANE 4b: None on every tick where the (optional, off-by-default) depth hook did
        # not fire or was never supplied -- never fabricated, so "no depth this tick" is
        # always visibly distinct from "depth capture ran and wrote 0 rows".
        "depth_capture": depth_summary,
        "_honest_note": (
            "In-play capture daemon heartbeat. Captures (model,devigged-price) pairs + paper "
            "UNIT decisions + settle labels; NO real money, NO flag flip, NO autostart. A down "
            "feed yields zero live games, never a fabricated one. CLV/outcome graded downstream."
        ),
    }
    _write_heartbeat(heartbeat, heartbeat_path)
    # LANE 2 (durable shadow-evidence store): the heartbeat above is OVERWRITTEN every
    # cycle, so a promotion decision needs an APPEND history of the 4 shadow fields
    # instead. Fail-open (mirrors every other measurement hook in this file): an
    # exception inside shadow_history can never sink this cycle's heartbeat write,
    # which has already happened by this point. history_dir is derived from
    # *heartbeat_path*'s own parent when the caller supplied one (every existing/test
    # call site already does, mirroring grade_dir's own tmp_path convention) so an
    # injected tmp heartbeat_path automatically isolates shadow history too -- a test
    # that never touches shadow_history at all still can't leak rows into the real
    # data/cache/ingame_shadow_history/ path. Only a caller that leaves BOTH
    # heartbeat_path and history_dir at their defaults (i.e. real production) reaches
    # the real DEFAULT_HISTORY_DIR.
    try:
        from scripts.platformkit.ingame import shadow_history as _sh
        hist_dir = (Path(heartbeat_path).parent / "ingame_shadow_history"
                   if heartbeat_path is not None else None)
        _sh.append_shadow_rows(games_seen, now=nowdt, history_dir=hist_dir)
    except Exception as exc:  # noqa: BLE001 -- shadow history is observability, not critical
        logger.warning("inplay_capture_loop shadow_history append failed: %s", exc)
    return heartbeat


def _process_game(sport: str, gid: str, legs: Dict[str, float],
                  ls_fn: LiveStateFn, md_fn: ModelFn,
                  pos_map: Dict[str, Dict[str, Any]],
                  grade_dir: Optional[Path], ledger_path: Optional[Path],
                  nowdt: datetime,
                  deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
                  signal_ts: Optional[str] = None,
                  src_ts: Optional[str] = None,
                  live_states_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
                  ) -> Dict[str, Any]:
    """Capture + paper-decide ONE live game's tick. Per-game guarded: never raises.

    *live_states_cache*: threaded from poll_once, shared across every game of THIS
    sport/tick, so the team-name ESPN bridge scan (_scan_live_by_legs) fires at most
    ONCE per sport per tick instead of once per game (see _cached_live_states)."""
    row: Dict[str, Any] = {"sport": sport, "game_id": gid, "paired": False,
                           "bet": False, "reason": ""}
    try:
        state = ls_fn(sport, gid)
        if not isinstance(state, dict):
            # gid is a Kalshi ticker, not an ESPN id -> bridge to the live game by team.
            state = _scan_live_by_legs(sport, legs, gid=gid, nowdt=nowdt,
                                       states=_cached_live_states(sport, live_states_cache))
        if not isinstance(state, dict):
            # KBO REORDER (kbo-reorder-verify lane, capture-only): ESPN cannot resolve a
            # KBO live state at all (ESPN doesn't carry the league), so this branch is
            # KBO's ONLY path to the relay wire -- the deep_state_fn dispatch below is
            # otherwise unreachable for kbo. Fire it here purely for its disk-append
            # side effect (kbo_capture_wire.kbo_deep_state_for_ticker persists via
            # append_state_row internally, see beb65aaa); fail-open (any exception is
            # swallowed, mirrors every other deep_state_fn call in this function) and
            # its return value is discarded. The returned row is UNCHANGED: reason
            # stays "no_live_state" and no decision field is touched -- capture-only.
            if str(sport).lower() == "kbo" and deep_state_fn is not None:
                try:
                    deep_state_fn(gid)
                except Exception as exc:  # noqa: BLE001 -- capture-only, never fatal
                    logger.debug(
                        "inplay_capture_loop kbo capture-only deep(%s/%s) failed: %s",
                        sport, gid, exc)
            row["reason"] = "no_live_state"
            return row
        state.setdefault("sport", sport)  # segment-trust floor lookup needs the sport
        # DEEP base-out enrichment (MLB): resolve gid (Kalshi ticker) -> statsapi gamePk ->
        # authoritative linescore base-out, MERGED onto the ESPN-resolved state so the active
        # series carries outs/base/bos/re/count + game_pk every tick (additive; never raises).
        if deep_state_fn is not None:
            try:
                deep = deep_state_fn(gid)
                if isinstance(deep, dict) and deep:
                    state = {**state, **deep}
            except Exception as exc:  # noqa: BLE001 -- deep state is additive, never fatal
                logger.debug("inplay_capture_loop deep(%s/%s) failed: %s", sport, gid, exc)
        model_p = _prob01(md_fn(sport, state))
        # SHADOW MEASUREMENT ONLY -- MUST run BEFORE the no_model_prob early return:
        # wnba/nba/tennis are exactly the sports whose md_fn returns None, so a shadow
        # write placed after that return is unreachable for its own target sports
        # (KBO wave-61 reorder precedent; decision path below is byte-unchanged).
        row["model_prob_wnba_shadow"] = _wnba_shadow(
            sport, state.get("home_display") or state.get("home"),
            state.get("away_display") or state.get("away"), state)
        row["model_prob_nba_shadow"] = _nba_shadow(
            sport, state.get("home_display") or state.get("home"),
            state.get("away_display") or state.get("away"), state)
        # SECOND, INDEPENDENT nba shadow (mechanism-ladder base spec, frozen coefficients) --
        # additive alongside model_prob_nba_shadow (NBARepricer), never replaces it. See
        # nba_logistic_pricer.py: same None-safe/never-raises contract.
        row["model_prob_nba_ladder_shadow"] = _nba_ladder_shadow(sport, state)
        row["model_prob_tennis_shadow"] = _tennis_shadow(
            sport, state.get("home_display") or state.get("home"),
            state.get("away_display") or state.get("away"), state)
        if model_p is None:
            row["reason"] = "no_model_prob"
            return row
        pair = _align_home_yes(str(state.get("home_display") or state.get("home") or ""),
                               str(state.get("away_display") or state.get("away") or ""), legs)
        if pair is None:
            row["reason"] = "no_home_leg"
            return row
        pair = _fold_draw_into_field(pair, legs)  # 3-way (soccer) -> 2-way home-vs-field
        tick = _build_tick(state, model_p, pair)
        tick["signal_ts"] = signal_ts
        state_src = (state.get("gumbo_event_ts") or _gumbo_event_ts(state)) if str(sport).lower() == "mlb" else (
            state.get("fotmob_update_ts") if str(sport).lower() in ("soccer", "soccer_intl") else None)
        tick["src_ts"] = state_src if isinstance(state_src, str) and state_src else src_ts
        pkey = "%s/%s" % (sport, gid)
        # ENRICHMENT MEASUREMENT ONLY (LANE 1), computed BEFORE on_tick (LANE 3
        # persistence): a lookup exception can never sink a tick or change on_tick's
        # decision -- _enrichment_fields is itself exception-safe (returns a None-filled
        # dict on failure) and is only ever THREADED THROUGH as additive `extra`, never
        # read by on_tick/capture_pair_once's core pairing/alignment logic.
        enrichment = _enrichment_fields(
            sport, state.get("home_display") or state.get("home"),
            state.get("away_display") or state.get("away"), gid, state)
        dec = _dt.on_tick(sport, gid, tick, position=pos_map.get(pkey),
                          now=nowdt, grade_dir=grade_dir, ledger_path=ledger_path,
                          extra=enrichment)
        pos_map[pkey] = dec.get("position")
        row.update({
            "paired": bool(dec.get("captured")), "bet": dec.get("action") == "bet",
            "action": dec.get("action"), "tier": dec.get("tier"),
            "model_prob": model_p, "devigged_price": _devig_of(tick),
            "p0_source": state.get("p0_source"), "reason": dec.get("reason") or "ok",
        })
        # SP SHADOW MEASUREMENT ONLY, added AFTER dec is final -- never read by on_tick.
        # (Stays here: it needs the real model_p, which mlb always has past the gate;
        # the wnba/nba/tennis shadows moved ABOVE the no_model_prob return, where their
        # target sports actually reach.)
        row["model_prob_sp_shadow"] = _sp_shadow(sport, state.get("home_display") or state.get("home"),
            state.get("away_display") or state.get("away"), model_p, state.get("game_pk"))
        # Same enrichment dict also mirrors onto the heartbeat/ops row for visibility
        # (unchanged behavior from before this LANE 3 move -- still after dec is final).
        row.update(enrichment)
    except Exception as exc:  # noqa: BLE001 -- one bad game never stops the others
        logger.warning("inplay_capture_loop game %s/%s failed: %s", sport, gid, exc)
        row["reason"] = "error:%s" % type(exc).__name__
    return row


def _sp_shadow(sport: str, home: Any, away: Any, model_p: float, game_pk: Any = None) -> Optional[float]:
    """SHADOW MEASUREMENT ONLY (logged, never decided on). All logic lives in
    ingame_sp_shadow.py; this wrapper only guarantees an exception here can never reach
    the capture path. None-safe."""
    try:
        from scripts.platformkit.ingame.ingame_sp_shadow import get_shadow
        return get_shadow().shadow_prob(sport, str(home or ""), str(away or ""), model_p,
                                        int(game_pk) if game_pk is not None else None)
    except Exception:  # noqa: BLE001 -- shadow measurement never affects the capture path
        return None


def _wnba_shadow(sport: str, home: Any, away: Any, state: Dict[str, Any]) -> Optional[float]:
    """SHADOW MEASUREMENT ONLY (logged, never decided on). All logic lives in
    wnba_ingame_shadow.py; this wrapper only guarantees an exception here can
    never reach the capture path. None-safe (see inplay_capture_loop's
    npb/kbo DEFAULT_SPORTS comment for the analogous no-live-model-yet gap
    this shadow is scoped to measure once wired)."""
    try:
        from scripts.platformkit.ingame.wnba_ingame_shadow import get_shadow
        return get_shadow().shadow_prob(sport, str(home or ""), str(away or ""), state)
    except Exception:  # noqa: BLE001 -- shadow measurement never affects the capture path
        return None


def _nba_shadow(sport: str, home: Any, away: Any, state: Dict[str, Any]) -> Optional[float]:
    """SHADOW MEASUREMENT ONLY (logged, never decided on). All logic lives in
    domains/basketball_nba/ingame_shadow.py; this wrapper only guarantees an
    exception here can never reach the capture path. None-safe. Same gap this
    measures as _wnba_shadow: live_board.live_model_home_prob's dispatch has
    no nba branch, so model_prob stays None for every nba tick regardless of
    this shadow's existence (LANE 3 wave)."""
    try:
        from domains.basketball_nba.ingame_shadow import get_shadow
        return get_shadow().shadow_prob(sport, str(home or ""), str(away or ""), state)
    except Exception:  # noqa: BLE001 -- shadow measurement never affects the capture path
        return None


def _nba_ladder_shadow(sport: str, state: Dict[str, Any]) -> Optional[float]:
    """SHADOW MEASUREMENT ONLY -- the mechanism-ladder base spec (frozen coefficients,
    nba_logistic_pricer.py) priced from this tick's (margin, frac_elapsed, pregame prior).
    Independent of _nba_shadow (NBARepricer); logged as a SEPARATE field so forward
    capture grades both against the market. Never decided on, never raises. nba-only;
    None on any missing input (state_diff/frac_elapsed/p0) or unreadable artifact."""
    try:
        if str(sport or "").lower() != "nba" or not isinstance(state, dict):
            return None
        from scripts.platformkit.ingame.nba_logistic_pricer import get_pricer
        return get_pricer().price(state.get("state_diff"), state.get("frac_elapsed"),
                                  state.get("p0"))
    except Exception:  # noqa: BLE001 -- shadow measurement never affects the capture path
        return None


def _tennis_shadow(sport: str, home: Any, away: Any, state: Dict[str, Any]) -> Optional[float]:
    """SHADOW MEASUREMENT ONLY (logged, never decided on). All logic lives in
    domains/tennis/ingame_shadow.py; this wrapper only guarantees an exception
    here can never reach the capture path. None-safe. Same gap this measures
    as _wnba_shadow: live_board.live_model_home_prob's dispatch has no tennis
    branch, so model_prob stays None for every tennis tick regardless of this
    shadow's existence (LANE 3 wave)."""
    try:
        from domains.tennis.ingame_shadow import get_shadow
        return get_shadow().shadow_prob(sport, str(home or ""), str(away or ""), state)
    except Exception:  # noqa: BLE001 -- shadow measurement never affects the capture path
        return None


def _identity_fields_mlb(state: Dict[str, Any]) -> Dict[str, Any]:
    """MLB IDENTITY fields for the grade row (root-cause fix: the live model only ever saw
    8 crude state features -- score/inning/base-out -- with no notion of WHO is playing).
    batter_id/pitcher_id/pitch_count/ondeck_id/bullpen_used are ALREADY resolved onto
    *state* by ingame_id_resolver_mlb's deep_state_fn merge (ingame_pitcher_mlb.
    pitcher_batter_fields, itself parsed from the SAME statsapi linescore+boxscore payload
    the base-out/pitch-count resolver already fetches -- no extra request, no new pacing).
    mlb_-prefixed so a future replay can condition on player identity without colliding with
    any other sport's state keys. None when the source key never resolved (pregame gap,
    resolver miss, non-MLB tick) -- never fabricated."""
    return {
        "mlb_batter_id": state.get("batter_id"),
        "mlb_pitcher_id": state.get("pitcher_id"),
        "mlb_pitcher_pitch_count": state.get("pitch_count"),
        "mlb_ondeck_id": state.get("ondeck_id"),
        "mlb_bullpen_used": state.get("bullpen_used"),
    }


def _enrichment_fields(sport: str, home: Any, away: Any, gid: str,
                       state: Dict[str, Any]) -> Dict[str, Any]:
    """ENRICHMENT MEASUREMENT ONLY (LANE 1). All lookup logic lives in
    ingame_enrichment.py (sidecar-file reads only, poisoned-source -> permanent
    None); this wrapper only guarantees an exception here can never reach the
    capture path. None-safe. soccer_intl gets xg_*; sports with a book-depth
    sidecar get spread_bp/book_thinness/stale_quote; mlb gets espn_wp (only if a
    cheap ESPN event id is already on the state -- else honest None/pending) AND
    the mlb_* IDENTITY fields (see _identity_fields_mlb) -- these need no facade/
    import, so they are set OUTSIDE the facade try/except: a poisoned enrichment
    facade must never suppress identity fields that were already sitting on state."""
    out: Dict[str, Any] = {"xg_home": None, "xg_away": None, "xg_asof_min": None,
                          "spread_bp": None, "book_thinness": None, "stale_quote": None,
                          "espn_wp": None, "mlb_batter_id": None, "mlb_pitcher_id": None,
                          "mlb_pitcher_pitch_count": None, "mlb_ondeck_id": None,
                          "mlb_bullpen_used": None}
    if str(sport or "").lower() == "mlb":
        out.update(_identity_fields_mlb(state))
    try:
        from scripts.platformkit.ingame.ingame_enrichment import get_facade
        facade = get_facade()
        if str(sport or "").lower() == "soccer_intl":
            xg = facade.fotmob_xg(str(home or ""), str(away or ""), state.get("minute"))
            if xg:
                out.update(xg)
        depth = facade.book_depth(str(gid or ""))
        if depth:
            out.update(depth)
        if str(sport or "").lower() == "mlb":
            wp = facade.espn_wp("mlb", state.get("espn_event_id"))
            if wp:
                out.update(wp)
    except Exception:  # noqa: BLE001 -- enrichment measurement never affects the capture path
        pass
    return out


def _devig_of(tick: Dict[str, Any]) -> Optional[float]:
    """The no-vig fair P(home) for the heartbeat readout (reuses the signal's devig). None-safe."""
    try:
        from scripts.platformkit.ingame import inplay_edge_signal as _sig
        return _sig.devig_home_price(tick.get("yes_home_prob"), tick.get("yes_away_prob"))
    except Exception:  # noqa: BLE001
        return None


def _stamp_final(sport: str, game: Dict[str, Any],
                 grade_dir: Optional[Path], nowdt: datetime) -> bool:
    """Stamp a FINAL game's held-out home_win label (W3). True iff a fresh stamp landed."""
    try:
        gid = str(game.get("game_id") or "")
        if not gid:
            return False
        res = _settle.stamp_final(sport, gid, ev=game.get("event") or game,
                                  home_win=game.get("home_win"),
                                  now=nowdt, grade_dir=grade_dir)
        return res.get("status") == "stamped"
    except Exception as exc:  # noqa: BLE001 -- a stamp failure never sinks the loop
        logger.warning("inplay_capture_loop stamp %s failed: %s", sport, exc)
        return False


def _write_heartbeat(heartbeat: Dict[str, Any], heartbeat_path: Optional[Path]) -> None:
    """Best-effort heartbeat write (reuses live_grade's atomic .tmp+replace discipline)."""
    try:
        import json
        from scripts.platformkit.ingame import live_grade as _lg
        path = Path(heartbeat_path) if heartbeat_path is not None else DEFAULT_HEARTBEAT
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(heartbeat, ensure_ascii=True))
        import os
        os.replace(str(tmp), str(path))
        _ = _lg  # keep the import meaningful (same atomic discipline family)
    except Exception as exc:  # noqa: BLE001 -- heartbeat is observability, not critical
        logger.warning("inplay_capture_loop heartbeat write failed: %s", exc)


def _make_mlb_deep_fn(deep_state_fn: Optional[Callable[[str], Dict[str, Any]]]
                      ) -> Optional[Callable[[str], Dict[str, Any]]]:
    """Build the per-tick MLB deep-state enricher (LAZY: no candidate fetch until a game
    actually needs enriching, so a dead-feed tick stays offline).  An explicit
    deep_state_fn wins (tests inject an offline stub); otherwise the real statsapi resolver.
    Returns None if the resolver cannot be imported -- enrichment is then simply skipped."""
    if deep_state_fn is not None:
        return deep_state_fn
    try:
        from scripts.platformkit.ingame import ingame_id_resolver_mlb as _res
        return _res.make_tick_deep_fn()
    except Exception as exc:  # noqa: BLE001 -- no resolver -> shallow capture, never a crash
        logger.debug("inplay_capture_loop deep enricher unavailable: %s", exc)
        return None


def _make_kbo_deep_fn(kbo_deep_state_fn: Optional[Callable[[str], Dict[str, Any]]]
                      ) -> Optional[Callable[[str], Dict[str, Any]]]:
    """Build the per-tick KBO deep-state enricher (kbo-alias-wire-soak lane, capture-
    only): kbo_capture_wire chains ticker->alias->matcher->relay to an as-of state row
    (inning/half/outs/base/score/count), NO model prob. An explicit kbo_deep_state_fn
    wins (tests inject an offline stub); otherwise the real wire. Returns None if the
    wire cannot be imported -- enrichment is then simply skipped (same degrade-to-shallow
    discipline as the MLB builder)."""
    if kbo_deep_state_fn is not None:
        return kbo_deep_state_fn
    try:
        from scripts.platformkit.ingame import kbo_capture_wire as _kbo_wire
        return _kbo_wire.make_kbo_deep_fn()
    except Exception as exc:  # noqa: BLE001 -- no wire -> shallow capture, never a crash
        logger.debug("inplay_capture_loop kbo deep enricher unavailable: %s", exc)
        return None


def serve_forever(interval: Optional[float] = None, *,
                  clock: Optional[Callable[[float], None]] = None,
                  max_ticks: Optional[int] = None,
                  sports: Optional[List[str]] = None,
                  live_state_fn: Optional[LiveStateFn] = None,
                  model_fn: Optional[ModelFn] = None,
                  inplay_fetch_fn: Optional[InplayFetchFn] = None,
                  finals_fn: Optional[FinalsFn] = None,
                  mlb_deep: bool = False,
                  deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
                  kbo_deep: bool = False,
                  kbo_deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
                  depth_capture: bool = False,
                  depth_capture_fn: Optional[DepthCaptureFn] = None,
                  grade_dir: Optional[Path] = None,
                  ledger_path: Optional[Path] = None,
                  heartbeat_path: Optional[Path] = None) -> int:
    """Drive poll_once on a cadence until *max_ticks* (or forever). Returns ticks executed.

    BOUNDED runs ALWAYS stop (max_ticks). *clock* is injectable so the tested path NEVER
    calls time.sleep. Positions are threaded across ticks. Never raises on a per-tick error.

    *mlb_deep* (default OFF) enables the statsapi base-out enricher so the captured MLB
    series carries the deep in-game state every tick; the production runner turns it ON.
    The enricher is rebuilt per tick (fresh live candidates) and LAZY (no fetch on a tick
    with no MLB game to enrich), so leaving it OFF -- or running with a dead feed -- needs
    no network.  *deep_state_fn* injects an offline enricher for the tested path.

    *kbo_deep* (default OFF, kbo-alias-wire-soak lane) enables the CAPTURE-ONLY KBO relay
    state-row enricher (kbo_capture_wire): NO model probability, NO dispatch branch --
    purely descriptive (inning/half/outs/base/score/count) alongside the existing tick.
    Same fail-open discipline as mlb_deep: OFF by default, any failure degrades to a
    shallow (unenriched) capture. *kbo_deep_state_fn* injects an offline stub for the
    tested path.

    *depth_capture* (LANE 4b, default OFF) enables the OPTIONAL order-book depth-capture
    hook (odds_provider.depth_capture.run_capture_pass by default) at a slower cadence
    (DEPTH_CAPTURE_EVERY_N_TICKS) than the price-pairing tick -- FAIL-OPEN: any exception
    inside the hook is caught in poll_once/_maybe_capture_depth and can never stop or
    affect this loop. *depth_capture_fn* injects an offline stub for the tested path (mirrors
    deep_state_fn); a real explicit depth_capture_fn implies depth_capture=True even if the
    flag was left at its default, so a caller can inject a test stub without also flipping
    the flag.
    """
    sleep = clock if clock is not None else time.sleep
    positions: Dict[str, Dict[str, Any]] = {}
    depth_tick_counter: Dict[str, int] = {}
    active_depth_fn: Optional[DepthCaptureFn] = None
    if depth_capture_fn is not None:
        active_depth_fn = depth_capture_fn
    elif depth_capture:
        active_depth_fn = _default_depth_capture
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        # Fresh per-tick enricher so the live candidate set tracks the slate (LAZY: built
        # only when mlb_deep is on; no candidate fetch until a real MLB game is enriched).
        tick_deep_fn = _make_mlb_deep_fn(deep_state_fn) if mlb_deep else None
        tick_kbo_deep_fn = _make_kbo_deep_fn(kbo_deep_state_fn) if kbo_deep else None
        try:
            hb = poll_once(sports=sports, live_state_fn=live_state_fn, model_fn=model_fn,
                           inplay_fetch_fn=inplay_fetch_fn, finals_fn=finals_fn,
                           deep_state_fn=tick_deep_fn,
                           kbo_deep_state_fn=tick_kbo_deep_fn,
                           depth_capture_fn=active_depth_fn,
                           depth_tick_counter=depth_tick_counter,
                           grade_dir=grade_dir, ledger_path=ledger_path,
                           heartbeat_path=heartbeat_path, positions=positions)
        except Exception as exc:  # noqa: BLE001 -- a tick error never stops the loop
            logger.warning("inplay_capture_loop tick error: %s", exc)
            hb = {"n_live": 0}
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        wait = float(interval) if interval is not None else (
            _live_interval_sec() if hb.get("n_live") else _idle_interval_sec())
        try:
            sleep(wait)
        except Exception as exc:  # noqa: BLE001 -- a clock error never sinks the loop
            logger.warning("inplay_capture_loop sleep error: %s", exc)
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: a BOUNDED measurement run (default 1 tick). NOT auto-armed -- explicit invocation."""
    import argparse
    ap = argparse.ArgumentParser(prog="inplay_capture_loop")
    ap.add_argument("--max-ticks", type=int, default=1, help="bounded ticks (default 1)")
    ap.add_argument("--interval", type=float, default=None, help="poll interval seconds")
    ap.add_argument("--sports", default=",".join(DEFAULT_SPORTS), help="comma sports")
    args = ap.parse_args(argv)
    n = serve_forever(interval=args.interval, max_ticks=args.max_ticks,
                      sports=[s.strip() for s in args.sports.split(",") if s.strip()])
    print("inplay_capture_loop ran %d tick(s); measurement-only, paper, no $." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_GRADE_DIR", "DEFAULT_SPORTS", "LIVE_INTERVAL_SEC", "IDLE_INTERVAL_SEC",
    "poll_once", "serve_forever",
]
