"""domains.soccer.knowledge.validate_ppda_shot_quality -- C15: does a team's
own first-half pressing intensity (PPDA proxy = opponent passes / own
Pressure+Duel+Interception count) predict the shot QUALITY it concedes in the
SECOND half (opponent's xG-per-shot against it), not just the turnover rate
already tested in mechanisms.md #19?

Leak audit: predictor is computed from period==1 events only, outcome from
period==2 events only -- a genuine forward (first-half -> second-half) split,
never same-window correlation.

Corpora: the two competition groups with match-level metadata (corpus A=EPL
2015/16, B=FA WSL, 200 matches each, `_data.load_match_meta`) are tested
independently and combined per HONESTY discipline: >=2 same-direction
significant corpora -> CONFIRMED_LOCAL, 1 -> PROVISIONAL, else NULL_LOCAL/
NOT_TESTABLE. The other ~3,000 events-only matches lack competition metadata
and are out of scope for this cross-competition-group test.

Run: python -m domains.soccer.knowledge.validate_ppda_shot_quality
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, load_events, load_match_meta
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_N = 30
DEF_ACTION_TYPES = {"Pressure", "Duel", "Interception"}
CORPORA = ["A", "B"]


def _verdict(p, min_abs_effect: float, effect) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _half_stats(events: List[Dict[str, Any]], period: int) -> Dict[str, Dict[str, float]]:
    """One team's own passes/def-actions/xG-created/shot-count for one half."""
    teams: Dict[str, Dict[str, float]] = {}

    def _t(name: str) -> Dict[str, float]:
        return teams.setdefault(name, {"passes": 0, "def_actions": 0, "xg": 0.0, "shots": 0})

    for e in events:
        if e.get("period") != period:
            continue
        team = (e.get("team") or {}).get("name")
        if not team:
            continue
        etype = e["type"]["name"]
        d = _t(team)
        if etype == "Pass":
            d["passes"] += 1
        elif etype in DEF_ACTION_TYPES:
            d["def_actions"] += 1
        elif etype == "Shot":
            xg = ((e.get("shot") or {}).get("statsbomb_xg"))
            if xg is not None:
                d["xg"] += xg
                d["shots"] += 1
    return teams


def match_rows(events: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """(first-half PPDA proxy, second-half xG-per-shot conceded) per team,
    for matches with exactly 2 teams present in both halves."""
    h1, h2 = _half_stats(events, 1), _half_stats(events, 2)
    names = [n for n in h1 if n in h2]
    if len(names) != 2:
        return []
    out = []
    for n in names:
        opp = [o for o in names if o != n][0]
        opp_passes_h1, def_actions_h1 = h1[opp]["passes"], h1[n]["def_actions"]
        opp_shots_h2, opp_xg_h2 = h2[opp]["shots"], h2[opp]["xg"]
        if opp_passes_h1 < 20 or def_actions_h1 == 0 or opp_shots_h2 == 0:
            continue
        out.append((opp_passes_h1 / def_actions_h1, opp_xg_h2 / opp_shots_h2))
    return out


def _corpus_test(rows: List[Tuple[float, float]], corpus: str) -> Dict[str, Any]:
    if len(rows) < MIN_N:
        return {"hypothesis": "ppda_h1_vs_shot_quality_conceded_h2", "n": len(rows), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient n=%d (<%d) after filters, corpus=%s" % (len(rows), MIN_N, corpus)}
    ppda, xg_shot = zip(*rows)
    r, p = stats.pearsonr(ppda, xg_shot)
    return {"hypothesis": "ppda_h1_vs_shot_quality_conceded_h2", "n": len(rows), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.05, r),
            "note": "pearson r, own 1st-half PPDA-proxy vs opponent's 2nd-half xG-per-shot (forward split, "
                    "n=%d team-match units), corpus=%s" % (len(rows), corpus)}


def _combine(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    else:
        signs = {np.sign(r["effect"]) for r in testable if r["p"] < ALPHA}
        sig = [r for r in testable if r["p"] < ALPHA]
        if len(sig) >= 2 and len(signs) == 1:
            verdict = "CONFIRMED_LOCAL"
        elif len(sig) == 1:
            verdict = "PROVISIONAL"
        else:
            verdict = "NULL_LOCAL"
    note = "; ".join("%s:%s(p=%s,eff=%s)" % (c, r["verdict"], r["p"], r["effect"]) for c, r in zip(CORPORA, rows))
    return {"hypothesis": "ppda_h1_vs_shot_quality_conceded_h2__combined", "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "cross-competition-group replication (2 corpora, A=EPL/B=WSL): %s" % note}


def run() -> List[Dict[str, Any]]:
    meta = load_match_meta()
    corpus_rows: List[Dict[str, Any]] = []
    for corpus in CORPORA:
        match_ids = meta[meta["corpus"] == corpus]["match_id"].tolist()
        rows: List[Tuple[float, float]] = []
        for mid in match_ids:
            rows.extend(match_rows(load_events(mid)))
        corpus_rows.append(_corpus_test(rows, corpus))
    out = corpus_rows + [_combine(corpus_rows)]
    for r in out:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_match_meta_400__A_epl_B_wsl"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return out


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
