"""domains.soccer.ingest_statsbomb_events -- BOUNDED, POLITE acquisition of StatsBomb
OPEN-DATA (free, keyless, public GitHub) + a LEAK-FREE as-of event-level feature layer.

WHY: ESPN's location xG-PROXY already REJECTED. StatsBomb open-data is the canonical
free EVENT-LEVEL soccer feed (REAL shot xG = shot.statsbomb_xg, minute/second stamps,
pressures, passes, carries). This module tests the REAL xG/event signal.

ACQUISITION (bounded + polite, per-file cache under data/cache/statsbomb/):
  competitions.json -> matches/<comp>/<season>.json -> a BOUNDED set of
  events/<match_id>.json. Each file cached on first fetch; subsequent runs are
  zero-network. A polite delay separates network calls. We do NOT clone the repo;
  we fetch only enough matches for >=2 independent corpora.

LEAK-FREE FEATURE LAYER (two grains, both keyed by match_id):
  (1) AS-OF IN-GAME (per match x minute-snapshot): cumulative REAL-xG-for/against,
      shot count, pressure count, pass-completion -- all folded AS-OF BY MINUTE from
      the event stream (strictly events with minute <= t). NEVER the match-final total.
  (2) PREGAME (per match, one row per home/away team slot): strictly-PRIOR trailing
      exponentially-weighted (EW) team xG-for/against + shot/pressure rates + pass%
      computed from each team's PREVIOUS matches only (snapshot-before-update). Debut
      -> NaN; we REFUSE to 0-fill. Uses scripts.platformkit.asof_common.ExpandingMean.

The realized GOAL outcome is the LABEL ONLY, never a feature. The close is never a
feature. CALIBRATION only -- NO $/ROI/edge field anywhere. ASCII; <=300 LOC (this is
a DATA spec module). Network = bounded + cached + delayed.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.asof_common import AsofSpec, ExpandingMean, walk_forward_asof

_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statsbomb"
_RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
_DELAY = 0.25  # polite per-network-call delay (seconds)

# Two INDEPENDENT corpora (different leagues/players/era => genuine replication).
# A: Premier League 2015/16 (English men, one full season). B: FA Women's Super
# League pooled (English women, distinct teams/dynamics). comp_id, season_id.
CORPUS_A: Tuple[Tuple[int, int], ...] = ((2, 27),)
CORPUS_B: Tuple[Tuple[int, int], ...] = ((37, 4), (37, 90), (37, 281))
_MATCH_CAP = 200          # bounded matches fetched per corpus
_EW_HALFLIFE = 5          # trailing EW half-life (matches) for pregame priors

_INGAME_OUT = _CACHE / "asof_ingame.parquet"
_PREGAME_OUT = _CACHE / "asof_pregame.parquet"
_MATCHMETA_OUT = _CACHE / "match_meta.parquet"


def _get_json(url_suffix: str, cache_path: Path) -> Optional[object]:
    """Fetch+cache one JSON file; zero-network on cache hit; polite delay otherwise."""
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    import requests  # local import: acquisition only
    time.sleep(_DELAY)
    r = requests.get(f"{_RAW}/{url_suffix}", timeout=60)
    if r.status_code != 200:
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(r.text, encoding="utf-8")
    return json.loads(r.text)


def fetch_competitions() -> object:
    return _get_json("competitions.json", _CACHE / "competitions.json")


def fetch_matches(comp_id: int, season_id: int) -> List[dict]:
    j = _get_json(f"matches/{comp_id}/{season_id}.json",
                  _CACHE / "matches" / f"{comp_id}_{season_id}.json")
    return list(j) if j else []


def fetch_events(match_id: int) -> List[dict]:
    j = _get_json(f"events/{match_id}.json",
                  _CACHE / "events" / f"{match_id}.json")
    return list(j) if j else []


def _gather_matches(corpus: Sequence[Tuple[int, int]], cap: int) -> List[dict]:
    """Bounded, completed matches sorted by date; capped at `cap`."""
    rows: List[dict] = []
    for cid, sid in corpus:
        for m in fetch_matches(cid, sid):
            if m.get("match_status") in ("available", None) or m.get("home_score") is not None:
                rows.append(m)
    rows = [m for m in rows if m.get("home_score") is not None]
    rows.sort(key=lambda m: m.get("match_date", ""))
    return rows[:cap]


def _team_event_stats(events: List[dict]) -> Dict[str, dict]:
    """Per-team match totals from the event stream (used to build pregame priors)."""
    acc: Dict[str, dict] = {}
    for e in events:
        tn = (e.get("team") or {}).get("name")
        if tn is None:
            continue
        a = acc.setdefault(tn, {"xg": 0.0, "shots": 0, "press": 0,
                                "pass_n": 0, "pass_ok": 0})
        et = (e.get("type") or {}).get("name")
        if et == "Shot":
            a["xg"] += float((e.get("shot") or {}).get("statsbomb_xg") or 0.0)
            a["shots"] += 1
        elif et == "Pressure":
            a["press"] += 1
        elif et == "Pass":
            a["pass_n"] += 1
            if (e.get("pass") or {}).get("outcome") is None:  # None outcome = complete
                a["pass_ok"] += 1
    return acc


def _ingame_snapshots(match_id: int, home: str, away: str,
                      events: List[dict], step: int = 15) -> List[dict]:
    """AS-OF in-game rows at minute snapshots: cumulative REAL xG/shots/pressure/pass%
    using ONLY events with minute <= t (never the final total)."""
    rows: List[dict] = []
    minute = lambda e: int(e.get("minute") or 0)
    maxmin = max((minute(e) for e in events), default=90)
    for t in range(step, min(maxmin, 90) + 1, step):
        cum = {home: {"xg": 0.0, "sh": 0, "pr": 0, "pn": 0, "po": 0},
               away: {"xg": 0.0, "sh": 0, "pr": 0, "pn": 0, "po": 0}}
        gh = ga = 0
        for e in events:
            if minute(e) > t:
                continue
            tn = (e.get("team") or {}).get("name")
            if tn not in cum:
                continue
            et = (e.get("type") or {}).get("name")
            if et == "Shot":
                sh = e.get("shot") or {}
                cum[tn]["xg"] += float(sh.get("statsbomb_xg") or 0.0)
                cum[tn]["sh"] += 1
                if (sh.get("outcome") or {}).get("name") == "Goal":
                    gh += 1 if tn == home else 0
                    ga += 1 if tn == away else 0
            elif et == "Pressure":
                cum[tn]["pr"] += 1
            elif et == "Pass":
                cum[tn]["pn"] += 1
                if (e.get("pass") or {}).get("outcome") is None:
                    cum[tn]["po"] += 1
        rows.append({
            "match_id": str(match_id), "minute": t,
            "home_xg_asof": cum[home]["xg"], "away_xg_asof": cum[away]["xg"],
            "xg_diff_asof": cum[home]["xg"] - cum[away]["xg"],
            "shot_diff_asof": cum[home]["sh"] - cum[away]["sh"],
            "press_diff_asof": cum[home]["pr"] - cum[away]["pr"],
            "home_pass_pct_asof": cum[home]["po"] / cum[home]["pn"] if cum[home]["pn"] else np.nan,
            "away_pass_pct_asof": cum[away]["po"] / cum[away]["pn"] if cum[away]["pn"] else np.nan,
            "goal_diff_asof": gh - ga,
        })
    return rows


def _pregame_spine(meta: pd.DataFrame) -> pd.DataFrame:
    """Per-team match totals (from cached events) -> realized for/against frame keyed
    by match_id, for the as-of EW prior builder."""
    recs: List[dict] = []
    for _, m in meta.iterrows():
        ev = fetch_events(int(m["match_id"]))
        st = _team_event_stats(ev)
        h, a = m["home_team"], m["away_team"]
        sh, sa = st.get(h, {}), st.get(a, {})
        def pp(d):
            return (d.get("pass_ok", 0) / d.get("pass_n", 1)) if d.get("pass_n") else np.nan
        recs.append({
            "match_id": str(m["match_id"]), "date": m["match_date"],
            "home_team": h, "away_team": a,
            "home_xg_for": sh.get("xg", np.nan), "home_xg_against": sa.get("xg", np.nan),
            "away_xg_for": sa.get("xg", np.nan), "away_xg_against": sh.get("xg", np.nan),
            "home_shots": sh.get("shots", np.nan), "away_shots": sa.get("shots", np.nan),
            "home_press": sh.get("press", np.nan), "away_press": sa.get("press", np.nan),
            "home_pass_pct": pp(sh), "away_pass_pct": pp(sa),
        })
    return pd.DataFrame(recs)


_PRE_METRICS = ("xg_for", "xg_against", "shots", "press", "pass_pct")


def build_pregame_priors(spine: pd.DataFrame) -> pd.DataFrame:
    """Strictly-prior trailing per-team priors (snapshot-before-update; debut=NaN),
    via asof_common.walk_forward_asof + ExpandingMean (per-team expanding mean; state
    SHARED across home/away slots). Returns home_/away_ prior_<metric> by match_id."""
    sp = spine.copy()
    sp["event_id"] = sp["match_id"].astype(str)
    out = pd.DataFrame({"match_id": spine["match_id"].astype(str).to_numpy()})
    for m in _PRE_METRICS:
        spec = AsofSpec(
            sort_keys=("date", "event_id"),
            slots=(("home_team", f"home_{m}", f"home_prior_{m}"),
                   ("away_team", f"away_{m}", f"away_prior_{m}")),
            id_col="event_id",
        )
        res = walk_forward_asof(sp, spec, lambda: ExpandingMean(min_prior=1))
        res = res.set_index("event_id")
        out[f"home_prior_{m}"] = res[f"home_prior_{m}_asof"].reindex(
            out["match_id"]).to_numpy()
        out[f"away_prior_{m}"] = res[f"away_prior_{m}_asof"].reindex(
            out["match_id"]).to_numpy()
    return out


def build(corpus_a: Sequence[Tuple[int, int]] = CORPUS_A,
          corpus_b: Sequence[Tuple[int, int]] = CORPUS_B,
          cap: int = _MATCH_CAP) -> Dict[str, object]:
    """Acquire (bounded) + build the as-of in-game + pregame parquets. Returns coverage."""
    cov: Dict[str, object] = {}
    all_meta: List[pd.DataFrame] = []
    ingame_rows: List[dict] = []
    for tag, corp in (("A", corpus_a), ("B", corpus_b)):
        ms = _gather_matches(corp, cap)
        meta = pd.DataFrame([{
            "match_id": m["match_id"], "match_date": m.get("match_date", ""),
            "home_team": m["home_team"]["home_team_name"],
            "away_team": m["away_team"]["away_team_name"],
            "home_score": m["home_score"], "away_score": m["away_score"],
            "corpus": tag,
        } for m in ms])
        cov[f"corpus_{tag}_matches"] = int(len(meta))
        for _, m in meta.iterrows():
            ev = fetch_events(int(m["match_id"]))
            if ev:
                ingame_rows.extend(
                    _ingame_snapshots(int(m["match_id"]), m["home_team"],
                                      m["away_team"], ev))
        all_meta.append(meta)

    meta_all = pd.concat(all_meta, ignore_index=True)
    ingame = pd.DataFrame(ingame_rows)

    pre_frames = []
    for tag in ("A", "B"):
        sub = meta_all[meta_all["corpus"] == tag].sort_values("match_date")
        spine = _pregame_spine(sub)
        pri = build_pregame_priors(spine)
        pri["corpus"] = tag
        pri = pri.merge(spine[["match_id", "home_xg_for", "away_xg_for",
                               "home_team", "away_team", "date"]], on="match_id")
        pre_frames.append(pri)
    pregame = pd.concat(pre_frames, ignore_index=True)

    _INGAME_OUT.parent.mkdir(parents=True, exist_ok=True)
    ingame.to_parquet(_INGAME_OUT, index=False)
    pregame.to_parquet(_PREGAME_OUT, index=False)
    meta_all.to_parquet(_MATCHMETA_OUT, index=False)

    cov["ingame_rows"] = int(len(ingame))
    cov["pregame_rows"] = int(len(pregame))
    cov["statsbomb_xg_nonnull_frac_ingame"] = float(
        ingame["xg_diff_asof"].notna().mean()) if len(ingame) else 0.0
    cov["press_nonnull_frac_ingame"] = float(
        ingame["press_diff_asof"].notna().mean()) if len(ingame) else 0.0
    cov["pregame_prior_xg_nonnull_frac"] = float(
        pregame["home_prior_xg_for"].notna().mean()) if len(pregame) else 0.0
    return cov


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Acquire StatsBomb open-data + build as-of layer.")
    ap.add_argument("--cap", type=int, default=_MATCH_CAP)
    a = ap.parse_args(argv)
    cov = build(cap=a.cap)
    print(json.dumps(cov, indent=2, sort_keys=True))
    return 0


__all__ = ["build", "build_pregame_priors", "fetch_competitions", "fetch_matches",
           "fetch_events", "CORPUS_A", "CORPUS_B", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
