"""domains.soccer.ingest_shot_states -- in-game SHOT-PRESSURE detail layer ingest.

For each ESPN event already in a soccer_states__<label>.parquet corpus, fetch the
match summary `commentary` stream (timestamped shot plays), attribute each shot to
the HOME or AWAY side via the match `rosters` (player displayName -> side), and build
a leak-free AS-OF-MINUTE cumulative shot-pressure trajectory on the SAME 5-min grid:

  shot_diff_<idx>   = (home shots up to minute) - (away shots up to minute)
  xgproxy_diff_<idx>= sum K(shot_type) home  - sum K(shot_type) away  up to minute

K weights are a CRUDE corpus-rough finishing-probability proxy by shot TYPE
(on-target > blocked/off > woodwork), NOT true xG (no shot-location quality on disk).

Why side attribution via roster (not commentary.team): ESPN commentary play.team is
None and play.fieldPositionX is taker-relative, so neither disambiguates side. The
play.participants[0].athlete.displayName DOES, joined to rosters -> reliable side.

Output: data/cache/ingame/soccer_shotstates__<label>.parquet, schema:
  game_id, asof_idx, shot_diff, xgproxy_diff, home_shots, away_shots
keyed to merge onto soccer_states__<label>.parquet by (game_id, asof_idx).

Leak-free: a grid point at minute m counts ONLY shots with clock <= m (step function,
no lookahead). Final-total boxscore stats are NEVER used (those are leaky in-game).

INVARIANTS: <=300 LOC; ASCII only; no API keys; no src.*/kernel.* imports.
CLI: python -m domains.soccer.ingest_shot_states --labels eng1 esp1
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_REPO = Path(__file__).resolve().parents[2]
_STATE_DIR = _REPO / "data" / "cache" / "ingame"
_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{l}/summary?event={e}"
_GRID = list(range(0, 91, 5))   # 19 grid points, mirror ingest_soccer_states
_LABEL2LEAGUE = {"eng1": "eng.1", "esp1": "esp.1", "ger1": "ger.1", "ita1": "ita.1",
                 "fra1": "fra.1"}

# Crude shot-type finishing-probability proxy weights (xG-proxy, NOT true xG).
_SHOT_K: Dict[str, float] = {
    "shot on target": 0.30, "goal": 0.30, "goal - header": 0.30,
    "penalty - scored": 0.75, "penalty - saved": 0.75,
    "shot blocked": 0.06, "shot off target": 0.05, "shot hit woodwork": 0.10,
}


def _norm(name: str) -> str:
    n = unicodedata.normalize("NFD", name.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z ]", " ", n).split())


def _get(url: str, getter: Optional[Callable] = None) -> dict:
    if getter is not None:
        return getter(url)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                log.warning("ESPN fetch failed url=%s err=%s", url, exc)
    return {}


def _home_id(payload: dict) -> str:
    comps = ((payload.get("header") or {}).get("competitions") or [{}])[0]
    for c in (comps.get("competitors") or []):
        if c.get("homeAway") == "home":
            return str((c.get("team") or {}).get("id", ""))
    return ""


def _name_to_side(payload: dict, home_id: str) -> Dict[str, str]:
    """Map normalised player displayName -> 'home'/'away' from the rosters block."""
    out: Dict[str, str] = {}
    for r in (payload.get("rosters") or []):
        tid = str((r.get("team") or {}).get("id", ""))
        side = "home" if tid == home_id else "away"
        for a in (r.get("roster") or []):
            nm = _norm((a.get("athlete") or {}).get("displayName") or "")
            if nm:
                out[nm] = side
    return out


def _clock_minute(play: dict) -> Optional[float]:
    """Elapsed minute from commentary clock displayValue ('67'' or "45'+3'")."""
    dv = (play.get("clock") or {}).get("displayValue") or ""
    m = re.match(r"(\d+)'(?:\+(\d+)')?", dv.strip())
    if not m:
        return None
    base = float(m.group(1))
    add = float(m.group(2)) if m.group(2) else 0.0
    return min(base + add, 90.0)


def shot_events(payload: dict) -> List[Tuple[float, str, float]]:
    """Return [(minute, side, k_weight)] for attributable shot plays. Pure."""
    home_id = _home_id(payload)
    if not home_id:
        return []
    side_map = _name_to_side(payload, home_id)
    out: List[Tuple[float, str, float]] = []
    for c in (payload.get("commentary") or []):
        pl = c.get("play") or {}
        t = (pl.get("type") or {}).get("text", "")
        tl = t.lower()
        if not (tl.startswith("shot") or tl.startswith("goal") or "penalty" in tl):
            continue
        k = _SHOT_K.get(tl)
        if k is None:
            continue
        minute = _clock_minute(pl)
        if minute is None:
            continue
        parts = pl.get("participants") or []
        nm = _norm((parts[0].get("athlete") or {}).get("displayName", "")) if parts else ""
        side = side_map.get(nm)
        if side is None:
            continue   # unattributable -> drop, never fabricate a side
        out.append((minute, side, k))
    return out


def build_shot_states(game_id: str, shots: List[Tuple[float, str, float]]) -> List[dict]:
    """Build cumulative per-grid-point shot-pressure rows (leak-free step function)."""
    rows: List[dict] = []
    for idx, minute in enumerate(_GRID):
        hs = sum(1 for m, sd, _ in shots if m <= minute and sd == "home")
        as_ = sum(1 for m, sd, _ in shots if m <= minute and sd == "away")
        hx = sum(k for m, sd, k in shots if m <= minute and sd == "home")
        ax = sum(k for m, sd, k in shots if m <= minute and sd == "away")
        rows.append({
            "game_id": str(game_id), "asof_idx": idx,
            "shot_diff": float(hs - as_), "xgproxy_diff": float(hx - ax),
            "home_shots": hs, "away_shots": as_,
        })
    return rows


def ingest_label(label: str, getter: Optional[Callable] = None,
                 max_events: Optional[int] = None,
                 out_dir: Optional[Path] = None) -> Path:
    """For every game_id in soccer_states__<label>, fetch shots; write shotstates."""
    outd = Path(out_dir) if out_dir else _STATE_DIR
    league = _LABEL2LEAGUE.get(label, label)
    base = outd / f"soccer_states__{label}.parquet"
    if not base.exists():
        raise FileNotFoundError(f"base states missing: {base}")
    ids = list(pd.read_parquet(base)["game_id"].astype(str).unique())
    if max_events is not None:
        ids = ids[:max_events]
    rows: List[dict] = []
    ok = empty = 0
    for eid in ids:
        payload = _get(_SUMMARY.format(l=league, e=eid), getter)
        shots = shot_events(payload) if payload else []
        st = build_shot_states(eid, shots)
        # only emit if at least one shot was attributed (else all-zero, no signal)
        if any(r["home_shots"] or r["away_shots"] for r in st):
            rows.extend(st)
            ok += 1
        else:
            empty += 1
        time.sleep(0.08)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    out = outd / f"soccer_shotstates__{label}.parquet"
    if not df.empty:
        df.to_parquet(out, index=False)
    log.info("label=%s games_with_shots=%d empty=%d rows=%d -> %s",
             label, ok, empty, len(df), out)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest soccer in-game shot-pressure states.")
    ap.add_argument("--labels", nargs="+", default=["eng1", "esp1"])
    ap.add_argument("--max-events", type=int, default=None)
    args = ap.parse_args(argv)
    for label in args.labels:
        out = ingest_label(label, max_events=args.max_events)
        if out.exists():
            df = pd.read_parquet(out)
            print("label=%s games=%d rows=%d -> %s"
                  % (label, df["game_id"].nunique(), len(df), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
