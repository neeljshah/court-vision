"""scripts.platformkit.ingame.live_p0 -- LIVE pregame-prior (p0) provider (P1 wire).

THE GAP THIS CLOSES: ingame_live_state.live_state takes p0 as a pass-through and, when a
caller has none, returns p0=None. serve_ingame / predict_live then SILENTLY DEGRADE TO
BASE (state_diff, frac_elapsed only) -- LOSING the PROVEN prior-conditioning beat (the
served in-game number is supposed to carry the pregame prior). This module supplies that
p0 so the served / paired model_prob carries the prior instead of the BASE fallback.

  live_p0(sport, game_id, *, store_dir=None, read_json=None) -> dict
     Reads the CANONICAL pregame snapshot (data/frontend/predict_service/<sport>/latest.json
     -- READ-ONLY) and returns {p0, source, game_id} where:
       source="PRIOR"      -> p0 is the leak-free pregame P(home win) for this game.
       source="BASE_FALLBACK" -> no usable prior on disk; p0 is None -> caller honestly
                              degrades to BASE (labelled, never a fabricated 0.5 prior).
     NEVER raises; a missing/odd file -> BASE_FALLBACK.

  p0_for(sport, game_id, ...) -> float | None
     Thin convenience returning just the prior (None on BASE_FALLBACK) for live_state /
     the daytrader pairing.

LEAK-FREE (binding): p0 is read ONLY from the PREGAME snapshot's pregame_probs.home_ml
(computed pregame, before tip -- no live score, no close, no outcome). It is the same
leak-free prior the offline in-game corpora carry. We NEVER derive p0 from the live score
or the in-play market (that would leak / circularly copy the price).

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network at import; READ-only on data/frontend/predict_service (no write); no data/registry
write, no flag flip; never edits predict_service / odds_provider / domains / src / kernel.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_live_p0.py -q
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/live_p0.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE_DIR = _REPO_ROOT / "data" / "frontend" / "predict_service"

# The honest source labels (so a caller / test can tell prior from degrade).
SRC_PRIOR = "PRIOR"              # exact game_id match in the pregame snapshot
SRC_PRIOR_TEAMS = "PRIOR_TEAMS"  # exact id missed; resolved by UNIQUE leak-free team match
SRC_BASE = "BASE_FALLBACK"       # no usable prior on disk -> caller degrades to BASE

ReadJsonFn = Callable[[Path], Optional[Dict[str, Any]]]


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Read+parse a JSON file; None on any error (missing / malformed). Never raises."""
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001 -- a bad snapshot is "no prior", not a crash
        logger.debug("live_p0 read failed %s: %s", path, exc)
        return None


def _latest_path(sport: str, store_dir: Path) -> Path:
    return store_dir / str(sport).lower() / "latest.json"


def _prob01(value: Any) -> Optional[float]:
    """Coerce to a prob in [0,1]; None otherwise (never fabricated)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _norm_team(name: Any) -> str:
    """Normalize a team name for cross-provider matching: lowercase, alnum+space only.

    The live ESPN feed and the producer snapshot may key the same game under different
    provider id namespaces but carry the SAME ESPN-style team display names, so a
    normalized full-name compare bridges them without a brittle abbreviation map.
    """
    s = "".join(ch if ch.isalnum() else " " for ch in str(name or "").lower())
    return " ".join(s.split())


def _home_prior_from_pred(pred: Dict[str, Any]) -> Optional[float]:
    """Extract leak-free pregame P(home win) from one prediction record, or None.

    Reads pregame_probs.home_ml (the canonical leak-free pregame prior). Falls back to
    1 - away_ml when only the away side is present. NEVER reads a live/in-play field.
    """
    probs = pred.get("pregame_probs")
    if not isinstance(probs, dict):
        return None
    p_home = _prob01(probs.get("home_ml"))
    if p_home is not None:
        return p_home
    p_away = _prob01(probs.get("away_ml"))
    if p_away is not None:
        return 1.0 - p_away
    return None


def live_p0(sport: str, game_id: str, *,
            store_dir: Optional[Path] = None,
            read_json: Optional[ReadJsonFn] = None) -> Dict[str, Any]:
    """Return the leak-free pregame prior p0 for a live game, or a labelled BASE fallback.

    Reads data/frontend/predict_service/<sport>/latest.json (READ-ONLY) and matches the
    prediction by game_id. Returns {p0, source, game_id, sport} where source is SRC_PRIOR
    (p0 is the pregame P(home win)) or SRC_BASE (p0 is None -> caller degrades to BASE).
    NEVER raises, NEVER fabricates a 0.5 prior (an absent prior is BASE, honestly labelled).
    """
    base_dir = Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR
    reader = read_json if read_json is not None else _read_json
    gid = str(game_id)
    out: Dict[str, Any] = {"sport": str(sport).lower(), "game_id": gid,
                           "p0": None, "source": SRC_BASE}
    try:
        env = reader(_latest_path(sport, base_dir))
        if not isinstance(env, dict):
            return out
        if str(env.get("status", "ok")).lower() not in ("ok", ""):
            return out
        preds = env.get("predictions")
        if not isinstance(preds, list):
            return out
        for pred in preds:
            if not isinstance(pred, dict) or str(pred.get("game_id", "")) != gid:
                continue
            p0 = _home_prior_from_pred(pred)
            if p0 is not None:
                out["p0"] = float(p0)
                out["source"] = SRC_PRIOR
            return out
    except Exception as exc:  # noqa: BLE001 -- a store miss is just "no prior"
        logger.debug("live_p0(%s/%s) failed: %s", sport, game_id, exc)
    return out


def live_p0_resolved(sport: str, game_id: str, *,
                     home: Optional[str] = None, away: Optional[str] = None,
                     store_dir: Optional[Path] = None,
                     read_json: Optional[ReadJsonFn] = None) -> Dict[str, Any]:
    """Like live_p0, but on an exact game_id MISS fall back to a UNIQUE leak-free team match.

    THE GAP THIS CLOSES: the live ESPN feed keys a game by an ESPN id (401...) while the
    producer snapshot may key the SAME game under a different provider's id (a 10-digit
    fallback) -> live_p0's exact-id compare degrades to BASE even though the leak-free
    pregame prior IS on disk. When the live home/away team names are supplied we resolve
    by NORMALIZED team names instead.

    SAFETY (never trades on the wrong game): exact id ALWAYS wins first. The team fallback
    requires EXACTLY ONE snapshot record matching both normalized (home, away); 0 or >1
    matches (e.g. an MLB doubleheader -- same teams, two games) -> BASE_FALLBACK, never a
    guess. LEAK-FREE: only pregame team names + pregame_probs are read; no score/close/outcome.

    Returns {sport, game_id, p0, source} where source is PRIOR (exact id), PRIOR_TEAMS
    (unique team match) or BASE_FALLBACK. NEVER raises, NEVER fabricates a 0.5 prior.
    """
    exact = live_p0(sport, game_id, store_dir=store_dir, read_json=read_json)
    if exact.get("source") == SRC_PRIOR:
        return exact
    out: Dict[str, Any] = dict(exact)  # carries sport/game_id, p0=None, source=BASE
    nh, na = _norm_team(home), _norm_team(away)
    if not nh or not na:
        return out
    base_dir = Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR
    reader = read_json if read_json is not None else _read_json
    try:
        env = reader(_latest_path(sport, base_dir))
        if not isinstance(env, dict) or not isinstance(env.get("predictions"), list):
            return out
        if str(env.get("status", "ok")).lower() not in ("ok", ""):
            return out
        matches = []
        for pred in env["predictions"]:
            if not isinstance(pred, dict):
                continue
            if _norm_team(pred.get("home")) == nh and _norm_team(pred.get("away")) == na:
                p0 = _home_prior_from_pred(pred)
                if p0 is not None:
                    matches.append(float(p0))
        if len(matches) == 1:  # unique-or-BASE: ambiguity (doubleheader) -> BASE, never guess
            out["p0"] = matches[0]
            out["source"] = SRC_PRIOR_TEAMS
    except Exception as exc:  # noqa: BLE001 -- a store miss is just "no prior"
        logger.debug("live_p0_resolved(%s/%s) failed: %s", sport, game_id, exc)
    return out


def p0_for(sport: str, game_id: str, *,
           store_dir: Optional[Path] = None,
           read_json: Optional[ReadJsonFn] = None) -> Optional[float]:
    """Convenience: just the leak-free pregame prior (None on BASE_FALLBACK).

    For live_state / the daytrader pairing which only need the float to thread into
    serve_ingame / predict_live. None -> the served number honestly degrades to BASE.
    """
    return live_p0(sport, game_id, store_dir=store_dir, read_json=read_json).get("p0")


def main(argv: Optional[list] = None) -> int:
    import sys
    args = list(argv) if argv is not None else sys.argv[1:]
    sport = args[0] if len(args) > 0 else "nba"
    gid = args[1] if len(args) > 1 else ""
    print(json.dumps(live_p0(sport, gid), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_STORE_DIR", "SRC_PRIOR", "SRC_PRIOR_TEAMS", "SRC_BASE",
           "live_p0", "live_p0_resolved", "p0_for"]
