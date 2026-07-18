"""scripts.platformkit.answers.winprob_dispatch -- LANE F: win-probability resolver.

Fail-closed envelope wrapper around the ALREADY-validated buyer-facing predictor
(scripts/platformkit/predict_matchup.py). This module authors NO new predictive
number -- it runs that CLI as a SUBPROCESS (never imports it -- the concept/
forecast decoupling guard), parses its JSON, and quotes the probability and any
component/driver fields VERBATIM back out in the standard resolver envelope
(mirrors scripts/platformkit/analytics_verify/answers.py's contract):
    {status: "ok"|"refused"|"not_supported"|"no_data", category, sport,
     source_artifact, as_of, ...}

Fails closed:
  - nonzero exit / unparseable stdout (incl. the "corpus unavailable" plain-text
    line predict_matchup prints on a fresh clone)  -> "no_data" + stderr/stdout tail
  - subprocess timeout (60s)                        -> "no_data"

Run: python -m scripts.platformkit.answers.winprob_dispatch --sport mlb --home NYY --away BOS
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_ARTIFACT = "scripts/platformkit/predict_matchup.py"
_TIMEOUT_S = 60

# generic ingame_state key -> predict_matchup CLI flag (sport-appropriate
# interpretation happens inside predict_matchup's own live_kwargs(); we just
# pass through whatever keys the caller supplies).
_INGAME_FLAGS = {
    "elapsed": "--elapsed", "inning": "--inning", "half": "--half",
    "home_score": "--home-score", "away_score": "--away-score",
    "sets_home": "--sets-home", "sets_away": "--sets-away",
    "games_home": "--games-home", "games_away": "--games-away",
    "surface": "--surface",
}


def _ascii_tail(text: str, n: int = 800) -> str:
    return text[-n:].encode("ascii", errors="replace").decode("ascii").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_args(sport: str, home: str, away: str,
                ingame_state: Optional[Dict[str, Any]]) -> list[str]:
    args = ["--sport", sport, "--home", home, "--away", away, "--json", "--no-banner"]
    for key, flag in _INGAME_FLAGS.items():
        val = (ingame_state or {}).get(key)
        if val is not None:
            args += [flag, str(val)]
    return args


def dispatch(sport: str, home: str, away: str,
            ingame_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run predict_matchup.py as a subprocess and return the standard envelope.

    Never imports predict_matchup -- always `sys.executable -m ...` so the
    forecast (predictor) stays decoupled from this concept (resolver) layer.
    """
    base = {"category": "winprob", "sport": sport, "source_artifact": _SOURCE_ARTIFACT,
            "as_of": _now_iso(), "home": home, "away": away}
    args = _build_args(sport, home, away, ingame_state)
    cmd = [sys.executable, "-m", "scripts.platformkit.predict_matchup", *args]
    try:
        proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True,
                              text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {**base, "status": "no_data",
                "note": f"predict_matchup timed out after {_TIMEOUT_S}s"}

    if proc.returncode != 0:
        return {**base, "status": "no_data",
                "note": f"predict_matchup exited {proc.returncode}: "
                        f"{_ascii_tail(proc.stderr or proc.stdout)}"}

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # e.g. the "corpus unavailable on this clone" plain-text line
        # (predict_matchup prints this and exits 0 -- never raises)
        return {**base, "status": "no_data",
                "note": f"predict_matchup produced no JSON: {_ascii_tail(proc.stdout)}"}

    out: Dict[str, Any] = {**base, "status": "ok",
                           "edge_claimed": result.get("edge_claimed"),
                           "framing": result.get("framing"),
                           "pregame": result.get("pregame")}
    if "ingame" in result:
        out["ingame"] = result["ingame"]
    elif "ingame_note" in result:
        out["ingame_note"] = result["ingame_note"]
    # convenience top-level probability, quoted verbatim off whichever block is live
    prob_block = out.get("ingame") or out.get("pregame") or {}
    if "p_home_win" in prob_block:
        out["p_home_win"] = prob_block["p_home_win"]

    # State-bucket calibration caveat (additive, never changes status/fields above).
    # Lazy import to keep this module import-light; never let a caveat-layer bug
    # break the envelope -- fail closed to an honest "lookup failed" caveat.
    if ingame_state:
        try:
            from scripts.platformkit.calibration_grid import caveats as _caveats
            cal = _caveats.caveat_for(sport, ingame_state)
            out["state_bucket"] = cal.get("state_bucket")
            out["bucket_calibration"] = cal
        except Exception:  # noqa: BLE001 -- caveat lookup must never break the envelope
            out["state_bucket"] = None
            out["bucket_calibration"] = {"can_price": False, "reason": "caveat lookup failed"}
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Win-probability resolver over predict_matchup.py")
    ap.add_argument("--sport", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--elapsed", type=float, default=None)
    ap.add_argument("--inning", type=int, default=None)
    ap.add_argument("--half", choices=["top", "bottom"], default=None)
    ap.add_argument("--home-score", type=int, default=None, dest="home_score")
    ap.add_argument("--away-score", type=int, default=None, dest="away_score")
    ap.add_argument("--sets-home", type=int, default=None, dest="sets_home")
    ap.add_argument("--sets-away", type=int, default=None, dest="sets_away")
    ap.add_argument("--games-home", type=int, default=None, dest="games_home")
    ap.add_argument("--games-away", type=int, default=None, dest="games_away")
    ap.add_argument("--surface", default=None)
    a = ap.parse_args(argv)
    ingame_state = {k: v for k, v in {
        "elapsed": a.elapsed, "inning": a.inning, "half": a.half,
        "home_score": a.home_score, "away_score": a.away_score,
        "sets_home": a.sets_home, "sets_away": a.sets_away,
        "games_home": a.games_home, "games_away": a.games_away,
        "surface": a.surface,
    }.items() if v is not None}
    envelope = dispatch(a.sport, a.home, a.away, ingame_state or None)
    print(json.dumps(envelope, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
