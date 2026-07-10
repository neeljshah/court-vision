"""domains.soccer.knowledge.validate_research_wave3 -- research-wave-3 UNTESTED
rows #39 (same-team shot-rebound-cluster xG additivity) and #40 (defensive
block depth vs own counterattack-shot share) from
domains/soccer/knowledge/mechanisms.md, against the full local StatsBomb
event cache. Leak audit: #39 groups shots by StatsBomb's own `possession` id
WITHIN a single match (contemporaneous/structural, no forecast into a future
match or a future possession -- goal indicator and shot xG both belong to the
same closed possession). #40 is a cross-sectional team-match descriptive
comparison, identical leak profile to the sibling #26 in
validate_pressing_defense.py (both measures come from the SAME match's own
events). Mirrors validate_research_wave2.py's run/run_split_half shape;
reuses `_per_match_team_stats` from validate_pressing_defense.py verbatim for
the #40 block-depth proxy rather than re-deriving it (row #40 states this
reuse explicitly).

Run: python -m domains.soccer.knowledge.validate_research_wave3
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, iter_all_event_files
from domains.soccer.knowledge.validate_pressing_defense import _per_match_team_stats
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_EFFECT_XG = 0.03  # xG-points, per row #39's declared bar
MIN_EFFECT_R = 0.05  # pearson r, per row #40's declared bar


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or p != p:  # NaN-safe
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _match_clusters(events: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """#39: group same-team shots by StatsBomb's own `possession` id within
    this match; cluster = 2+ shots by the same team in the same possession.
    Returns (cluster_gaps, single_gaps) -- per-possession
    (summed statsbomb_xg - goal_indicator) calibration gaps."""
    groups: Dict[Tuple[str, Any], List[Tuple[float, bool]]] = {}
    for e in events:
        if (e.get("type") or {}).get("name") != "Shot":
            continue
        team = (e.get("team") or {}).get("name")
        poss = e.get("possession")
        if not team or poss is None:
            continue
        shot = e.get("shot") or {}
        xg = shot.get("statsbomb_xg")
        if xg is None:
            continue
        is_goal = (shot.get("outcome") or {}).get("name") == "Goal"
        groups.setdefault((team, poss), []).append((xg, is_goal))

    cluster_gaps: List[float] = []
    single_gaps: List[float] = []
    for shots in groups.values():
        summed_xg = sum(xg for xg, _ in shots)
        any_goal = 1.0 if any(g for _, g in shots) else 0.0
        gap = summed_xg - any_goal
        (cluster_gaps if len(shots) >= 2 else single_gaps).append(gap)
    return cluster_gaps, single_gaps


def _counter_share(events: List[Dict[str, Any]]) -> Dict[str, Tuple[int, int]]:
    """#40: per-team (n_counter_shots, n_total_shots) using StatsBomb's native
    `play_pattern` tag -- no derived/proxy ingredient on the outcome side."""
    counts: Dict[str, List[int]] = {}
    for e in events:
        if (e.get("type") or {}).get("name") != "Shot":
            continue
        team = (e.get("team") or {}).get("name")
        if not team:
            continue
        c = counts.setdefault(team, [0, 0])
        c[1] += 1
        if ((e.get("play_pattern") or {}).get("name")) == "From Counter":
            c[0] += 1
    return {t: (v[0], v[1]) for t, v in counts.items()}


def _accumulate(events: List[Dict[str, Any]], acc: Dict[str, List[float]]) -> None:
    cg, sg = _match_clusters(events)
    acc["cluster_gap"].extend(cg)
    acc["single_gap"].extend(sg)

    teams_stats = _per_match_team_stats(events)
    counter = _counter_share(events)
    names = list(teams_stats.keys())
    if len(names) != 2:
        return
    for n in names:
        d = teams_stats[n]
        if d["def_x_n"] == 0 or d["shot_x_n"] == 0:
            continue
        block_proxy = abs(d["def_x_sum"] / d["def_x_n"] - d["shot_x_sum"] / d["shot_x_n"])
        n_counter, n_total = counter.get(n, (0, 0))
        if n_total == 0:
            continue
        acc["block_proxy"].append(block_proxy)
        acc["counter_share"].append(n_counter / n_total)


def _score_rebound(acc: Dict[str, List[float]]) -> Tuple[float, float]:
    """Welch t-test cluster-gap vs single-shot-gap -- (effect, p)."""
    if not (acc["cluster_gap"] and acc["single_gap"]):
        return 0.0, float("nan")
    _, p = stats.ttest_ind(acc["cluster_gap"], acc["single_gap"], equal_var=False)
    eff = (sum(acc["cluster_gap"]) / len(acc["cluster_gap"])
           - sum(acc["single_gap"]) / len(acc["single_gap"]))
    return eff, p


def _score_block_counter(acc: Dict[str, List[float]]) -> Tuple[float, float]:
    """Pearson r block-depth-proxy vs own counterattack-shot share -- (effect, p)."""
    if len(acc["block_proxy"]) < 2:
        return 0.0, float("nan")
    r, p = stats.pearsonr(acc["block_proxy"], acc["counter_share"])
    return float(r), float(p)


def _row(hyp: str, n: int, effect: float, p: float, min_abs_effect: float, note: str) -> Dict[str, Any]:
    return {"hypothesis": hyp, "n": n, "effect": round(effect, 5), "p": float(p),
            "verdict": _verdict(p, effect, min_abs_effect), "note": note}


def run() -> List[Dict[str, Any]]:
    acc: Dict[str, List[float]] = {k: [] for k in (
        "cluster_gap", "single_gap", "block_proxy", "counter_share")}
    n_matches = 0
    for _, events in iter_all_event_files():
        n_matches += 1
        _accumulate(events, acc)

    eff, p = _score_rebound(acc)
    rows = [_row("xg_rebound_cluster_calibration",
                 len(acc["cluster_gap"]) + len(acc["single_gap"]), eff, p, MIN_EFFECT_XG,
                 "mean(summed cluster xG - goal indicator), cluster(n=%d) vs single-shot(n=%d) "
                 "possessions, n_matches_scanned=%d" % (
                     len(acc["cluster_gap"]), len(acc["single_gap"]), n_matches))]

    eff, p = _score_block_counter(acc)
    rows.append(_row("block_depth_counterattack_share", len(acc["block_proxy"]), eff, p, MIN_EFFECT_R,
                      "pearson r, |own def-action mean x - own shot mean x| block-depth proxy "
                      "(reused from validate_pressing_defense) vs own play_pattern=='From Counter' "
                      "share of shots, n=%d team-match units" % len(acc["block_proxy"])))

    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full__%d_matches" % n_matches
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def run_split_half() -> List[Dict[str, Any]]:
    """Even/odd match-index split -- the >=2-independent-groups evidence the
    honesty bar requires behind an affirmative (CONFIRMED_LOCAL) verdict; this
    ledger's corpus has no separate second corpus to reuse instead."""
    accs: Dict[str, Dict[str, List[float]]] = {
        half: {k: [] for k in ("cluster_gap", "single_gap", "block_proxy", "counter_share")}
        for half in ("A", "B")}
    i = 0
    for _, events in iter_all_event_files():
        _accumulate(events, accs["A" if i % 2 == 0 else "B"])
        i += 1

    rows = []
    for half, acc in accs.items():
        eff, p = _score_rebound(acc)
        rows.append(_row("xg_rebound_cluster_calibration__split_%s" % half,
                          len(acc["cluster_gap"]) + len(acc["single_gap"]), eff, p, MIN_EFFECT_XG,
                          "split-half(even/odd match index) robustness check, half=%s" % half))
        eff, p = _score_block_counter(acc)
        rows.append(_row("block_depth_counterattack_share__split_%s" % half,
                          len(acc["block_proxy"]), eff, p, MIN_EFFECT_R,
                          "split-half(even/odd match index) robustness check, half=%s" % half))

    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full__split_half"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run() + run_split_half():
        print("%-42s %-16s n=%-8d effect=%+.5f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds behave as declared."""
    assert _verdict(0.001, 0.5, 0.03) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.03) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.03) == "NOT_TESTABLE"
    assert _verdict(0.001, 0.01, 0.03) == "NULL_LOCAL"  # p ok but effect below bar
    print("self-check OK")
