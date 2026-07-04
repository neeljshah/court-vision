"""domains.soccer.ingame_fotmob -- LIVE xG ingest from FotMob (keyless, plain urllib).

WHY: in-game soccer had no live shot-quality signal (xG/xGOT/SoT), only
score+minute from ESPN. FotMob's public data API exposes per-shot xG,
per-minute momentum, and match stats with NO key/auth (verified 2026-07-03:
51 real matches / real xG on 20260703 WC round-of-32 -- see report).

ENDPOINTS (keyless GET, UA header only -- no stealth needed):
  .../api/data/matches?date=YYYYMMDD       -> day's matches (list)
  .../api/data/matchDetails?matchId=<id>   -> per-match detail
TRAP: `/api/matches` (no `/data/`) 404s -- wrong path, NOT a block.

AS-OF DISCIPLINE: `content.shotmap.shots[]` is a flat list of EVERY shot,
each with absolute `min` (+`minAdded` stoppage). asof_state_at(detail,
cutoff) sums only shots with effective minute <= cutoff -- a shot at minute
60 must NEVER leak into a minute-45 row (enforced by
test_asof_no_future_leak: monotonic cutoffs never see a later shot).

FIELDS AS-OF A CUTOFF MINUTE: xg_home/away, xgot_home/away (sum of
expectedGoals/OnTarget); sot_diff (on-target shot count diff); momentum_last10
(mean of momentum.main.data in (cutoff-10, cutoff]); red_card_state
(home_reds, away_reds) from matchFacts events (type=='Card', card=='Red').
big_chance_diff is ALWAYS None: shotmap has no per-shot isBigChance flag
(confirmed absent, 3 sampled WC matches) and content.stats' "Big chances" is
FINAL-match only (would leak as-of) -- an honest gap, not a fabrication.
Home/away split uses content.general.homeTeam.id vs shot teamId --
fetch_match_detail MERGES the top-level `general` block into the returned
dict (FotMob puts homeTeam/awayTeam id there, NOT inside `content` --
verified against a real payload 2026-07-03).

TEAM MATCHING (unambiguity guard, same convention as
scripts.platformkit.ingame.soccer_outcome.SoccerOutcomeResolver): case-
insensitive substring match, either direction, against our fixture's
home/away names (e.g. ingame_live_state.live_states('soccer_intl')). BOTH
sides must match distinct legs or the pair is None -- never guess a side.

PERSISTENCE: append-only JSONL sidecars, one per FotMob matchId:
  data/domains/soccer_intl/fotmob_live/<matchId>.jsonl
Each line = one snapshot {"fetch_ts": iso, "cutoff_min": float, ...fields}.
Append-only avoids read-modify-write races; dedup is the reader's job.

WIRE SPEC (future lane -- NOT applied this wave). Additive lines for
inplay_capture_loop._extract's soccer branch:
    fx = match_to_fixture(fotmob_matches, out["home_display"], out["away_display"])
    if fx is not None:
        detail = fetch_match_detail(fx["id"])
        if detail is not None:
            out["fotmob_live_xg"] = asof_state_at(detail, out.get("minute") or 0.0)
No existing capture-loop file is touched by this module.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; ~1s pacing
between fetches; never raises; no $ fields; measurement/sidecar only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_ingame_fotmob.py -q
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
SIDECAR_DIR = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_live"

_UA = {"User-Agent": "Mozilla/5.0 (compatible; CourtVisionResearch/1.0)"}
_MATCHES_URL = "https://www.fotmob.com/api/data/matches?date={date}"
_DETAIL_URL = "https://www.fotmob.com/api/data/matchDetails?matchId={mid}"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get_json(url: str, timeout: float = 15.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 -- network flake must never crash a poller
        logger.debug("fotmob GET failed %s: %s", url, exc)
        return None


def fetch_matches_for_date(date_str: str,
                            getter: Callable[[str], Optional[dict]] = _http_get_json
                            ) -> List[dict]:
    """date_str = 'YYYYMMDD'. Flattens leagues[].matches[] -> one list. [] on any failure."""
    payload = getter(_MATCHES_URL.format(date=date_str))
    if not isinstance(payload, dict):
        return []
    out: List[dict] = []
    for lg in payload.get("leagues") or []:
        if not isinstance(lg, dict):
            continue
        out.extend(m for m in (lg.get("matches") or []) if isinstance(m, dict))
    return out


def fetch_match_detail(match_id: Any,
                        getter: Callable[[str], Optional[dict]] = _http_get_json
                        ) -> Optional[dict]:
    """matchDetails `content` + top-level `general` merged under
    content['general'] (see module docstring). None on any failure."""
    payload = getter(_DETAIL_URL.format(mid=match_id))
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if not isinstance(content, dict):
        return None
    gen = payload.get("general")
    if isinstance(gen, dict):
        content = dict(content)
        content["general"] = gen
    return content


def _names_align(a: Any, b: Any) -> bool:
    a, b = str(a or "").strip().lower(), str(b or "").strip().lower()
    return bool(a) and bool(b) and (a in b or b in a)


def match_to_fixture(fotmob_matches: List[dict], home_display: str, away_display: str
                      ) -> Optional[dict]:
    """FotMob match whose home/away names align (BOTH sides, order-
    respecting) with (home_display, away_display). None if no match or
    ambiguous (>1) -- never a guess."""
    hits = []
    for m in fotmob_matches:
        h = ((m.get("home") or {}).get("name")
             or (m.get("home") or {}).get("longName") or "")
        a = ((m.get("away") or {}).get("name")
             or (m.get("away") or {}).get("longName") or "")
        if _names_align(home_display, h) and _names_align(away_display, a):
            hits.append(m)
    if len(hits) == 1:
        return hits[0]
    return None


def _eff_minute(shot_or_event: dict) -> Optional[float]:
    """min + minAdded/overloadTime -> one comparable float minute."""
    base = shot_or_event.get("min", shot_or_event.get("time"))
    if base is None:
        return None
    try:
        base = float(base)
    except (TypeError, ValueError):
        return None
    extra = shot_or_event.get("minAdded") or shot_or_event.get("overloadTime") or 0
    try:
        extra = float(extra)
    except (TypeError, ValueError):
        extra = 0.0
    return base + extra


def asof_state_at(detail: dict, cutoff_min: float) -> Dict[str, Any]:
    """As-of live-xG state for *detail* at *cutoff_min*. STRICT as-of: a
    shot/event with eff_minute > cutoff_min is NEVER included. Never raises."""
    out: Dict[str, Any] = {
        "cutoff_min": float(cutoff_min),
        "xg_home": 0.0, "xg_away": 0.0,
        "xgot_home": 0.0, "xgot_away": 0.0,
        "sot_diff": 0, "big_chance_diff": None,  # not derivable as-of; see module docstring
        "momentum_last10": None,
        "red_card_state": (0, 0),
    }
    try:
        home_id = ((detail.get("general") or {}).get("homeTeam") or {}).get("id")
        sot_home = sot_away = 0
        for s in (detail.get("shotmap") or {}).get("shots") or []:
            em = _eff_minute(s)
            if em is None or em > cutoff_min:
                continue
            xg, xgot = float(s.get("expectedGoals") or 0.0), float(s.get("expectedGoalsOnTarget") or 0.0)
            on_target = bool(s.get("isOnTarget"))
            if home_id is not None and s.get("teamId") == home_id:
                out["xg_home"] += xg; out["xgot_home"] += xgot
                sot_home += int(on_target)
            else:
                out["xg_away"] += xg; out["xgot_away"] += xgot
                sot_away += int(on_target)
        out["sot_diff"] = sot_home - sot_away
        for k in ("xg_home", "xg_away", "xgot_home", "xgot_away"):
            out[k] = round(out[k], 4)
    except Exception as exc:  # noqa: BLE001 -- shot aggregation must never crash a poller
        logger.debug("asof_state_at shots failed: %s", exc)

    try:
        mom = ((detail.get("momentum") or {}).get("main") or {}).get("data") or []
        pts = [float(p["value"]) for p in mom
               if isinstance(p, dict) and p.get("minute") is not None
               and cutoff_min - 10 < float(p["minute"]) <= cutoff_min]
        if pts:
            out["momentum_last10"] = round(sum(pts) / len(pts), 3)
    except Exception as exc:  # noqa: BLE001
        logger.debug("asof_state_at momentum failed: %s", exc)

    try:
        events = ((detail.get("matchFacts") or {}).get("events") or {}).get("events") or []
        reds_home = reds_away = 0
        for e in events:
            if not isinstance(e, dict) or e.get("type") != "Card" or e.get("card") != "Red":
                continue
            em = _eff_minute(e)
            if em is None or em > cutoff_min:
                continue
            reds_home += int(bool(e.get("isHome")))
            reds_away += int(not e.get("isHome"))
        out["red_card_state"] = (reds_home, reds_away)
    except Exception as exc:  # noqa: BLE001
        logger.debug("asof_state_at cards failed: %s", exc)

    return out


def sidecar_path(match_id: Any) -> Path:
    return SIDECAR_DIR / f"{match_id}.jsonl"


def append_snapshot(match_id: Any, row: Dict[str, Any]) -> None:
    """Append one snapshot line. Best-effort; never raises."""
    try:
        SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
        row = dict(row)
        row.setdefault("fetch_ts", _utc_iso())
        with sidecar_path(match_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("append_snapshot failed for %s: %s", match_id, exc)


def poll_once(date_str: Optional[str] = None, *, sleep_s: float = 1.0,
              our_fixtures: Optional[List[dict]] = None) -> Dict[str, Any]:
    """One poll pass: fetch today's FotMob matches, keep only STARTED-and-not-
    FINISHED ones, append one as-of snapshot each (cutoff = latest shot
    minute). *our_fixtures* (optional list of {'home_display','away_display'}
    dicts, e.g. ingame_live_state.live_states('soccer_intl')) restricts to
    matched fixtures only; omitted = poll ALL live FotMob matches for the
    date (standalone/offline runs). Returns {n_matches, n_matched,
    n_snapshots}; never raises."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y%m%d")
    matches = fetch_matches_for_date(date_str)
    summary = {"date": date_str, "n_matches": len(matches), "n_matched": 0, "n_snapshots": 0}

    live = []
    for m in matches:
        st = m.get("status") or {}
        if st.get("started") and not st.get("finished") and not st.get("cancelled"):
            live.append(m)

    targets = live
    if our_fixtures:
        matched = []
        for fx in our_fixtures:
            hit = match_to_fixture(live, fx.get("home_display", ""), fx.get("away_display", ""))
            if hit is not None:
                matched.append(hit)
        targets = matched

    summary["n_matched"] = len(targets)
    for m in targets:
        detail = fetch_match_detail(m["id"])
        if detail is None:
            time.sleep(sleep_s)
            continue
        shots = (detail.get("shotmap") or {}).get("shots") or []
        cutoff = max((_eff_minute(s) or 0.0) for s in shots) if shots else 0.0
        row = asof_state_at(detail, cutoff)
        row["match_id"] = m["id"]
        row["home"] = (m.get("home") or {}).get("name")
        row["away"] = (m.get("away") or {}).get("name")
        append_snapshot(m["id"], row)
        summary["n_snapshots"] += 1
        time.sleep(sleep_s)
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    summary = poll_once()
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "fetch_matches_for_date", "fetch_match_detail", "match_to_fixture",
    "asof_state_at", "append_snapshot", "sidecar_path", "poll_once", "SIDECAR_DIR",
]
