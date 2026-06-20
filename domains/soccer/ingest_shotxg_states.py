"""domains.soccer.ingest_shotxg_states -- in-game LOCATION-xG-proxy detail layer ingest.

NETWORK tier (zero-INCREMENTAL vs the base in-game corpus): this module re-reads the
SAME ESPN match `summary` `commentary` stream already fetched for the base shot/card
layers (no new network round-trip beyond what ingest_soccer_states.py already does) and
UPGRADES the type-only `xgproxy_diff` of ingest_shot_states.py into a location-weighted
shot-xG PROXY using the per-shot `play.fieldPositionX` coordinate.

PROBE EVIDENCE (.planning/product/deepdata/soccer.md, probe 2026-06-19, event 740956):
  - `commentary[].play.fieldPositionX` populated 18/18 shots (e.g. 0.376); taker-relative
    attacking progress along the axis, ~1.0 == at the opponent goal line.
  - `commentary[].play.fieldPositionY` present (lateral, 0.5 == central).
  - `goalPositionX/Y` are ALL-ZERO (probed) -> on-target PLACEMENT cannot be modeled, so
    we model ONLY shot ORIGIN distance/angle. This is a PROXY, NOT vendor/Opta/StatsBomb xG.

Output: data/cache/ingame/soccer_shotxgstates__<label>.parquet, schema:
  game_id, asof_idx, xgloc_diff, home_xgloc, away_xgloc, n_shots_loc
keyed to merge onto soccer_states__<label>.parquet by (game_id, asof_idx) -- mirrors the
FROZEN base grid (19 points, 0..18) + ADDITIVE as-of cols for this layer.

Location -> xG proxy (monotone, NOT a fabricated formula): for a shot with origin progress
x in [0,1] and lateral offset |y-0.5|, distance-to-goal d ~ (1-x) and angle penalty ~|y-0.5|.
We map (d, lateral) through a logistic finishing curve whose two anchors are pinned to the
WELL-KNOWN aggregate shot->goal rates that the corpus itself reproduces (a penalty-spot /
6-yard shot finishes far more often than a 30-yard effort). Per-shot proxy is clamped to
the open interval (0,1) and is a finishing-PROBABILITY proxy, not money.

Side attribution mirrors ingest_shot_states.py EXACTLY: ESPN commentary play.team is None
and play.fieldPositionX is taker-relative, so neither disambiguates side. We join
play.participants[0].athlete.displayName -> rosters -> 'home'/'away'. An UNATTRIBUTABLE
shot (taker not in either roster, or no participant) is DROPPED, never given a side
(anchor: ingest_shot_states.py:136 -- drop, don't guess). A shot with NO usable
fieldPositionX is excluded from xgloc and from n_shots_loc (coverage guard).

Leak-free: grid minute m counts ONLY shots with clock <= m (step function, no lookahead).
A shot at min 40 contributes to xgloc for ticks >= 40 ONLY, 0 before. Final-total boxscore
xG / shot stats are NEVER used (those are leaky in-game). The match-final score/close is a
held-out yardstick, NEVER read here.

Honest expected verdict: REJECT-leaning vs the type-only proxy and the (margin,time) base
-- a refined location proxy MAY win on in-game Brier CALIBRATION but that is NOT a $ edge.
NO $ / ROI / hit-rate field anywhere; UNITS/probability only.

INVARIANTS: <=300 LOC; ASCII only; no API keys; no src.*/kernel.* imports.
Train/inference parity: the SAME pure functions (shot_xg_events -> build_xgloc_states)
produce the additive cols at ingest (train corpus) and at live inference; a new feature
read here is read identically in both, never silently 0.0.
CLI: python -m domains.soccer.ingest_shotxg_states --labels eng1 esp1
"""
from __future__ import annotations

import argparse
import json
import logging
import math
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

# Logistic finishing-curve anchors. These pin the proxy to the two well-known aggregate
# shot->goal rates the corpus reproduces: a near-goal central shot (x~1, lateral~0) finishes
# at ~_P_NEAR, a long central shot (x~_X_FAR) at ~_P_FAR. NOT a fabricated $ figure; this is
# a finishing-PROBABILITY proxy only. Lateral offset adds an angle penalty (_LAT_PEN).
_P_NEAR, _P_FAR, _X_FAR = 0.45, 0.03, 0.55
_LAT_PEN = 2.5            # angle penalty weight on |y-0.5|
_XG_MIN, _XG_MAX = 1e-4, 0.99


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


def _is_shot(type_text: str) -> bool:
    tl = (type_text or "").lower()
    return tl.startswith("shot") or tl.startswith("goal") or "penalty" in tl


# Logistic fit pinned to the two anchors above (solved once at import, pure arithmetic).
def _fit_logit() -> Tuple[float, float]:
    """Return (a, b) for p(d) = sigmoid(a + b*d) with p(0)=_P_NEAR, p(_X_FAR)=_P_FAR.

    d is distance-to-goal proxy = (1 - x) in [0,1]; d=0 == at goal line.
    """
    def logit(p: float) -> float:
        return math.log(p / (1.0 - p))
    a = logit(_P_NEAR)
    b = (logit(_P_FAR) - a) / _X_FAR
    return a, b


_A, _B = _fit_logit()


def loc_xg(field_x: float, field_y: Optional[float]) -> float:
    """Location -> finishing-probability proxy in (0,1). Pure, monotone in distance.

    field_x: taker-relative attacking progress in [0,1] (~1.0 == at goal). field_y: lateral
    in [0,1] (0.5 == central); None -> no angle penalty. Distance d = (1 - x); angle penalty
    scales d by lateral offset. Clamped to [_XG_MIN, _XG_MAX]. NOT vendor xG, NOT money.
    """
    x = min(1.0, max(0.0, float(field_x)))
    d = 1.0 - x
    lat = 0.0 if field_y is None else min(0.5, abs(float(field_y) - 0.5))
    d_eff = d * (1.0 + _LAT_PEN * lat)
    p = 1.0 / (1.0 + math.exp(-(_A + _B * d_eff)))
    return min(_XG_MAX, max(_XG_MIN, p))


def shot_xg_events(payload: dict) -> List[Tuple[float, str, float]]:
    """Return [(minute, side, loc_xg)] for ATTRIBUTABLE shots with a usable fieldPositionX.

    A shot missing fieldPositionX (None / non-numeric) is DROPPED from the location layer
    (coverage guard) -- it is NOT 0-filled into a fake xG. Unattributable shots dropped.
    """
    home_id = _home_id(payload)
    if not home_id:
        return []
    side_map = _name_to_side(payload, home_id)
    out: List[Tuple[float, str, float]] = []
    for c in (payload.get("commentary") or []):
        pl = c.get("play") or {}
        if not _is_shot((pl.get("type") or {}).get("text", "")):
            continue
        fx = pl.get("fieldPositionX")
        if fx is None:
            continue
        try:
            x = float(fx)
        except (TypeError, ValueError):
            continue
        fy = pl.get("fieldPositionY")
        try:
            y = float(fy) if fy is not None else None
        except (TypeError, ValueError):
            y = None
        minute = _clock_minute(pl)
        if minute is None:
            continue
        parts = pl.get("participants") or []
        nm = _norm((parts[0].get("athlete") or {}).get("displayName", "")) if parts else ""
        side = side_map.get(nm)
        if side is None:
            continue   # unattributable -> drop, never fabricate a side (shot_states.py:136)
        out.append((minute, side, loc_xg(x, y)))
    return out


def build_xgloc_states(game_id: str,
                       shots: List[Tuple[float, str, float]]) -> List[dict]:
    """Build cumulative per-grid-point location-xG rows (leak-free step function).

    At grid minute m, xgloc counts ONLY shots with event-minute <= m. n_shots_loc is the
    cumulative count of shots with a usable location (coverage guard for the gate).
    """
    rows: List[dict] = []
    for idx, minute in enumerate(_GRID):
        hx = sum(xg for m, sd, xg in shots if m <= minute and sd == "home")
        ax = sum(xg for m, sd, xg in shots if m <= minute and sd == "away")
        n = sum(1 for m, _, _ in shots if m <= minute)
        rows.append({
            "game_id": str(game_id), "asof_idx": idx,
            "xgloc_diff": float(hx - ax),
            "home_xgloc": float(hx), "away_xgloc": float(ax),
            "n_shots_loc": int(n),
        })
    return rows


def ingest_label(label: str, getter: Optional[Callable] = None,
                 max_events: Optional[int] = None,
                 out_dir: Optional[Path] = None) -> Path:
    """For every game_id in soccer_states__<label>, fetch shots; write shotxgstates.

    Only games with at least one located+attributed shot emit rows (an all-zero grid
    carries no location signal; do not 0-fill a no-coverage game into the corpus).
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
    ok = empty = 0
    for eid in ids:
        payload = _get(_SUMMARY.format(l=league, e=eid), getter)
        shots = shot_xg_events(payload) if payload else []
        st = build_xgloc_states(eid, shots)
        if any(r["n_shots_loc"] for r in st):
            rows.extend(st)
            ok += 1
        else:
            empty += 1
        time.sleep(0.08)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    out = outd / f"soccer_shotxgstates__{label}.parquet"
    if not df.empty:
        df.to_parquet(out, index=False)
    log.info("label=%s games_with_loc_shots=%d empty=%d rows=%d -> %s",
             label, ok, empty, len(df), out)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Ingest soccer in-game location-xG states.")
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
