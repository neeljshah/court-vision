"""scripts.platformkit.frontend.live_board -- TODAY's real games + LIVE in-game predictions.

Pulls today's real schedule and LIVE game state from ESPN's keyless public scoreboard
endpoint (site.api.espn.com/apis/site/v2/sports/<sport>/<league>/scoreboard), normalizes
each game (home/away, state pre/in/post, score, clock/period), and for every IN-PROGRESS
game feeds the realized live state through the SAME validated predictor chain the rest of
the product uses -- scripts.platformkit.predict_matchup.build_result on a predictor from
predictor_jd._build_predictor -- to attach the coherent pregame + in-game block.

HONEST + SAFE (binding):
  * NEVER fabricates a score or a prediction. If the feed is down -> status="unavailable".
  * ESPN full team names are mapped onto the predictor's expected ids (NBA/MLB short codes,
    full national-team names for the World Cup) via the same kind of resolution odds/predictor
    use. A team that cannot be resolved is SKIPPED with a logged note, never faked.
  * numpy scalars are coerced to plain float so the payload is strict-JSON-safe.
  * Markets are efficient -- NO $ edge is claimed anywhere.

NO network at import time / in tests: the http getter is INJECTABLE (http_get=...).

INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

import argparse
import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.predictor_jd import _build_predictor
from scripts.platformkit import predict_matchup as pm

logger = logging.getLogger(__name__)

# Our platform sport id -> ESPN (site_path, league) for the keyless scoreboard.
# soccer_intl = the World Cup (fifa.world); soccer = club (eng.1 demo league).
_ESPN_ROUTES: Dict[str, Tuple[str, str]] = {
    "mlb": ("baseball/mlb", "mlb"),
    "nba": ("basketball/nba", "nba"),
    "wnba": ("basketball/wnba", "wnba"),
    "soccer_intl": ("soccer/fifa.world", "fifa.world"),
    "soccer": ("soccer/eng.1", "eng.1"),
}

_SITE_BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_TIMEOUT = 12

# ESPN abbreviation -> predictor short code where they differ. ESPN uses a handful of
# non-standard codes; the predictors key on the corpus' own short codes (see their .teams).
_NBA_ABBR = {"SA": "SAS", "NY": "NYK", "GS": "GSW", "NO": "NOP", "UTAH": "UTA",
             "WSH": "WAS", "PHO": "PHX"}
_MLB_ABBR = {"SF": "SFG", "KC": "KAN", "SD": "SDG", "TB": "TAM", "WSH": "WAS",
             "AZ": "ARI", "CHW": "CWS"}
# ESPN national-team displayName -> soccer_intl corpus name where they differ.
_INTL_NAME = {"Congo DR": "DR Congo", "Korea Republic": "South Korea",
              "Korea DPR": "North Korea", "USA": "United States", "IR Iran": "Iran"}

_UNAVAILABLE_FEED = (
    "ESPN scoreboard unavailable (feed down/blocked); no live games returned. "
    "This is degraded-not-fabricated: no scores or predictions are invented.")


def _http_json(url: str) -> Dict[str, Any]:
    """Default keyless GET (urllib + browser UA + timeout). Returns {} on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_exc:
            if http_exc.code != 403:
                raise
            # Datacenter IPs (RunPod) get 403 on browser UAs but 200 on plain
            # ones -- verified 2026-08-31. Retry once with a plain UA.
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
                return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network guard
        logger.warning("ESPN scoreboard GET failed %s: %s", url, exc)
        return {}


def _norm_sport(sport: str) -> str:
    s = sport.lower()
    return {"basketball_nba": "nba", "worldcup": "soccer_intl", "wc": "soccer_intl"}.get(s, s)


def resolve_team(sport: str, abbr: Optional[str], display: Optional[str]) -> Optional[str]:
    """Map an ESPN team (abbreviation + displayName) onto the predictor's expected id.

    NBA/MLB key on short codes; the World Cup keys on the full national-team name. Returns
    the predictor id, or None if nothing usable was supplied (caller SKIPS, never fabricates).
    """
    s = _norm_sport(sport)
    if s == "nba":
        if not abbr:
            return None
        return _NBA_ABBR.get(abbr.upper(), abbr.upper())
    if s == "mlb":
        if not abbr:
            return None
        return _MLB_ABBR.get(abbr.upper(), abbr.upper())
    if s in ("soccer_intl", "soccer"):
        if not display:
            return None
        return _INTL_NAME.get(display, display)
    if s == "wnba":
        # WNBA corpus (espn_scoreboard.parquet) keys on the full ESPN
        # displayName ("Las Vegas Aces") -- it was BUILT from this same ESPN
        # feed, so pass through unchanged (no short-code map needed, unlike
        # nba/mlb whose corpora predate/differ from ESPN's own codes).
        if not display:
            return None
        return display
    return None


_PREDICTOR_CACHE: Dict[str, Any] = {}


def _cached_predictor(sport: str) -> Any:
    """Build (once) + cache the domain predictor; building is corpus-heavy."""
    s = _norm_sport(sport)
    if s not in _PREDICTOR_CACHE:
        _PREDICTOR_CACHE[s] = _build_predictor(s)
    return _PREDICTOR_CACHE[s]


def live_model_home_prob(sport: str, state: Dict[str, Any]) -> Optional[float]:
    """P(home win) as-of this live tick -- the seam the in-play capture loop's default
    model_fn calls. Reuses the domain predictor's CALIBRATED, leak-free predict_live
    (read-only) on the realized live state (absolute score + minute + pregame lambdas).

    Wired for mlb, nba, wnba, tennis, soccer, and soccer_intl; any other sport returns None so the caller
    SKIPS the pair cleanly -- it NEVER fabricates a number. Never raises (a model miss is a
    clean skip, not a crashed tick).

    NPB/KBO are NOT wired: both sports' BASE fits are HONEST_NEGATIVE, disqualified by the
    same planted pure-noise control (data/domains/{npb,kbo}/ingame_base_fit_verdict.json,
    disqualified_by_noise_control=true, params_persisted=false) -- see
    scripts/platformkit/ingame/test_npb_kbo_live_model_gap.py."""
    try:
        s = _norm_sport(sport)
        if not isinstance(state, dict):
            return None
        # MLB in-game: blend the proven pregame prior toward the realized run-diff via the
        # verified freshness surface (carries p0; calibration, not edge). Daily slate -> live.
        if s == "mlb":
            from scripts.platformkit.ingame.mlb_live_model import mlb_home_prob
            return mlb_home_prob(state)
        # NBA in-game: the W146/W156 temperature-recalibrated NBAPredictor.predict_live,
        # already proven out as domains/basketball_nba/ingame_shadow's measurement-only
        # shadow probe (see that module's docstring) -- served here for real, unchanged.
        # The independent frozen-coefficient ladder (nba_logistic_pricer) stays a shadow
        # column only (inplay_capture_loop.model_prob_nba_ladder_shadow); not served.
        if s == "nba":
            from domains.basketball_nba.ingame_shadow import get_shadow
            home = state.get("home_display") or state.get("home")
            away = state.get("away_display") or state.get("away")
            return get_shadow().shadow_prob(s, home, away, state)
        # WNBA in-game: the walk-forward-fitted anchored blend (2024 fit -> 2025
        # validate -> 2026 OOS, data/domains/wnba/ingame_blend_check.json) via
        # WNBAAdapter.predict_live, same shadow-module pattern as nba above.
        if s == "wnba":
            from scripts.platformkit.ingame.wnba_ingame_shadow import get_shadow as _wshadow
            home = state.get("home_display") or state.get("home")
            away = state.get("away_display") or state.get("away")
            return _wshadow().shadow_prob(s, home, away, state)
        # TENNIS in-game (promoted 2026-07-19, same shadow->served path wnba/nba
        # took): TennisPredictor.predict_live behind domains/tennis/ingame_shadow,
        # backed by the REPLICATED base+prior calibration surface
        # (data/cache/ingame/models/tennis_ingame.json, n_games=40588). Paper
        # decisions stay bounded by the breaker + divergence gate; shadow column
        # keeps logging alongside (byte-identical from this wave, same as nba's).
        if s == "tennis":
            from domains.tennis.ingame_shadow import get_shadow as _tshadow
            home = state.get("home_display") or state.get("home")
            away = state.get("away_display") or state.get("away")
            return _tshadow().shadow_prob(s, home, away, state)
        if s not in ("soccer", "soccer_intl"):
            return None
        home = resolve_team(s, state.get("home"), state.get("home_display"))
        away = resolve_team(s, state.get("away"), state.get("away_display"))
        frac = state.get("frac_elapsed")
        if not home or not away or frac is None:
            return None
        minute = max(0.0, min(90.0, float(frac) * 90.0))
        hg = int(round(float(state.get("home_goals") or 0)))
        ag = int(round(float(state.get("away_goals") or 0)))
        res = _cached_predictor(s).predict_live(home, away, minute, hg, ag)
        p = res.get("p_home_win") if isinstance(res, dict) else None
        return float(p) if isinstance(p, (int, float)) else None
    except Exception as exc:  # noqa: BLE001 -- a model miss is a clean skip, never a crash
        logger.debug("live_model_home_prob(%s) failed: %s", sport, exc)
        return None


def _nba_elapsed(period: Optional[int], clock: Optional[str]) -> Optional[float]:
    """NBA minutes ELAPSED from period (quarter) + displayClock (time REMAINING in period)."""
    if not period:
        return None
    rem = 0.0
    if clock and ":" in str(clock):
        try:
            mm, ss = str(clock).split(":")
            rem = float(mm) + float(ss) / 60.0
        except (ValueError, TypeError):
            rem = 0.0
    return round(max(0.0, (int(period) - 1) * 12.0 + (12.0 - rem)), 2)


def _wnba_elapsed(period: Optional[int], clock: Optional[str]) -> Optional[float]:
    """WNBA minutes ELAPSED: same shape as _nba_elapsed but 10-min quarters
    (REG_SEC=2400s, see domains/basketball_wnba/ingame_blend.py PERIOD_SEC)."""
    if not period:
        return None
    rem = 0.0
    if clock and ":" in str(clock):
        try:
            mm, ss = str(clock).split(":")
            rem = float(mm) + float(ss) / 60.0
        except (ValueError, TypeError):
            rem = 0.0
    return round(max(0.0, (int(period) - 1) * 10.0 + (10.0 - rem)), 2)


def _mlb_half_inning(detail: Optional[str], period: Optional[int]
                     ) -> Tuple[Optional[int], Optional[str]]:
    """MLB (inning, half) from the ESPN shortDetail ('Top 6th' / 'Bot 3rd' / 'End 2nd')."""
    if not detail:
        return (period if period else None), None
    low = detail.lower()
    half = "top" if low.startswith("top") else ("bottom" if low.startswith("bot") else None)
    # 'Mid'/'End' = between halves; treat as the inning's bottom not started -> top boundary.
    inning = period if period else None
    return inning, half


def _parse_event(ev: Dict[str, Any], sport: str) -> Optional[Dict[str, Any]]:
    """One ESPN scoreboard event -> a normalized row (no prediction yet). None if unparseable."""
    comps = ev.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    status = ev.get("status") or {}
    st_type = status.get("type") or {}
    state = st_type.get("state")  # 'pre' | 'in' | 'post'
    detail = st_type.get("shortDetail") or st_type.get("detail")
    clock = status.get("displayClock")
    period = status.get("period")
    home = away = None
    for c in comp.get("competitors") or []:
        team = c.get("team") or {}
        info = {"abbr": team.get("abbreviation"),
                "display": team.get("displayName") or team.get("abbreviation"),
                "score": c.get("score")}
        if c.get("homeAway") == "home":
            home = info
        elif c.get("homeAway") == "away":
            away = info
    if home is None or away is None:
        return None
    return {"sport": _norm_sport(sport),
            "home": home["display"], "away": away["display"],
            "home_abbr": home["abbr"], "away_abbr": away["abbr"],
            "state": state, "detail": detail, "clock": clock,
            "period": int(period) if period else None,
            "home_score": _to_int(home["score"]), "away_score": _to_int(away["score"])}


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _live_ns(sport: str, row: Dict[str, Any], home_id: str, away_id: str
             ) -> argparse.Namespace:
    """Build a predict_matchup-shaped Namespace carrying the live state for this sport."""
    s = _norm_sport(sport)
    ns = argparse.Namespace(
        sport=s, home=home_id, away=away_id, surface="Hard",
        elapsed=None, inning=None, half=None,
        home_score=row.get("home_score"), away_score=row.get("away_score"),
        sets_home=None, sets_away=None, games_home=None, games_away=None)
    if s == "nba":
        ns.elapsed = _nba_elapsed(row.get("period"), row.get("clock"))
    elif s == "wnba":
        ns.elapsed = _wnba_elapsed(row.get("period"), row.get("clock"))
    elif s in ("soccer", "soccer_intl"):
        ns.elapsed = _soccer_minute(row.get("clock"))
    elif s == "mlb":
        inning, half = _mlb_half_inning(row.get("detail"), row.get("period"))
        ns.inning, ns.half = inning, half
    return ns


def _soccer_minute(clock: Optional[str]) -> Optional[float]:
    """Soccer match minute from the ESPN displayClock ("29'" / "90'+5'")."""
    if not clock:
        return None
    txt = str(clock).replace("'", " ").strip()
    try:
        if "+" in txt:
            base, extra = txt.split("+")
            return float(base.strip()) + float(extra.strip() or 0)
        return float(txt.split()[0])
    except (ValueError, IndexError):
        return None


def _predict_for_row(row: Dict[str, Any], predictor: Any) -> None:
    """Attach pregame+ingame prediction to an IN-PROGRESS row, in place. Never fabricates."""
    sport = row["sport"]
    home_id = resolve_team(sport, row.get("home_abbr"), row.get("home"))
    away_id = resolve_team(sport, row.get("away_abbr"), row.get("away"))
    if home_id is None or away_id is None:
        row["prediction"] = None
        row["predict_note"] = ("team could not be resolved to a predictor id; skipped "
                               "(no fabricated prediction)")
        logger.warning("live_board skip: unresolved team %s vs %s (%s)",
                       row.get("home"), row.get("away"), sport)
        return
    ns = _live_ns(sport, row, home_id, away_id)
    try:
        result = pm.build_result(sport, predictor, ns)
        # Honest in-game-support note: some predictors (e.g. soccer_intl/World Cup) ship
        # pregame only -- no predict_live -- so build_result returns pregame + ingame_note.
        if "ingame" not in result and not hasattr(predictor, "predict_live"):
            result["ingame_note"] = ("this predictor has no in-game (predict_live) model; "
                                     "live state is shown but only pregame is predicted")
        row["prediction"] = pm._jsonsafe(result)
        row["predictor_ids"] = {"home": home_id, "away": away_id}
    except Exception as exc:  # noqa: BLE001 - one bad game never sinks the board
        row["prediction"] = None
        row["predict_note"] = f"prediction error ({type(exc).__name__})"
        logger.warning("live_board predict failed %s vs %s: %s", home_id, away_id, exc)


def todays_live_games(sport: str, *,
                      date: Optional[str] = None,
                      http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
                      predictor_factory: Callable[[str], Any] = _build_predictor,
                      ) -> Dict[str, Any]:
    """Today's (or *date*='YYYYMMDD') real games + LIVE state for *sport*.

    *date* is an AS-OF override for ESPN's own historical scoreboard (confirmed live:
    ``?dates=YYYYMMDD`` returns that day's board with state='post' for finals) -- used
    by grade_paper_asof's backlog pass to resolve a game that ended on a prior day.
    None (default) = today, unchanged behavior for every existing caller.

    *http_get* and *predictor_factory* are injectable (tests pass canned payloads + stubs;
    no network, no corpus). Degrades to status='unavailable' if the feed is down -- never
    fabricates a score or a prediction.
    """
    s = _norm_sport(sport)
    as_of = datetime.now(timezone.utc).isoformat()
    if s not in _ESPN_ROUTES:
        return {"sport": s, "status": "unknown_sport", "as_of": as_of, "games": [],
                "note": f"unknown sport '{s}'; choose one of {', '.join(_ESPN_ROUTES)}"}
    getter = http_get if http_get is not None else _http_json
    site_path, league = _ESPN_ROUTES[s]
    url = _SITE_BASE.format(path=site_path)
    if date:
        url = f"{url}?dates={date}"
    try:
        payload = getter(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("live_board feed error %s: %s", s, exc)
        payload = {}
    events = (payload or {}).get("events")
    if not payload or events is None:
        return {"sport": s, "status": "unavailable", "as_of": as_of, "games": [],
                "note": _UNAVAILABLE_FEED}
    predictor = None
    try:
        predictor = predictor_factory(s)
    except Exception as exc:  # noqa: BLE001
        logger.warning("live_board predictor factory failed %s: %s", s, exc)
    rows: List[Dict[str, Any]] = []
    for ev in events:
        try:
            row = _parse_event(ev, s)
        except Exception as exc:  # noqa: BLE001 - per-event guard
            logger.warning("live_board event parse failed: %s", exc)
            continue
        if row is None:
            continue
        row["as_of"] = as_of
        if row["state"] == "in":
            if predictor is None:
                row["prediction"] = None
                row["predict_note"] = pm._UNAVAILABLE
            else:
                _predict_for_row(row, predictor)
        rows.append(row)
    live = [r for r in rows if r["state"] == "in"]
    return {"sport": s, "status": "ok", "as_of": as_of,
            "n_games": len(rows), "n_live": len(live),
            "predictor_available": predictor is not None,
            "games": rows,
            "honest_note": ("Live state from ESPN's keyless scoreboard; in-game numbers "
                            "from the validated predictor. Markets efficient -- NO $ edge.")}


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Today's live games + in-game predictions.")
    ap.add_argument("--sport", default="mlb")
    a = ap.parse_args(argv)
    print(json.dumps(todays_live_games(a.sport), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
