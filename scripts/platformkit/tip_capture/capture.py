"""scripts.platformkit.tip_capture.capture -- the four forward-capture sources.

Each function wraps an EXISTING, already-tested in-repo fetcher and fails
open (a per-source error never sinks the row; it is recorded as a status
field instead). No new transport, no new team-matching logic -- see
daemon.py's module docstring for the why.

  1. INJURY/LINEUP state  -- edge_engine.injury_facts.fetch_injuries (ESPN
     injuries feed; whole-sport snapshot -- ponytail: a reliable per-game
     team filter does not exist here, and every row already carries its own
     team name, so the caller/consumer can filter downstream).
  2. SCHEDULE + tip time   -- odds_provider.espn.EspnProvider (ESPN
     scoreboard; already handles the stale-echo guard).
  3. OUR FROZEN PRIOR      -- answers.winprob_dispatch.dispatch, itself a
     subprocess wrapper over predict_matchup.py.
  4. OPTIONAL market price -- odds_provider.kalshi/polymarket, kalshi paced
     via kalshi_rate_governor caller="tip_capture" (unregistered caller ->
     the governor's small default 0.05 share; deliberately conservative).
"""
from __future__ import annotations

import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.answers import winprob_dispatch
from scripts.platformkit.edge_engine import injury_facts
from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.espn import EspnProvider
from scripts.platformkit.odds_provider.kalshi import KalshiProvider
from scripts.platformkit.odds_provider.polymarket import PolymarketProvider
from scripts.platformkit.odds_provider.team_resolver import _CODE_TO_NICK, canonical

from .schedule import parse_iso

_REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNOR_CALLER = "tip_capture"


def _code_for(sport: str, display_name: str) -> str:
    """Best-effort ESPN full-name -> short venue code (BOS/LAL/NYY/...), reusing
    team_resolver's existing per-sport code maps. Falls back to the raw
    display name (predict_matchup/dispatch degrade to no_data, never crash)."""
    code_map = _CODE_TO_NICK.get(sport)
    if not code_map:
        return display_name
    key = canonical(sport, display_name)
    nick = key.split(":", 1)[1] if ":" in key else ""
    for code, n in code_map.items():
        if n == nick:
            return code
    return display_name


def fetch_schedule(sport: str, *, provider: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Upcoming games for *sport* via the ESPN scoreboard. [] on any failure."""
    prov = provider if provider is not None else EspnProvider()
    try:
        events = prov.fetch(sport)
    except Exception:  # noqa: BLE001
        return []
    if is_unavailable(events):
        return []
    out: List[Dict[str, Any]] = []
    for ev in events:
        tip = parse_iso(getattr(ev, "commence_time", None))
        if tip is None:
            continue
        out.append({
            "sport": sport, "game_id": str(getattr(ev, "event_id", "") or ""),
            "home": ev.home, "away": ev.away, "tip_time": tip.isoformat(),
        })
    return out


def capture_injuries(sport: str, *, fetch_fn: Optional[Callable] = None) -> Dict[str, Any]:
    fn = fetch_fn if fetch_fn is not None else injury_facts.fetch_injuries
    try:
        return {"status": "ok", "rows": fn(sport)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": type(exc).__name__}


def capture_winprob(sport: str, home: str, away: str,
                    *, dispatch_fn: Optional[Callable] = None) -> Dict[str, Any]:
    fn = dispatch_fn if dispatch_fn is not None else winprob_dispatch.dispatch
    try:
        return fn(sport, _code_for(sport, home), _code_for(sport, away))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": type(exc).__name__}


def capture_market(sport: str, *, kalshi_fn: Optional[Callable] = None,
                   polymarket_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Best-effort pregame price snapshot. Independently fail-open per venue."""
    k_fn = kalshi_fn or (lambda s: KalshiProvider(governor_caller=GOVERNOR_CALLER).fetch(s))
    p_fn = polymarket_fn or (lambda s: PolymarketProvider().fetch(s))
    out: Dict[str, Any] = {}
    for name, fn in (("kalshi", k_fn), ("polymarket", p_fn)):
        try:
            res = fn(sport)
            if is_unavailable(res):
                out[name] = {"status": "unavailable"}
            else:
                out[name] = {"status": "ok",
                             "events": [asdict(e) if not isinstance(e, dict) else e
                                        for e in res]}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"status": "error", "error": type(exc).__name__}
    return out


def git_sha() -> str:
    """Best-effort short-circuit git HEAD sha -- the "model version" stamp
    (predict_matchup carries no version field of its own)."""
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT),
                              capture_output=True, text=True, timeout=5)
        sha = proc.stdout.strip()
        return sha if proc.returncode == 0 and sha else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def build_row(game: Dict[str, Any], pass_name: str, *, now: datetime,
             deps: Optional[Dict[str, Callable]] = None,
             include_market: bool = True) -> Dict[str, Any]:
    """Capture everything for one (game, capture_pass) -> the store row."""
    deps = deps or {}
    payload: Dict[str, Any] = {
        "injuries": capture_injuries(game["sport"], fetch_fn=deps.get("injuries")),
        "winprob": capture_winprob(game["sport"], game["home"], game["away"],
                                   dispatch_fn=deps.get("winprob")),
    }
    if include_market:
        payload["market"] = capture_market(game["sport"], kalshi_fn=deps.get("kalshi"),
                                           polymarket_fn=deps.get("polymarket"))
    return {
        "capture_ts": now.isoformat(), "sport": game["sport"],
        "game_id": game["game_id"], "home": game["home"], "away": game["away"],
        "tip_time": game["tip_time"], "capture_pass": pass_name,
        "source": "tip_capture", "model_sha": git_sha(), "payload": payload,
    }


__all__ = [
    "GOVERNOR_CALLER", "fetch_schedule", "capture_injuries", "capture_winprob",
    "capture_market", "git_sha", "build_row",
]
