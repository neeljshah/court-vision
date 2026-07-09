"""domains.soccer.knowledge.validate_ingame_state -- 4 UNTESTED in-match-state
mechanisms against the full local StatsBomb event cache (~3,400 matches, no
match_meta join needed). Leak audit: every check compares two windows WITHIN
the same match using StatsBomb's own elapsed-time clock (minute+second) --
contemporaneous/structural, not a forecast into a future match, so there is
no leak. One pass over the event cache feeds all four accumulators.

Run: python -m domains.soccer.knowledge.validate_ingame_state
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, extract_match_facts, iter_all_event_files
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_WINDOW_MIN = 5.0
SUB_WINDOW_MIN = 15.0
SETPIECE_TYPES = {"Corner", "Free Kick"}


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or p != p:  # NaN-safe
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _accumulate(facts: Dict[str, Any], acc: Dict[str, List[float]]) -> None:
    shots = facts["shots"]
    match_len = facts["match_len"]

    # 1) red_card_suppresses_shot_rate: exactly one sending-off this match.
    if len(facts["red_cards"]) == 1:
        t_card, team = facts["red_cards"][0]
        if t_card >= MIN_WINDOW_MIN and (match_len - t_card) >= MIN_WINDOW_MIN:
            team_shots = [t for (tm, t, _, _) in shots if tm == team]
            before = sum(1 for t in team_shots if t < t_card) / t_card
            after = sum(1 for t in team_shots if t >= t_card) / (match_len - t_card)
            acc["redcard_before"].append(before)
            acc["redcard_after"].append(after)

    # 2) leading_team_shot_rate_suppression: state segments from goal timeline.
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
            dur = {"leading": 0.0, "tied": 0.0}
            cnt = {"leading": 0, "tied": 0}
            for t0, t1, diff_a in segments:
                d = t1 - t0
                if d <= 0:
                    continue
                diff_x = diff_a if team == teams[0] else -diff_a
                state = "leading" if diff_x > 0 else ("tied" if diff_x == 0 else None)
                if state is None:
                    continue
                dur[state] += d
                cnt[state] += sum(1 for (tm, t, _, _) in shots if tm == team and t0 <= t < t1)
            if dur["leading"] >= MIN_WINDOW_MIN and dur["tied"] >= MIN_WINDOW_MIN:
                acc["leading_rate"].append(cnt["leading"] / dur["leading"])
                acc["tied_rate"].append(cnt["tied"] / dur["tied"])

    # 3) substitution_shot_rate_dip: first sub per team, +/-15 min window.
    for team, sub_t in facts["subs"].items():
        w_before = min(SUB_WINDOW_MIN, sub_t)
        w_after = min(SUB_WINDOW_MIN, match_len - sub_t)
        if w_before >= 10.0 and w_after >= 10.0:
            team_shots = [t for (tm, t, _, _) in shots if tm == team]
            n_before = sum(1 for t in team_shots if sub_t - w_before <= t < sub_t)
            n_after = sum(1 for t in team_shots if sub_t <= t < sub_t + w_after)
            acc["sub_before"].append(n_before / w_before)
            acc["sub_after"].append(n_after / w_after)

    # 4) setpiece_vs_openplay_conversion: pooled shot-level, all matches.
    for _, _, is_goal, shot_type in shots:
        if shot_type == "Open Play":
            acc["openplay_goal"].append(float(is_goal))
        elif shot_type in SETPIECE_TYPES:
            acc["setpiece_goal"].append(float(is_goal))


def _row(hyp: str, n: int, effect: float, p: float, note: str, min_eff: float) -> Dict[str, Any]:
    return {"hypothesis": hyp, "n": n, "effect": round(effect, 5), "p": float(p),
            "verdict": _verdict(p, effect, min_eff), "note": note}


def run() -> List[Dict[str, Any]]:
    acc: Dict[str, List[float]] = {k: [] for k in (
        "redcard_before", "redcard_after", "leading_rate", "tied_rate",
        "sub_before", "sub_after", "openplay_goal", "setpiece_goal")}
    n_matches = 0
    for _, events in iter_all_event_files():
        n_matches += 1
        _accumulate(extract_match_facts(events), acc)

    rows = []
    t, p = stats.ttest_rel(acc["redcard_after"], acc["redcard_before"])
    eff = (sum(acc["redcard_after"]) - sum(acc["redcard_before"])) / len(acc["redcard_after"])
    rows.append(_row("red_card_suppresses_shot_rate", len(acc["redcard_before"]), eff, p,
                      "shots/min after send-off vs before, same team+match, n_matches_scanned=%d" % n_matches, 0.05))

    t, p = stats.ttest_rel(acc["leading_rate"], acc["tied_rate"])
    eff = (sum(acc["leading_rate"]) - sum(acc["tied_rate"])) / len(acc["leading_rate"])
    rows.append(_row("leading_team_shot_rate_suppression", len(acc["leading_rate"]), eff, p,
                      "team-match units, shots/min while leading vs tied", 0.02))

    t, p = stats.ttest_rel(acc["sub_after"], acc["sub_before"])
    eff = (sum(acc["sub_after"]) - sum(acc["sub_before"])) / len(acc["sub_after"])
    rows.append(_row("substitution_shot_rate_change", len(acc["sub_before"]), eff, p,
                      "shots/min in 15min after 1st sub vs 15min before, per team-match", 0.05))

    a, b = acc["setpiece_goal"], acc["openplay_goal"]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    eff = sum(a) / len(a) - sum(b) / len(b)
    rows.append(_row("setpiece_vs_openplay_conversion", len(a) + len(b), eff, p,
                      "goal rate set-piece (n=%d) vs open-play (n=%d)" % (len(a), len(b)), 0.01))

    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full__%d_matches" % n_matches
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-8d effect=%+.5f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds behave as declared."""
    assert _verdict(0.001, 0.5, 0.05) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.05) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.05) == "NOT_TESTABLE"
    print("self-check OK")
