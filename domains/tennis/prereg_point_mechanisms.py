"""domains.tennis.prereg_point_mechanisms -- point-level tennis mechanism tests
on the new Sackmann PBP parquets (slam_points 2011-2015, charting_points
1960-2026). Descriptive 'clutch serving' claims live in pressure_claims.py.

PREREGISTERED (K=2, Bonferroni alpha=0.025, declared before running):
  H1 break-point serve dip: within-match paired design -- per (match, server)
    unit, delta = bp_win_rate - non_bp_win_rate (own baseline, SAME match),
    cluster-robust (by match_id) one-sample mean-zero OLS. Floors: >=3 BP,
    >=10 non-BP points/unit (declared).
  H2 serve-vs-return interaction: logit(server_won ~ serve_str + return_str +
    serve_str:return_str), points where BOTH as-of profiles clear >=500 prior
    points. The interaction coefficient is the hypothesis.
Both scored only over STANDARD (non-tiebreak) points -- tiebreaks use raw
integer scores (not 0/15/30/40/AD); "break point" isn't coherent there.

REPLICATION: slam_points (2011-2015, whole corpus) vs charting_points
restricted to year>=2016 (disjoint years = independent corpus; charting is a
curated non-random sample -- honesty caveat on every charting row).
REPLICATED = same-sign AND p<ALPHA in BOTH; n=0 in either -> NOT_TESTABLE,
never a silent FAILED_REPLICATION.

SCHEMA VERIFIED ON REAL DATA THIS SESSION: slam p1_score/p2_score are the
score AFTER each row's own point (the row that wins a game shows the "0-0"
reset meant for the NEXT game) -- pre-point state is the PRIOR row's score
within (match_id, set_no, game_no). charting score_state is "server-returner"
BEFORE the point (verified by chaining consecutive rows) -- no shift needed,
and DOES carry real in-game state (contrary to the brief's up-front worry) --
H1 replicates on both corpora, no NOT_TESTABLE fallback needed for it.

PLAYER IDENTITY (H2's cross-match as-of profiles only -- H1 needs none):
slam_points.parquet has no id/name column (verified); joined from the
already-local raw *-matches.csv (player1id/player2id), zero network.
charting_points.parquet's match_id is "<date>-<tour>-<event>-<round>-<p1name>-
<p2name>" (verified on 15 real ids) -- names are the last 2 '-'-tokens.

LEAK DISCIPLINE (H2): as-of profiles are DATE-BATCHED -- matches sharing a
date snapshot from the SAME pre-batch history; histories update once per
whole batch -- leak-free even though slam dates are tourney-start
approximations shared by a whole event (conservative only, never leaks).

edge_claimed hard-wired False everywhere. NETWORK: zero.
CLI: python -m domains.tennis.prereg_point_mechanisms
Per-file test: python -m pytest domains/tennis/test_prereg_point_mechanisms.py -q
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

REPO_ROOT = Path(__file__).resolve().parents[2]
_SLAM_PATH = REPO_ROOT / "data/cache/sackmann_pbp/slam_points.parquet"
_CHART_PATH = REPO_ROOT / "data/cache/sackmann_pbp/charting_points.parquet"
_SLAM_RAW_DIR = REPO_ROOT / "data/domains/tennis/_raw/sackmann_pbp_repos/tennis_slam_pointbypoint"
LEDGER_PATH = REPO_ROOT / "data/cache/intel_claims/prereg_hypothesis_ledger.jsonl"

ALPHA = 0.025  # K=2, plain Bonferroni (0.05/2) -- declared before running
MIN_BP, MIN_NONBP = 3, 10          # H1 per-match-server floors
MIN_PRIOR_PTS = 500                 # H2 as-of profile floor
STANDARD = {"0", "15", "30", "40", "AD"}

SURVIVES, NULL, NOT_TESTABLE = "SURVIVES_PREREG", "NULL", "NOT_TESTABLE"
REPLICATED, FAILED_REPLICATION = "REPLICATED", "FAILED_REPLICATION"

def _break_point(server_sc: pd.Series, ret_sc: pd.Series) -> pd.Series:
    """returner one point from breaking: AD, or 40 while server isn't also at 40/AD."""
    return (ret_sc == "AD") | ((ret_sc == "40") & ~server_sc.isin(("40", "AD")))

def slam_point_state(df: pd.DataFrame) -> pd.DataFrame:
    """POST-point scores (verified) -- shift w/in (match,set,game) for pre-point state; drop winner=0 sentinel."""
    d0 = df.sort_values(["match_id", "set_no", "game_no", "point_number"]).reset_index(drop=True)
    grp = d0.groupby(["match_id", "set_no", "game_no"], sort=False)
    pre1 = grp["p1_score"].shift(1).fillna("0")
    pre2 = grp["p2_score"].shift(1).fillna("0")
    mask = d0["point_winner"].isin((1, 2)) & pre1.isin(STANDARD) & pre2.isin(STANDARD)
    d, pre1, pre2 = d0[mask], pre1[mask], pre2[mask]
    server = d["point_server"].astype(int)
    is_p1_server = (server.to_numpy() == 1)
    server_sc = pre1.where(is_p1_server, pre2)
    ret_sc = pre2.where(is_p1_server, pre1)
    return pd.DataFrame({
        "match_id": d["match_id"].to_numpy(), "server": server.to_numpy(),
        "server_won": (d["point_winner"].astype(int).to_numpy() == server.to_numpy()).astype(int),
        "break_point": _break_point(server_sc, ret_sc).to_numpy(),
        "date": pd.to_datetime(d["date"]).to_numpy(),
    })

def charting_point_state(df: pd.DataFrame, year_min: Optional[int] = None) -> pd.DataFrame:
    """score_state is "server-returner" PRE-point (verified), no shift needed; unresolvable dates dropped."""
    d = df[(df["date_source"] != "missing") & df["server"].isin((1, 2)) & df["point_winner"].isin((1, 2))].copy()
    if year_min is not None:
        d = d[pd.to_datetime(d["date"]).dt.year >= year_min]
    parts = d["score_state"].astype(str).str.split("-", n=1, expand=True)
    before_srv, before_ret = parts[0], parts[1]
    keep = before_srv.isin(STANDARD) & before_ret.isin(STANDARD)
    d, before_srv, before_ret = d[keep], before_srv[keep], before_ret[keep]
    server = d["server"].astype(int)
    return pd.DataFrame({
        "match_id": d["match_id"].to_numpy(), "server": server.to_numpy(),
        "server_won": (d["point_winner"].astype(int).to_numpy() == server.to_numpy()).astype(int),
        "break_point": _break_point(before_srv, before_ret).to_numpy(),
        "date": pd.to_datetime(d["date"]).to_numpy(),
    })

def h1_fit(frame: pd.DataFrame) -> Dict[str, Any]:
    """Cluster-by-match one-sample test of mean delta != 0 across (match_id, server) units."""
    bp_g = frame[frame["break_point"]].groupby(["match_id", "server"])["server_won"].agg(["mean", "size"])
    nb_g = frame[~frame["break_point"]].groupby(["match_id", "server"])["server_won"].agg(["mean", "size"])
    both = bp_g.join(nb_g, lsuffix="_bp", rsuffix="_nb", how="inner")
    both = both[(both["size_bp"] >= MIN_BP) & (both["size_nb"] >= MIN_NONBP)]
    if both.empty:
        return {"n": 0, "effect": None, "p": None, "term": "delta_bp_minus_nonbp"}
    deltas = (both["mean_bp"] - both["mean_nb"]).to_numpy()
    match_ids = both.index.get_level_values("match_id").to_numpy()
    model = sm.OLS(deltas, np.ones(len(deltas))).fit(cov_type="cluster", cov_kwds={"groups": match_ids})
    return {"n": int(len(deltas)), "effect": float(model.params[0]), "p": float(model.pvalues[0]),
            "term": "delta_bp_minus_nonbp"}

def _slam_match_ids(raw_dir: Path = _SLAM_RAW_DIR) -> Dict[str, tuple]:
    """match_id -> (player1id, player2id) from the already-local raw matches.csv (no id col in the parquet)."""
    out: Dict[str, tuple] = {}
    for p in sorted(glob.glob(str(raw_dir / "*-matches.csv"))):
        m = pd.read_csv(p, dtype=str, usecols=["match_id", "player1id", "player2id"])
        out.update(dict(zip(m["match_id"], zip(m["player1id"], m["player2id"]))))
    return out

def _charting_match_ids(match_ids: pd.Series) -> Dict[str, tuple]:
    """match_id -> (p1_name, p2_name); last 2 '-'-tokens (verified format)."""
    out: Dict[str, tuple] = {}
    for mid in match_ids.dropna().unique():
        parts = str(mid).split("-")
        out[mid] = (parts[-2], parts[-1]) if len(parts) >= 2 else ("Unknown", "Unknown")
    return out

def _id_frame(id_map: Dict[str, tuple]) -> pd.DataFrame:
    return pd.DataFrame([(k, v[0], v[1]) for k, v in id_map.items()],
                         columns=["match_id", "p1_id", "p2_id"])

def _match_level_agg(frame: pd.DataFrame, id_map: Dict[str, tuple]) -> pd.DataFrame:
    """One row per (match_id, player_id): serve_won/n, return_won/n, date. Return stats for slot X
    = the OTHER slot's serve stats inverted (return_won = other_serve_n - other_serve_won)."""
    agg = frame.groupby(["match_id", "server"])["server_won"].agg(["sum", "size"]).reset_index()
    agg = agg.rename(columns={"sum": "won", "size": "n"})
    piv_won = agg.pivot(index="match_id", columns="server", values="won").fillna(0)
    piv_n = agg.pivot(index="match_id", columns="server", values="n").fillna(0)
    dates = frame.groupby("match_id")["date"].first()
    idm = _id_frame(id_map).set_index("match_id")
    rows = []
    for slot, other in ((1, 2), (2, 1)):
        s_won = piv_won.get(slot, pd.Series(0.0, index=piv_won.index))
        s_n = piv_n.get(slot, pd.Series(0.0, index=piv_n.index))
        o_won = piv_won.get(other, pd.Series(0.0, index=piv_won.index))
        o_n = piv_n.get(other, pd.Series(0.0, index=piv_n.index))
        pid_col = f"p{slot}_id"
        pid_raw = idm[pid_col].reindex(piv_won.index)
        # unmapped id (e.g. 2012-ausopen's matches.csv has NO player ids, verified) gets a per-
        # (match,slot) UNIQUE synthetic id -- never collides, so it sits at n_prior=0 forever (floored out).
        fallback = pd.Series([f"UNK_{m}_p{slot}" for m in piv_won.index], index=piv_won.index)
        pid = pid_raw.where(pid_raw.notna(), fallback).to_numpy()
        rows.append(pd.DataFrame({
            "match_id": piv_won.index, "player_id": pid,
            "serve_won": s_won.to_numpy(), "serve_n": s_n.to_numpy(),
            "return_won": (o_n - o_won).to_numpy(), "return_n": o_n.to_numpy(),
            "date": dates.reindex(piv_won.index).to_numpy(),
        }))
    return pd.concat(rows, ignore_index=True)

class _Hist:
    __slots__ = ("sw", "sn", "rw", "rn")

    def __init__(self) -> None:
        self.sw = self.sn = self.rw = self.rn = 0.0

def asof_walkforward(match_lvl: pd.DataFrame) -> pd.DataFrame:
    """Date-batched snapshot-then-update: matches sharing a date get the SAME pre-batch snapshot;
    histories update once per batch, after ALL of that date's matches. Leak-free by construction."""
    hist: Dict[str, _Hist] = {}
    snaps: List[dict] = []
    for _, batch in match_lvl.groupby("date", sort=True):
        for _, row in batch.iterrows():
            h = hist.setdefault(row["player_id"], _Hist())
            snaps.append({
                "match_id": row["match_id"], "player_id": row["player_id"],
                "serve_str": h.sw / h.sn if h.sn > 0 else np.nan,
                "return_str": h.rw / h.rn if h.rn > 0 else np.nan,
                "serve_n_prior": h.sn, "return_n_prior": h.rn,
            })
        for _, row in batch.iterrows():
            h = hist[row["player_id"]]
            h.sw += row["serve_won"]; h.sn += row["serve_n"]
            h.rw += row["return_won"]; h.rn += row["return_n"]
    return pd.DataFrame(snaps)

def h2_fit(frame: pd.DataFrame, id_map: Dict[str, tuple], year_min: Optional[int] = None) -> Dict[str, Any]:
    ml = _match_level_agg(frame, id_map)
    snap = asof_walkforward(ml).set_index(["match_id", "player_id"])

    f = frame.merge(_id_frame(id_map), on="match_id", how="left")
    server_pid = np.where(f["server"] == 1, f["p1_id"], f["p2_id"])
    returner_pid = np.where(f["server"] == 1, f["p2_id"], f["p1_id"])
    snap_s = snap.reindex(list(zip(f["match_id"], server_pid)))
    snap_r = snap.reindex(list(zip(f["match_id"], returner_pid)))
    f = f.assign(serve_str=snap_s["serve_str"].to_numpy(), serve_n_prior=snap_s["serve_n_prior"].to_numpy(),
                 return_str=snap_r["return_str"].to_numpy(), return_n_prior=snap_r["return_n_prior"].to_numpy())

    if year_min is not None:
        f = f[pd.to_datetime(f["date"]).dt.year >= year_min]
    scored = f[(f["serve_n_prior"] >= MIN_PRIOR_PTS) & (f["return_n_prior"] >= MIN_PRIOR_PTS)]
    scored = scored.dropna(subset=["serve_str", "return_str"])
    if scored.empty:
        return {"n": 0, "effect": None, "p": None, "term": "serve_str:return_str"}
    res = smf.logit("server_won ~ serve_str + return_str + serve_str:return_str", data=scored).fit(disp=0)
    term = "serve_str:return_str"
    return {"n": int(res.nobs), "effect": float(res.params[term]), "p": float(res.pvalues[term]), "term": term}

def _corpus_row(name: str, corpus: str, atomic_unit: str, fit: Dict[str, Any]) -> Dict[str, Any]:
    if fit["n"] == 0:
        v, note = NOT_TESTABLE, "n=0: no rows cleared the declared floors on this corpus"
    else:
        v, note = (SURVIVES if fit["p"] < ALPHA else NULL), ""
    return {
        "hypothesis": name, "sport": "tennis", "atomic_unit": atomic_unit, "corpus": corpus,
        "method": "prereg_point_mechanisms", "n": fit["n"], "effect": fit["effect"], "p": fit["p"],
        "alpha_fwer": ALPHA, "term": fit["term"], "verdict": v, "note": note, "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

def _replication_row(name: str, atomic_unit: str, fit_a: Dict[str, Any], fit_b: Dict[str, Any]) -> Dict[str, Any]:
    if fit_a["n"] == 0 or fit_b["n"] == 0:
        v, note = NOT_TESTABLE, "n=0 in at least one corpus -- not a failed replication"
    else:
        same_sign = (fit_a["effect"] > 0) == (fit_b["effect"] > 0)
        both_sig = fit_a["p"] < ALPHA and fit_b["p"] < ALPHA
        v = REPLICATED if (same_sign and both_sig) else FAILED_REPLICATION
        note = "" if v == REPLICATED else "same-sign-and-p<alpha required in BOTH corpora"
    return {
        "hypothesis": name, "sport": "tennis", "atomic_unit": atomic_unit, "corpus": "slam_vs_charting2016plus",
        "method": "prereg_point_mechanisms", "n": fit_a["n"] + fit_b["n"],
        "effect_slam": fit_a["effect"], "effect_charting": fit_b["effect"],
        "p_slam": fit_a["p"], "p_charting": fit_b["p"], "alpha_fwer": ALPHA,
        "verdict": v, "note": note, "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

def append_ledger(rows: List[Dict[str, Any]], path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

def run() -> Dict[str, Any]:
    slam_raw = pd.read_parquet(_SLAM_PATH)
    chart_raw = pd.read_parquet(_CHART_PATH)

    slam_state = slam_point_state(slam_raw)
    chart_state_full = charting_point_state(chart_raw)
    chart_state_2016 = chart_state_full[pd.to_datetime(chart_state_full["date"]).dt.year >= 2016]

    slam_ids = _slam_match_ids()
    chart_ids = _charting_match_ids(chart_raw["match_id"])

    h1_slam = h1_fit(slam_state)
    h1_chart = h1_fit(chart_state_2016)
    h2_slam = h2_fit(slam_state, slam_ids)
    h2_chart = h2_fit(chart_state_full, chart_ids, year_min=2016)

    rows = [
        _corpus_row("H1 break-point serve dip", "slam_points_2011_15", "point", h1_slam),
        _corpus_row("H1 break-point serve dip", "charting_points_2016plus", "point", h1_chart),
        _replication_row("H1 break-point serve dip", "point", h1_slam, h1_chart),
        _corpus_row("H2 serve-return interaction", "slam_points_2011_15", "point", h2_slam),
        _corpus_row("H2 serve-return interaction", "charting_points_2016plus", "point", h2_chart),
        _replication_row("H2 serve-return interaction", "point", h2_slam, h2_chart),
    ]
    append_ledger(rows)
    return {"rows": rows}

def main() -> int:
    result = run()
    print(f"K=2 alpha_bonferroni={ALPHA} -- tennis point-level prereg mechanisms")
    for r in result["rows"]:
        print(f"  [{r['verdict']:>18}] {r['hypothesis']} ({r.get('corpus')}): "
              f"n={r['n']} effect={r.get('effect', r.get('effect_slam'))}")
    print(f"appended {len(result['rows'])} rows -> {LEDGER_PATH}")
    from domains.tennis.pressure_claims import build_pressure_claims, CLAIMS_PATH  # noqa: PLC0415
    chart_raw = pd.read_parquet(_CHART_PATH)
    claims = build_pressure_claims(chart_raw)
    print(f"wrote {len(claims)} claim(s) -> {CLAIMS_PATH}")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
