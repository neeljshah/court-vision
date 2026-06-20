"""predict_service.produce -- SnapshotEnvelope producer.

Assembles ONE canonical snapshot for a sport: build_result (pregame numbers) +
keyless odds aggregate + devig/EV helpers -> PredictionRecord + MarketRow + EdgeRow.

INJECTABLE FEEDS (offline/test): schedule_feed / odds_feed / predict_fn.

CORPUS WARMUP: produce_sport() pre-warms the predictor ONCE (via _try_warm_predictor)
before the per-game loop. For the default predict_fn, corpus absent or degenerate ->
status='unavailable' before any per-game call; never a fabricated constant-prior slate.

DEGENERACY GUARD (P0 MLB flat-prior): detects <=2 distinct pregame_probs on a
>=MIN_CARDS-game slate. On detection: clear cache + single rebuild. Still flat ->
status='unavailable'; NEVER status='ok' with constant probs. _build_predictor also
refuses a predictor whose _elo is nearly constant across all corpus teams.

HONESTY: no $ edge; leak_guard in_sample=False; CLV computed downstream.
INVARIANTS: predict_service/ only; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from predict_service import store
from predict_service.assemble import (
    edge_rows,
    market_rows,
    model_probs_from_pregame,
    pregame_probs_record,
)
from predict_service.contracts import (
    GAME_STATE_LIVE,
    GAME_STATE_POST,
    GAME_STATE_PRE,
    _TYPICAL_GAME_DURATION_SECONDS,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

ScheduleFeed = Callable[[str], List[Dict[str, Any]]]
OddsFeed = Callable[[str], Dict[str, Any]]
PredictFn = Callable[[str, str, str], Dict[str, Any]]

# A slate is considered "real" (not an empty/off-day slate) when it has at least this
# many games. Below this threshold the flat-prior check is skipped (a 1-game slate with
# one unique p_home is fine; we only care when many games all share the same prob).
MIN_CARDS = 3

# When <=_MAX_DISTINCT_PROBS distinct pregame_probs values are found across a real slate
# (>= MIN_CARDS games), the snapshot is flagged as degenerate (flat-prior collapse).
_MAX_DISTINCT_PROBS = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _derive_game_state(tipoff: Optional[str],
                       live_state: Optional[str] = None) -> str:
    """Derive 'pre'|'live'|'post'. live_state wins if present; else tipoff heuristic."""
    if live_state is not None:
        ls = str(live_state).strip().lower()
        if ls in ("post", "final", "ft", "complete", "finished", "closed"):
            return GAME_STATE_POST
        if ls in ("live", "in_progress", "inprogress", "half_time", "halftime"):
            return GAME_STATE_LIVE
        if ls in ("pre", "scheduled", "notstarted"):
            return GAME_STATE_PRE
    if not tipoff:
        return GAME_STATE_PRE
    try:
        tip_dt = datetime.fromisoformat(str(tipoff).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return GAME_STATE_PRE
    now = datetime.now(timezone.utc)
    if tip_dt.tzinfo is None:
        tip_dt = tip_dt.replace(tzinfo=timezone.utc)
    elapsed = (now - tip_dt).total_seconds()
    if elapsed < 0:
        return GAME_STATE_PRE
    return GAME_STATE_LIVE if elapsed <= _TYPICAL_GAME_DURATION_SECONDS else GAME_STATE_POST


def _default_odds_feed(sport: str) -> Dict[str, Any]:
    from scripts.platformkit.odds_provider.aggregate import aggregate  # noqa: PLC0415
    return aggregate(sport)


def _default_schedule_feed(sport: str) -> List[Dict[str, Any]]:
    return games_from_odds(_default_odds_feed(sport))


def _try_warm_predictor(sport: str) -> Optional[str]:
    """Pre-warm corpus for *sport*. None=ready; str=honest unavailable reason."""
    try:
        from scripts.platformkit.predictor_jd import _build_predictor  # noqa: PLC0415
        if _build_predictor(sport) is None:
            return (
                f"{sport} corpus unavailable or init-rating collapse; "
                "snapshot withheld to prevent fabricated constant-prior cards."
            )
        return None
    except Exception as exc:  # noqa: BLE001 -- never block produce on a warmup error
        return f"{sport} predictor warmup error: {type(exc).__name__}: {exc}"


def _default_predict_fn(sport: str, home: str, away: str) -> Dict[str, Any]:
    """build_result via cached predictor; {} when corpus unavailable."""
    from scripts.platformkit.predict_matchup import build_result  # noqa: PLC0415
    from scripts.platformkit.predictor_jd import _build_predictor  # noqa: PLC0415
    pred = _build_predictor(sport)
    if pred is None:
        return {}
    args = argparse.Namespace(home=home, away=away, surface="Hard", elapsed=None,
                              inning=None, half=None, home_score=None, away_score=None,
                              sets_home=None, sets_away=None, games_home=None,
                              games_away=None)
    return build_result(sport, pred, args)


def games_from_odds(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull a clean schedule list out of an aggregate-shaped odds payload."""
    games: List[Dict[str, Any]] = []
    for ev in (payload or {}).get("events", []) or []:
        home, away = ev.get("home"), ev.get("away")
        if not home or not away:
            continue
        games.append({
            "game_id": str(ev.get("event_id") or f"{away}@{home}"),
            "home": home, "away": away,
            "tipoff": ev.get("commence_time"),
        })
    return games


def _prices_for(payload: Dict[str, Any], home: str, away: str
                ) -> Dict[str, Dict[str, Optional[float]]]:
    """Find the merged price book for one (home, away) game in the odds payload."""
    for ev in (payload or {}).get("events", []) or []:
        if ev.get("home") == home and ev.get("away") == away:
            return ev.get("prices") or {}
    return {}


def _live_state_for(payload: Dict[str, Any], home: str, away: str
                    ) -> Optional[str]:
    """Return the live.state string for one game from the odds payload, or None."""
    for ev in (payload or {}).get("events", []) or []:
        if ev.get("home") == home and ev.get("away") == away:
            live = ev.get("live") or {}
            state = live.get("state")
            return str(state) if state is not None else None
    return None


def _record_for_game(sport: str, game: Dict[str, Any], payload: Dict[str, Any],
                     predict_fn: PredictFn, produced_at: str
                     ) -> Optional[Dict[str, Any]]:
    """Build {record, markets, edges} for one game; None if no usable prediction."""
    home, away = game["home"], game["away"]
    result = predict_fn(sport, home, away) or {}
    pregame = result.get("pregame") or {}
    record_probs = pregame_probs_record(pregame)
    if not record_probs:
        return None  # no model number -> skip; never fabricate
    if "home_ml" in record_probs and pregame.get("p_home_win") is not None:
        assert record_probs["home_ml"] == float(pregame["p_home_win"]), \
            "pregame home prob drifted from build_result"
    if "draw" in record_probs and pregame.get("p_draw") is not None:
        assert record_probs["draw"] == float(pregame["p_draw"]), \
            "pregame draw prob drifted from build_result"
    game_id = game["game_id"]
    prices = _prices_for(payload, home, away)
    mkts = market_rows(sport, game_id, prices, captured_at=(payload or {}).get("as_of"))
    edges = edge_rows(game_id, model_probs_from_pregame(pregame), mkts)
    game_state = _derive_game_state(game.get("tipoff"),
                                    live_state=_live_state_for(payload, home, away))
    record = PredictionRecord(
        sport=sport, game_id=game_id, home=home, away=away,
        tipoff=game.get("tipoff"), pregame_probs=record_probs,
        markets=mkts, leak_guard={"in_sample": False},
        produced_at=produced_at, game_state=game_state, note="")
    return {"record": record, "markets": mkts, "edges": edges}


def _is_degenerate(records: List[PredictionRecord]) -> bool:
    """True when >=MIN_CARDS-game slate has <=_MAX_DISTINCT_PROBS distinct home_ml values."""
    if len(records) < MIN_CARDS:
        return False  # off-day / small slate: not degenerate by this test
    probs = [round(r.pregame_probs.get("home_ml", 0.0), 4) for r in records
             if r.pregame_probs.get("home_ml") is not None]
    if len(probs) < MIN_CARDS:
        return False  # fewer than MIN_CARDS games had a home_ml prob
    return len(set(probs)) <= _MAX_DISTINCT_PROBS


def _build_records(sport: str, games: List[Dict[str, Any]], payload: Dict[str, Any],
                   predict_fn: PredictFn, produced_at: str
                   ) -> tuple[List[PredictionRecord], list, list]:
    """Build all (records, markets, edges) for the slate in one pass."""
    records: List[PredictionRecord] = []
    all_markets: list = []
    all_edges: list = []
    for game in games:
        built = _record_for_game(sport, game, payload, predict_fn, produced_at)
        if built is None:
            continue
        records.append(built["record"])
        all_markets.extend(built["markets"])
        all_edges.extend(built["edges"])
    return records, all_markets, all_edges


def produce_sport(sport: str, *,
                  schedule_feed: Optional[ScheduleFeed] = None,
                  odds_feed: Optional[OddsFeed] = None,
                  predict_fn: Optional[PredictFn] = None) -> SnapshotEnvelope:
    """Build (not persist) SnapshotEnvelope for *sport*. Warmup + degeneracy guard."""
    sport = sport.lower()
    _using_default_fn = predict_fn is None
    odds_feed = odds_feed or _default_odds_feed
    schedule_feed = schedule_feed or _default_schedule_feed
    predict_fn = predict_fn or _default_predict_fn
    produced_at = _now_iso()

    # CORPUS WARMUP: pre-load once on the real corpus path. Corpus absent or
    # degenerate -> honest 'unavailable' before any per-game loop.
    if _using_default_fn:
        warm_reason = _try_warm_predictor(sport)
        if warm_reason is not None:
            return SnapshotEnvelope.unavailable(
                sport, generated_at=produced_at, reason=warm_reason)

    payload = odds_feed(sport) or {}
    games = schedule_feed(sport) or []
    records, all_markets, all_edges = _build_records(
        sport, games, payload, predict_fn, produced_at)

    # DEGENERACY GUARD: flat-prior collapse -> cache clear + single rebuild.
    if _is_degenerate(records):
        try:
            from scripts.platformkit.predictor_jd import clear_cache  # noqa: PLC0415
            clear_cache()
        except Exception:  # noqa: BLE001
            pass
        produced_at = _now_iso()
        records, all_markets, all_edges = _build_records(
            sport, games, payload, predict_fn, produced_at)
        if _is_degenerate(records):
            return SnapshotEnvelope.unavailable(
                sport, generated_at=produced_at,
                reason=(
                    f"flat-prior collapse: {len(records)} games share "
                    f"<={_MAX_DISTINCT_PROBS} distinct pregame_probs after rebuild. "
                    "Corpus absent or init-rating fallback active. "
                    "Snapshot withheld; never status=ok with constant-prior cards."
                ))

    if not records:
        return SnapshotEnvelope.unavailable(
            sport, generated_at=produced_at,
            reason="no upcoming games with a usable prediction")
    return SnapshotEnvelope(
        sport=sport, generated_at=produced_at, status="ok",
        predictions=records, markets=all_markets, edges=all_edges,
        note="forward OOS snapshot; markets efficient; no $ edge")


def produce_once(sport: str = "nba", *,
                 out_dir: Optional[str] = None,
                 schedule_feed: Optional[ScheduleFeed] = None,
                 odds_feed: Optional[OddsFeed] = None,
                 predict_fn: Optional[PredictFn] = None) -> str:
    """Build + persist the envelope. Returns latest.json path. boot.ps1 calls THIS."""
    env = produce_sport(sport, schedule_feed=schedule_feed,
                         odds_feed=odds_feed, predict_fn=predict_fn)
    path = store.save(env, out_dir=out_dir)
    return str(path)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="predict_service.produce",
        description="Produce + persist one SnapshotEnvelope for a sport.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--out-dir", default=None, dest="out_dir")
    a = ap.parse_args(argv)
    path = produce_once(a.sport, out_dir=a.out_dir)
    env = store.read_latest(a.sport, out_dir=a.out_dir)
    print("sport=%s status=%s predictions=%d edges=%d" % (
        a.sport, env.status, len(env.predictions), len(env.edges)))
    print("saved=%s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
