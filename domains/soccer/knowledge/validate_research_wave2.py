"""domains.soccer.knowledge.validate_research_wave2 -- research-wave-2 UNTESTED
rows #37 (first-substitution timing moderates the shot-rate shift) and #38
(trailing-team shot rate vs tied, extends #9's leading/tied state machine)
from domains/soccer/knowledge/mechanisms.md, against the full local StatsBomb
event cache. Leak audit: both checks compare windows WITHIN the same match
using StatsBomb's own elapsed-time clock (minute+second) -- contemporaneous/
structural, not a forecast into a future match, so there is no leak. Mirrors
the sibling validate_ingame_state.py pattern exactly; reuses
extract_match_facts/iter_all_event_files from _data.py rather than
re-deriving match facts.

Run: python -m domains.soccer.knowledge.validate_research_wave2
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, extract_match_facts, iter_all_event_files
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_EFFECT = 0.02  # shots/min, same declared-bar convention as #9's family
SUB_WINDOW_MIN = 15.0
EARLY_SUB_MAX_MIN = 60.0  # row #37: sub_t<=60 -> "early" bucket
LATE_SUB_MIN_MIN = 75.0  # row #37: sub_t>=75 -> "late" bucket
MIN_STATE_WINDOW_MIN = 5.0  # row #38: same >=5min-both-states floor as #9


def _verdict(p: float, effect: float, min_abs_effect: float = MIN_EFFECT) -> str:
    if p is None or p != p:  # NaN-safe
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _accumulate(facts: Dict[str, Any], acc: Dict[str, List[float]]) -> None:
    shots = facts["shots"]
    match_len = facts["match_len"]

    # #37: first-sub-per-team (facts["subs"]), same before/after 15min
    # shots-per-minute window + >=10min-both-sides floor as #11, but bucketed
    # by how early/late the sub landed instead of pooled.
    for team, sub_t in facts["subs"].items():
        w_before = min(SUB_WINDOW_MIN, sub_t)
        w_after = min(SUB_WINDOW_MIN, match_len - sub_t)
        if w_before >= 10.0 and w_after >= 10.0:
            team_shots = [t for (tm, t, _, _) in shots if tm == team]
            n_before = sum(1 for t in team_shots if sub_t - w_before <= t < sub_t)
            n_after = sum(1 for t in team_shots if sub_t <= t < sub_t + w_after)
            shift = (n_after / w_after) - (n_before / w_before)
            if sub_t <= EARLY_SUB_MAX_MIN:
                acc["early_shift"].append(shift)
            elif sub_t >= LATE_SUB_MIN_MIN:
                acc["late_shift"].append(shift)

    # #38: same leading/tied state-segment loop as #9's _accumulate, extended
    # to also bucket the previously-discarded diff_x<0 case as "trailing".
    teams = facts["teams"]
    if len(teams) == 2 and match_len > 0:
        goals_sorted = sorted(facts["goals"])
        segments: List[Tuple[float, float, int]] = []
        cur_diff, prev_t = 0, 0.0
        for gt, gteam in goals_sorted:
            segments.append((prev_t, gt, cur_diff))
            cur_diff += 1 if gteam == teams[0] else -1
            prev_t = gt
        segments.append((prev_t, match_len, cur_diff))
        for team in teams:
            dur = {"trailing": 0.0, "tied": 0.0}
            cnt = {"trailing": 0, "tied": 0}
            for t0, t1, diff_a in segments:
                d = t1 - t0
                if d <= 0:
                    continue
                diff_x = diff_a if team == teams[0] else -diff_a
                state = "trailing" if diff_x < 0 else ("tied" if diff_x == 0 else None)
                if state is None:
                    continue
                dur[state] += d
                cnt[state] += sum(1 for (tm, t, _, _) in shots if tm == team and t0 <= t < t1)
            if dur["trailing"] >= MIN_STATE_WINDOW_MIN and dur["tied"] >= MIN_STATE_WINDOW_MIN:
                acc["trailing_rate"].append(cnt["trailing"] / dur["trailing"])
                acc["tied_rate"].append(cnt["tied"] / dur["tied"])


def _row(hyp: str, n: int, effect: float, p: float, note: str) -> Dict[str, Any]:
    return {"hypothesis": hyp, "n": n, "effect": round(effect, 5), "p": float(p),
            "verdict": _verdict(p, effect), "note": note}


def _score_sub_timing(acc: Dict[str, List[float]]) -> Tuple[float, float]:
    """Welch t-test early-sub vs late-sub (after-before) shift -- (effect, p)."""
    if not (acc["early_shift"] and acc["late_shift"]):
        return 0.0, float("nan")
    _, p = stats.ttest_ind(acc["early_shift"], acc["late_shift"], equal_var=False)
    eff = (sum(acc["early_shift"]) / len(acc["early_shift"])
           - sum(acc["late_shift"]) / len(acc["late_shift"]))
    return eff, p


def _score_trailing(acc: Dict[str, List[float]]) -> Tuple[float, float]:
    """Paired t-test trailing-rate vs tied-rate -- (effect, p)."""
    if not acc["trailing_rate"]:
        return 0.0, float("nan")
    _, p = stats.ttest_rel(acc["trailing_rate"], acc["tied_rate"])
    eff = (sum(acc["trailing_rate"]) - sum(acc["tied_rate"])) / len(acc["trailing_rate"])
    return eff, p


def run() -> List[Dict[str, Any]]:
    acc: Dict[str, List[float]] = {k: [] for k in (
        "early_shift", "late_shift", "trailing_rate", "tied_rate")}
    n_matches = 0
    for _, events in iter_all_event_files():
        n_matches += 1
        _accumulate(extract_match_facts(events), acc)

    eff, p = _score_sub_timing(acc)
    rows = [_row("substitution_timing_moderates_shift",
                 len(acc["early_shift"]) + len(acc["late_shift"]), eff, p,
                 "shift(after-before) early-sub(sub_t<=60,n=%d) vs late-sub(sub_t>=75,n=%d) shots/min, n_matches_scanned=%d" % (
                     len(acc["early_shift"]), len(acc["late_shift"]), n_matches))]

    eff, p = _score_trailing(acc)
    rows.append(_row("trailing_team_shot_rate", len(acc["trailing_rate"]), eff, p,
                      "team-match units, shots/min while trailing vs tied"))

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
        half: {k: [] for k in ("early_shift", "late_shift", "trailing_rate", "tied_rate")}
        for half in ("A", "B")}
    i = 0
    for _, events in iter_all_event_files():
        _accumulate(extract_match_facts(events), accs["A" if i % 2 == 0 else "B"])
        i += 1

    rows = []
    for half, acc in accs.items():
        eff, p = _score_sub_timing(acc)
        rows.append(_row("substitution_timing_moderates_shift__split_%s" % half,
                          len(acc["early_shift"]) + len(acc["late_shift"]), eff, p,
                          "split-half(even/odd match index) robustness check, half=%s" % half))
        eff, p = _score_trailing(acc)
        rows.append(_row("trailing_team_shot_rate__split_%s" % half, len(acc["trailing_rate"]), eff, p,
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
    assert _verdict(0.001, 0.5) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5) == "NOT_TESTABLE"
    print("self-check OK")
