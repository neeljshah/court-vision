"""domains.soccer.knowledge.validate_event_windows -- 3 UNTESTED event-
triggered mechanisms (mechanisms.md #20 goalkeeper distribution vs possession
retention, #21 tactical-shift shot-rate change, #22 injury-time added-goals
rate) against the full local StatsBomb event cache. Leak audit: #20 uses the
pass's own recorded outcome (a fact resolved the instant the pass happens);
#21 mirrors the substitution before/after design in validate_ingame_state.py
(within-match, contemporaneous); #22 compares goal-rate-per-minute between
StatsBomb's own added-time and regulation-time windows, both already-played.

Run: python -m domains.soccer.knowledge.validate_event_windows
"""
from __future__ import annotations

from typing import Any, Dict, List

from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

from domains.soccer.knowledge._data import LEDGER_PATH, iter_all_event_files
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
SHORT_HEIGHTS = {"Ground Pass", "Low Pass"}
BAD_OUTCOMES = {"Incomplete", "Out", "Pass Offside", "Unknown"}
MIN_WINDOW_MIN = 10.0


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or p != p:
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def goalkeeper_distribution_vs_retention(goal_kicks: List[tuple]) -> Dict[str, Any]:
    short_ok = short_n = long_ok = long_n = 0
    for height, retained in goal_kicks:
        if height in SHORT_HEIGHTS:
            short_n += 1
            short_ok += int(retained)
        elif height == "High Pass":
            long_n += 1
            long_ok += int(retained)
    stat, p_val = proportions_ztest([short_ok, long_ok], [short_n, long_n])
    eff = (short_ok / short_n) - (long_ok / long_n)
    return {"hypothesis": "goalkeeper_distribution_vs_retention", "n": short_n + long_n,
            "effect": round(float(eff), 4), "p": float(p_val), "verdict": _verdict(p_val, 0.02, eff),
            "note": "goal-kick retention rate, short/ground (%.4f, n=%d) vs long/high (%.4f, n=%d)"
                    % (short_ok / short_n, short_n, long_ok / long_n, long_n)}


def _match_tactical_shift_facts(events: List[Dict[str, Any]]) -> List[tuple]:
    """Per-team (t_shift, before_rate, after_rate) for this one match."""
    shifts: Dict[str, float] = {}
    shots: Dict[str, List[float]] = {}
    match_len = 0.0
    for e in events:
        t_min = e["minute"] + e["second"] / 60.0
        match_len = max(match_len, t_min)
        team = (e.get("team") or {}).get("name")
        if not team:
            continue
        if e["type"]["name"] == "Tactical Shift" and team not in shifts:
            shifts[team] = t_min
        elif e["type"]["name"] == "Shot":
            shots.setdefault(team, []).append(t_min)
    out = []
    for team, t_shift in shifts.items():
        if t_shift < MIN_WINDOW_MIN or (match_len - t_shift) < MIN_WINDOW_MIN:
            continue
        team_shots = shots.get(team, [])
        before = sum(1 for t in team_shots if t < t_shift) / t_shift
        after = sum(1 for t in team_shots if t >= t_shift) / (match_len - t_shift)
        out.append((before, after))
    return out


def tactical_shift_shot_rate_change(pairs: List[tuple]) -> Dict[str, Any]:
    before_rates = [b for b, _ in pairs]
    after_rates = [a for _, a in pairs]
    t, p = stats.ttest_rel(after_rates, before_rates)
    eff = float(sum(after_rates) / len(after_rates) - sum(before_rates) / len(before_rates))
    return {"hypothesis": "tactical_shift_shot_rate_change", "n": len(before_rates), "effect": round(eff, 5),
            "p": float(p), "verdict": _verdict(p, 0.005, eff),
            "note": "shots/min after own team's 1st Tactical Shift vs before, paired, n=%d team-match units"
                    % len(before_rates)}


def injury_time_added_goals_rate(match_period_goals: List[Any]) -> Dict[str, Any]:
    reg_goals = add_goals = 0
    reg_minutes = add_minutes = 0.0
    for periods in match_period_goals:
        p1_max, p2_max, p1_goals, p2_goals = periods
        reg_minutes += 45.0 + max(0.0, min(p2_max, 90.0) - 45.0)
        add_minutes += max(0.0, p1_max - 45.0) + max(0.0, p2_max - 90.0)
        reg_goals += p1_goals["reg"] + p2_goals["reg"]
        add_goals += p1_goals["add"] + p2_goals["add"]
    stat, p_val = proportions_ztest([add_goals, reg_goals], [add_minutes, reg_minutes])
    rate_add = add_goals / add_minutes if add_minutes else float("nan")
    rate_reg = reg_goals / reg_minutes
    eff = rate_add - rate_reg
    return {"hypothesis": "injury_time_added_goals_rate", "n": int(reg_goals + add_goals),
            "effect": round(float(eff), 5), "p": float(p_val), "verdict": _verdict(p_val, 0.01, eff),
            "note": "goals-per-minute, added-time (%.5f, %d goals / %.0f min) vs regulation (%.5f, %d goals "
                    "/ %.0f min)" % (rate_add, add_goals, add_minutes, rate_reg, reg_goals, reg_minutes)}


def _extract_period_goals(events: List[Dict[str, Any]]) -> Any:
    p1_max = p2_max = 0.0
    p1_goals = {"reg": 0, "add": 0}
    p2_goals = {"reg": 0, "add": 0}
    for e in events:
        t_min = e["minute"] + e["second"] / 60.0
        period = e.get("period")
        if period == 1:
            p1_max = max(p1_max, t_min)
        elif period == 2:
            p2_max = max(p2_max, t_min)
        is_goal = e["type"]["name"] == "Own Goal Against" or (
            e["type"]["name"] == "Shot" and (e.get("shot") or {}).get("outcome", {}).get("name") == "Goal")
        if is_goal and period == 1:
            p1_goals["add" if t_min > 45 else "reg"] += 1
        elif is_goal and period == 2:
            p2_goals["add" if t_min > 90 else "reg"] += 1
    return (p1_max, p2_max, p1_goals, p2_goals)


def _match_goal_kicks(events: List[Dict[str, Any]]) -> List[tuple]:
    out = []
    for e in events:
        if e["type"]["name"] != "Pass":
            continue
        p = e.get("pass") or {}
        if (p.get("type") or {}).get("name") != "Goal Kick":
            continue
        height = (p.get("height") or {}).get("name")
        outcome = (p.get("outcome") or {}).get("name")
        out.append((height, outcome not in BAD_OUTCOMES))
    return out


def run() -> List[Dict[str, Any]]:
    goal_kicks: List[tuple] = []
    shift_pairs: List[tuple] = []
    period_goals: List[Any] = []
    for _, events in iter_all_event_files():
        goal_kicks.extend(_match_goal_kicks(events))
        shift_pairs.extend(_match_tactical_shift_facts(events))
        period_goals.append(_extract_period_goals(events))
    rows = [goalkeeper_distribution_vs_retention(goal_kicks), tactical_shift_shot_rate_change(shift_pairs),
            injury_time_added_goals_rate(period_goals)]
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_events_full_cache"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-36s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
