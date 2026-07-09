"""attribute_priors -- the leak-legal, strictly-AS-OF team-attribute priors and
the leak-free realized-at-checkpoint quantities that attribute_conditioning
interacts. Split out of attribute_conditioning purely for the 300-LOC cap; see
that module's docstring for the leak-legality decision and hypothesis list.

Every prior here is recomputed from raw pbp/stints with a `date < game_date`
cut (same discipline as livestate_priors) -- NOT from the profile parquet
(whole-season = leak) and NOT from the season-aggregate on_off/zone artifacts
(also whole-season). Realized sides reuse the checkpoint machinery verbatim
(elapsed<=t / start_g<t), so they cannot see the future.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.ingame_compose.checkpoints import _global_elapsed
from scripts.platformkit.ingame_compose.livestate_ingame import (
    floor_lineup_at, truncated_minutes_at,
)


# ----------------------------- leak-legal priors -----------------------------
def _rim_flag(a: dict) -> bool:
    """A 2pt attempt at the rim. `area` is empty in this feed, so we read the
    description: an explicit small foot-distance, or a dunk/layup/tip/hook --
    present across all 3 seasons' pbp (verified 2023-24/24-25/25-26)."""
    if a.get("actionType") != "2pt":
        return False
    d = (a.get("description") or "").lower()
    if any(w in d for w in ("dunk", "layup", "tip", "hook", "putback")):
        return True
    for tok in d.split():
        if tok.endswith("-foot"):
            try:
                return int(tok[:-5]) <= 4
            except ValueError:
                return False
    return False


def build_shot_priors(pbp_dir, ev: pd.DataFrame) -> pd.DataFrame:
    """Per (team, date) whole-game shot counts -> cumulative-by-date table.
    Offence: att2/att3/rim. Defence: opp's rim + total (what the team ALLOWED).
    Strictly-prior is enforced at lookup (date < target), same as
    livestate_priors.build_top3_fga_table."""
    rows: List[dict] = []
    for r in ev.itertuples(index=False):
        fp = pbp_dir / f"{r.game_id}.json"
        if not fp.exists():
            continue
        tally: Dict[str, List[int]] = {}   # tri -> [att2, att3, rim]
        for a in json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]:
            at = a.get("actionType")
            tri = a.get("teamTricode")
            if at not in ("2pt", "3pt") or not tri:
                continue
            t = tally.setdefault(tri, [0, 0, 0])
            t[0 if at == "2pt" else 1] += 1
            if _rim_flag(a):
                t[2] += 1
        tris = list(tally)
        for i, tri in enumerate(tris):
            a2, a3, rim = tally[tri]
            opp = tris[1 - i] if len(tris) == 2 else None
            drim, dtot = (tally[opp][2], tally[opp][0] + tally[opp][1]) if opp else (0, 0)
            rows.append({"team": tri, "date": r.date, "att2": a2, "att3": a3,
                         "rim": rim, "def_rim": drim, "def_tot": dtot})
    b = pd.DataFrame(rows).sort_values(["team", "date"])
    for c in ("att2", "att3", "rim", "def_rim", "def_tot"):
        b[c] = b.groupby("team")[c].cumsum()
    return b


def _asof_row(tbl: pd.DataFrame, team: str, date) -> Optional[pd.Series]:
    prior = tbl[(tbl["team"] == team) & (tbl["date"] < date)]
    return None if prior.empty else prior.iloc[-1]


def three_share_asof(tbl: pd.DataFrame, team: str, date) -> Optional[float]:
    r = _asof_row(tbl, team, date)
    if r is None or (r["att2"] + r["att3"]) <= 0:
        return None
    return float(r["att3"] / (r["att2"] + r["att3"]))


def rim_allowed_asof(tbl: pd.DataFrame, team: str, date) -> Optional[float]:
    r = _asof_row(tbl, team, date)
    if r is None or r["def_tot"] <= 0:
        return None
    return float(r["def_rim"] / r["def_tot"])


def build_continuity(stints_all: pd.DataFrame, ev: pd.DataFrame) -> Dict[int, List[Tuple]]:
    """team_id -> [(date, frozenset(starting-5)), ...] sorted by date. Starters =
    the opening stint (start_g<=0). continuity_asof reduces this to a strictly-
    prior mean jaccard of consecutive lineups."""
    date_by_gid = {str(r.game_id): r.date for r in ev.itertuples(index=False)}
    seq: Dict[int, List[Tuple]] = {}
    for gid, g in stints_all.groupby(stints_all["game_id"].astype(str)):
        d = date_by_gid.get(gid)
        if d is None:
            continue
        for tid in g["team_id"].unique():
            starters = floor_lineup_at(g, int(tid), 0.0)
            if starters:
                seq.setdefault(int(tid), []).append((d, frozenset(int(p) for p in starters)))
    for tid in seq:
        seq[tid].sort(key=lambda x: x[0])
    return seq


def continuity_asof(seq: Dict[int, List[Tuple]], team_id: int, date) -> Optional[float]:
    prior = [s for dt, s in seq.get(team_id, []) if dt < date]
    if len(prior) < 2:
        return None
    js = [len(prior[i] & prior[i + 1]) / len(prior[i] | prior[i + 1])
          for i in range(len(prior) - 1)]
    return float(np.mean(js))


# --------------------------- realized (leak-free) ----------------------------
def rim_tally_before(actions: List[dict], t: float) -> Dict[int, List[int]]:
    """teamId -> [rim_att, total_att] for elapsed<=t (same <=t boundary as
    shot_tally_before)."""
    out: Dict[int, List[int]] = {}
    for a in actions:
        at = a.get("actionType")
        tid = a.get("teamId")
        if at not in ("2pt", "3pt") or tid is None:
            continue
        e = _global_elapsed(a.get("period"), a.get("clock"))
        if e is None or e > t:
            continue
        d = out.setdefault(int(tid), [0, 0])
        d[1] += 1
        if _rim_flag(a):
            d[0] += 1
    return out


def rim_share(tally: Dict[int, List[int]], tid: int) -> Optional[float]:
    rim, tot = tally.get(tid, [0, 0])
    return None if tot <= 0 else rim / tot


def luck3(tally: Dict[int, List[int]], tid: int, p3: float) -> float:
    _m2, _a2, made3, att3, _mf, _af = tally.get(tid, [0, 0, 0, 0, 0, 0])
    return float(3 * made3 - 3 * p3 * att3)


def starter_disruption(gstints: pd.DataFrame, tid: int, t: float) -> Optional[float]:
    starters = floor_lineup_at(gstints, tid, 0.0)
    if not starters or t <= 0:
        return None
    tm = truncated_minutes_at(gstints, tid, t)
    share = sum(tm.get(p, 0.0) for p in starters) / (5.0 * t)
    return float(1.0 - share)   # higher = starters sat more (foul trouble/subs)
