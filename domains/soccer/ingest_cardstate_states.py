"""domains.soccer.ingest_cardstate_states -- in-game MAN-ADVANTAGE detail layer ingest.

A red card (man-advantage) is the single most decisive in-game soccer state, and the
margin-only base in-game corpus (soccer_states__<label>.parquet) does NOT carry it. This
module re-reads the SAME ESPN match `summary` `commentary` stream we already fetch for the
shot layer (zero new network tier) and builds a leak-free AS-OF-MINUTE additive detail
trajectory on the SAME 5-min grid as the base:

  red_diff_<idx>       = (home reds up to minute) - (away reds up to minute)
  yellow_diff_<idx>    = (home yellows up to minute) - (away yellows up to minute)
  sub_count_diff_<idx> = (home subs up to minute)   - (away subs up to minute)
  shot_zone_diff_<idx> = coarse home-vs-away box-proximity shot share up to minute

PRECONDITION VERIFIED (zero-network probe, MOAT MUST-FIX #6): commentary play.type.text
carries 'Red Card' (type id 93), 'Yellow Card' (94), 'Substitution', and shots with a
fieldPositionX. Red cards are SPARSE (man-advantage is rare) but present and attributable.

Side attribution mirrors ingest_shot_states.py EXACTLY: ESPN commentary play.team is None,
so we join play.participants[0].athlete.displayName -> rosters -> 'home'/'away'. An
UNATTRIBUTABLE card (taker not in either roster, or no participant) is DROPPED, never
assigned a side (anchor: ingest_shot_states.py:136 -- drop, don't guess).

Output: data/cache/ingame/soccer_cardstates__<label>.parquet, schema:
  game_id, asof_idx, red_diff, yellow_diff, sub_count_diff, shot_zone_diff,
  home_reds, away_reds
keyed to merge onto soccer_states__<label>.parquet by (game_id, asof_idx).

Leak-free: a grid point at minute m counts ONLY events with clock <= m (step function, no
lookahead). A red card at min 40 sets red_diff for ticks >= 40 ONLY, 0 before. Final-total
boxscore card counts are NEVER used (those are leaky in-game).

INVARIANTS: <=300 LOC; ASCII only; no API keys; no src.*/kernel.* imports.
CLI: python -m domains.soccer.ingest_cardstate_states --labels eng1 ger1
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

# Event-kind classifier from commentary play.type.text (lowercased). A red card may be a
# direct 'red card' or a 'second yellow card'/'yellow-red'; both confer man-advantage.
_RED_RE = re.compile(r"red card|second yellow|yellow[ -]?red")
_YELLOW_RE = re.compile(r"yellow card")
_SUB_RE = re.compile(r"substitution|substitute")


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


def _kind(type_text: str) -> Optional[str]:
    """Classify a commentary play into 'red'/'yellow'/'sub', else None. Red checked first
    so a 'second yellow card' (a sending-off) counts as a red, not a yellow."""
    tl = (type_text or "").lower()
    if _RED_RE.search(tl):
        return "red"
    if _YELLOW_RE.search(tl):
        return "yellow"
    if _SUB_RE.search(tl):
        return "sub"
    return None


def _zone_share(play: dict) -> Optional[float]:
    """Coarse box-proximity score in [0,1] for a SHOT play from fieldPositionX (taker-
    relative attacking progress: ~1.0 == at goal). None if absent. Used only as a soft
    shot-quality-by-zone proxy for shot_zone_diff -- NOT true xG and never location-exact."""
    tl = ((play.get("type") or {}).get("text") or "").lower()
    if not (tl.startswith("shot") or tl.startswith("goal") or "penalty" in tl):
        return None
    fx = play.get("fieldPositionX")
    if fx is None:
        return None
    try:
        x = float(fx)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, x))


def card_events(payload: dict) -> List[Tuple[float, str, str, float]]:
    """Return [(minute, side, kind, zone)] for ATTRIBUTABLE card/sub/shot-zone plays. Pure.

    kind in {'red','yellow','sub','shot'}; zone is the box-proximity share for a 'shot'
    kind (0.0 for non-shot kinds). An unattributable event (taker not in roster) is DROPPED.
    """
    home_id = _home_id(payload)
    if not home_id:
        return []
    side_map = _name_to_side(payload, home_id)
    out: List[Tuple[float, str, str, float]] = []
    for c in (payload.get("commentary") or []):
        pl = c.get("play") or {}
        kind = _kind((pl.get("type") or {}).get("text", ""))
        zone = _zone_share(pl)
        if kind is None and zone is None:
            continue
        minute = _clock_minute(pl)
        if minute is None:
            continue
        parts = pl.get("participants") or []
        nm = _norm((parts[0].get("athlete") or {}).get("displayName", "")) if parts else ""
        side = side_map.get(nm)
        if side is None:
            continue   # unattributable -> drop, never fabricate a side (shot_states.py:136)
        if kind is not None:
            out.append((minute, side, kind, 0.0))
        else:
            out.append((minute, side, "shot", float(zone)))
    return out


def build_card_states(game_id: str,
                      events: List[Tuple[float, str, str, float]]) -> List[dict]:
    """Build cumulative per-grid-point man-advantage rows (leak-free step function).

    At grid minute m, every diff counts ONLY events with event-minute <= m. shot_zone_diff
    is (home cumulative zone sum) - (away cumulative zone sum) over shot kinds up to m.
    """
    rows: List[dict] = []
    for idx, minute in enumerate(_GRID):
        def cnt(side: str, kind: str) -> int:
            return sum(1 for m, sd, k, _ in events
                       if m <= minute and sd == side and k == kind)

        def zsum(side: str) -> float:
            return sum(z for m, sd, k, z in events
                       if m <= minute and sd == side and k == "shot")

        hr, ar = cnt("home", "red"), cnt("away", "red")
        hy, ay = cnt("home", "yellow"), cnt("away", "yellow")
        hs, as_ = cnt("home", "sub"), cnt("away", "sub")
        rows.append({
            "game_id": str(game_id), "asof_idx": idx,
            "red_diff": float(hr - ar),
            "yellow_diff": float(hy - ay),
            "sub_count_diff": float(hs - as_),
            "shot_zone_diff": float(zsum("home") - zsum("away")),
            "home_reds": hr, "away_reds": ar,
        })
    return rows


def ingest_label(label: str, getter: Optional[Callable] = None,
                 max_events: Optional[int] = None,
                 out_dir: Optional[Path] = None) -> Path:
    """For every game_id in soccer_states__<label>, fetch card/sub events; write cardstates.

    EVERY game emits its 19-row grid (an all-zero grid is the honest 'no man-advantage'
    state and is a valid base-equal detail row, unlike the shot layer where all-zero means
    no attribution). Games where NO red card ever occurs still contribute red_diff==0 rows.
    """
    outd = Path(out_dir) if out_dir else _STATE_DIR
    league = _LABEL2LEAGUE.get(label, label)
    base = outd / f"soccer_states__{label}.parquet"
    if not base.exists():
        raise FileNotFoundError(f"base states missing: {base}")
    ids = list(pd.read_parquet(base)["game_id"].astype(str).unique())
    if max_events is not None:
        ids = ids[:max_events]
    rows: List[dict] = []
    games_with_red = 0
    for eid in ids:
        payload = _get(_SUMMARY.format(l=league, e=eid), getter)
        events = card_events(payload) if payload else []
        st = build_card_states(eid, events)
        if any(r["home_reds"] or r["away_reds"] for r in st):
            games_with_red += 1
        rows.extend(st)
        time.sleep(0.08)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    out = outd / f"soccer_cardstates__{label}.parquet"
    if not df.empty:
        df.to_parquet(out, index=False)
    log.info("label=%s games=%d games_with_red=%d rows=%d -> %s",
             label, len(ids), games_with_red, len(df), out)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest soccer in-game man-advantage states.")
    ap.add_argument("--labels", nargs="+", default=["eng1", "ger1"])
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
