"""
TOTAL & PACE MOVERS — who, by their presence, pushes their games OVER/UNDER
and speeds up / slows down the game.

This is the "scoring-environment" sibling of the margin/win outcome cut. For
every rotation player we already have his IN (he played) vs OUT (he sat, same
roster window) split of the GAME TOTAL and the PACE in
`player_availability.json`. Here we re-rank players purely on:

  - total_swing = total_in - total_out  (avg combined game points IN minus OUT;
        positive => his games go OVER when he plays, i.e. he RAISES the total)
  - pace_swing  = pace_in  - pace_out   (avg possessions/40 IN minus OUT;
        positive => the game is FASTER when he plays)

and cross-reference each mover with his team's full-season scoring environment
(`game_control.json`: total_desc, total_vs_league_desc) and 2024-25 on/off net
context (`player_onoff.json`) for color.

Output: data/cache/intel_outcome/player_total_pace_impact.json   (SCOUTING)

GATING (inherited from player_availability inclusion + the margin board's
gates so the boards are apples-to-apples):
  - inclusion: n_out >= 4 & n_in >= 10  (already enforced upstream; re-checked)
  - "clean" board = rotation/starter player (min_in >= 20 mpg), confound_flag
        False, confidence == "high"  (n_out >= 8 & n_in >= 25 & no confound).
  - everything that passes inclusion but not the clean gate is carried on the
        "confounded / low-confidence" board, shown with its flags.

CONFOUND / LEAK NOTE
--------------------
total_swing & pace_swing inherit the SAME schedule confound as margin_swing:
when a player sits, opponent quality, other injuries, rest, and tank /
load-management spots co-vary, and a different opponent slate changes both the
total and the pace. `confound_flag` (|opp_strength_diff| >= 0.06) marks rows
where the OUT slate was materially different. Small n_out is noisy. This is
ASSOCIATION, NOT CAUSATION, and is SCOUTING ONLY — availability-driven total/
pace betting was REJECTED (no graded game-line edge from this layer; see
docs/_audits/INTEL_CAMPAIGN_PUNCHLIST.md). Defer to the market on the game
total; use this to understand WHY a total/pace might move.

SCOUTING ONLY. No betting code, no model wiring. New artifact only.
"""

import io
import json
import os
from statistics import mean

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))  # .../nba-ai-system
SEASON = "2025-26"

INTEL_DIR = os.path.join(BASE, "data", "cache", "intel_outcome")
AVAIL_PATH = os.path.join(INTEL_DIR, "player_availability.json")
ONOFF_PATH = os.path.join(INTEL_DIR, "player_onoff.json")
GAMECTL_PATH = os.path.join(INTEL_DIR, "game_control.json")
OUT_PATH = os.path.join(INTEL_DIR, "player_total_pace_impact.json")

# clean-board gates (match the margin board)
MIN_MIN_IN = 20.0          # rotation/starter floor; deep-bench swings are artifacts
CLEAN_CONF = "high"        # n_out>=8 & n_in>=25 & no confound
# inclusion gates (re-checked; availability already applies these)
MIN_N_OUT = 4
MIN_N_IN = 10
# how many to carry on each ranked board
TOP_N = 40


def _load(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _round(x, n=3):
    return round(x, n) if isinstance(x, (int, float)) else x


def main():
    avail = _load(AVAIL_PATH)
    onoff = _load(ONOFF_PATH)
    gamectl = _load(GAMECTL_PATH)

    avail_players = avail["players"]
    onoff_players = onoff.get("players", {})
    teams_env = gamectl.get("teams", {})
    league_env = gamectl.get("league", {})
    league_total = league_env.get("avg_total")

    players_out = {}
    for pid, p in avail_players.items():
        n_in = p.get("n_in", 0)
        n_out = p.get("n_out", 0)
        # inclusion (defensive re-check; upstream already enforces)
        if n_in < MIN_N_IN or n_out < MIN_N_OUT:
            continue
        total_swing = p.get("total_swing")
        pace_swing = p.get("pace_swing")
        if total_swing is None or pace_swing is None:
            continue

        team = p.get("team")
        min_in = p.get("min_in", 0.0)
        role = p.get("role", "")
        confidence = p.get("confidence", "low")
        confound = bool(p.get("confound_flag", False))

        # team scoring-environment context (cross-reference #3)
        tenv = teams_env.get(team, {}) if team else {}
        team_ctx = {
            "team_total_desc": tenv.get("total_desc"),
            "team_total_vs_league": tenv.get("total_vs_league_desc"),
        }

        # 2024-25 on/off net context for color (prior season)
        oo = onoff_players.get(pid, {})
        onoff_ctx = {
            "onoff_swing_2024_25": oo.get("onoff_swing"),
            "onoff_minutes_2024_25": oo.get("minutes"),
        }

        # the "clean" gate: genuine rotation player, no confound, high confidence
        is_clean = (
            min_in >= MIN_MIN_IN
            and not confound
            and confidence == CLEAN_CONF
        )

        players_out[pid] = {
            "name": p.get("name"),
            "team": team,
            "vault_slug": p.get("vault_slug"),
            "role": role,
            "min_in": _round(min_in, 1),
            "n_in": n_in,
            "n_out": n_out,
            "total_in": _round(p.get("total_in")),
            "total_out": _round(p.get("total_out")),
            "total_swing": _round(total_swing),
            "pace_in": _round(p.get("pace_in")),
            "pace_out": _round(p.get("pace_out")),
            "pace_swing": _round(pace_swing),
            "opp_strength_diff": _round(p.get("opp_strength_diff")),
            "confidence": confidence,
            "confound_flag": confound,
            "confound_note": p.get("confound_note", ""),
            "is_clean": is_clean,
            **team_ctx,
            **onoff_ctx,
        }

    def board(key, reverse, clean_only):
        """Ranked list of pids by `key` (desc if reverse=True)."""
        rows = [
            (pid, r) for pid, r in players_out.items()
            if (r["is_clean"] if clean_only else True)
        ]
        rows.sort(key=lambda kv: kv[1][key], reverse=reverse)
        out = []
        for pid, r in rows[:TOP_N]:
            out.append({
                "pid": pid,
                "name": r["name"],
                "team": r["team"],
                "total_swing": r["total_swing"],
                "pace_swing": r["pace_swing"],
                "n_in": r["n_in"],
                "n_out": r["n_out"],
                "min_in": r["min_in"],
                "role": r["role"],
                "confidence": r["confidence"],
                "confound_flag": r["confound_flag"],
                "team_total_vs_league": r["team_total_vs_league"],
            })
        return out

    boards = {
        # CLEAN high-confidence boards (the headline scouting tables)
        "total_over_movers": board("total_swing", True, clean_only=True),
        "total_under_movers": board("total_swing", False, clean_only=True),
        "pace_up": board("pace_swing", True, clean_only=True),
        "pace_down": board("pace_swing", False, clean_only=True),
        # ALL-cohort boards (clean + confounded together) for completeness
        "total_over_movers_all": board("total_swing", True, clean_only=False),
        "total_under_movers_all": board("total_swing", False, clean_only=False),
        "pace_up_all": board("pace_swing", True, clean_only=False),
        "pace_down_all": board("pace_swing", False, clean_only=False),
    }

    n_clean = sum(1 for r in players_out.values() if r["is_clean"])
    n_confounded = sum(1 for r in players_out.values() if r["confound_flag"])

    # league pace context (for the note header): avg pace across all IN games
    pace_in_vals = [r["pace_in"] for r in players_out.values()
                    if isinstance(r["pace_in"], (int, float))]
    league_pace_ref = _round(mean(pace_in_vals), 1) if pace_in_vals else None

    out = {
        "meta": {
            "artifact": "player_total_pace_impact",
            "agent": "OUTCOME-IMPACT / total-&-pace movers",
            "season": SEASON,
            "generated_from": [
                "data/cache/intel_outcome/player_availability.json "
                "(total_swing, pace_swing, gates, confound flags) — PRIMARY 2025-26",
                "data/cache/intel_outcome/game_control.json "
                "(team scoring environment: total_desc, total_vs_league) — 2025-26",
                "data/cache/intel_outcome/player_onoff.json "
                "(2024-25 on/off net context, prior-season color)",
            ],
            "units": {
                "total_in/out": "avg combined both-teams final game points in his "
                                "IN / OUT games",
                "total_swing": "total_in - total_out (points). POSITIVE => his "
                               "games go OVER when he plays (he RAISES the total); "
                               "NEGATIVE => games go UNDER without changing him.",
                "pace_in/out": "avg possessions-per-40 (from season_games) in his "
                               "IN / OUT games",
                "pace_swing": "pace_in - pace_out (poss/40). POSITIVE => the game "
                              "is FASTER when he plays; NEGATIVE => slower.",
                "opp_strength_diff": "opp_strength_in - opp_strength_out (>0 => he "
                                     "played the tougher slate). |.|>=0.06 sets "
                                     "confound_flag.",
                "team_total_desc": "team's full-season descriptive avg game total "
                                   "(scouting, hindsight) from game_control",
                "team_total_vs_league": "team_total_desc minus league avg total "
                                        "(>0 => an already-OVER scoring environment)",
                "onoff_swing_2024_25": "2024-25 on-court minus off-court net rating "
                                       "(pts/100); prior-season color only",
            },
            "gates": {
                "inclusion": f"n_out >= {MIN_N_OUT} & n_in >= {MIN_N_IN} "
                             "(inherited from player_availability)",
                "clean_board": f"min_in >= {MIN_MIN_IN} mpg & confound_flag False & "
                               f"confidence == '{CLEAN_CONF}' "
                               "(n_out>=8 & n_in>=25 & no confound). The headline "
                               "*_movers / pace_* boards are CLEAN-only; the *_all "
                               "boards add confounded/low-confidence rows.",
                "top_n_per_board": TOP_N,
            },
            "league_context": {
                "league_avg_total": league_total,
                "league_pace_ref_in_games": league_pace_ref,
            },
            "coverage": {
                "n_players_scored": len(players_out),
                "n_clean_high_confidence": n_clean,
                "n_confound_flagged": n_confounded,
            },
            "caveats": [
                "ASSOCIATION, NOT CAUSATION. total_swing & pace_swing inherit the "
                "SAME schedule confound as margin_swing: when a player sits, "
                "opponent quality, other injuries, rest, and tank/load-management "
                "spots co-vary, and a different opponent slate moves both the total "
                "and the pace. confound_flag marks materially different OUT slates.",
                "Small n_out is noisy; pace_swing especially is a thin difference "
                "of two season-pace means and should be read directionally.",
                "Team scoring-environment fields (total_desc) are DESCRIPTIVE "
                "full-season hindsight aggregates, included for context only — a "
                "sibling agent proved using a full-season total as predictive is a "
                "leakage trap. Do NOT treat them as forward-looking.",
                "on/off net is 2024-25 (prior season), teammate-confounded, color "
                "only — not a 2025-26 ground truth.",
                "SCOUTING ONLY. Availability-driven total/pace betting was REJECTED "
                "(no graded game-line edge on >=2 corpora from this layer). Defer to "
                "the market on the game total/pace; use this to understand WHY they "
                "might move.",
            ],
        },
        "players": players_out,
        **boards,
    }

    os.makedirs(INTEL_DIR, exist_ok=True)
    with io.open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"[total_pace_movers] wrote {OUT_PATH}")
    print(f"  players scored : {len(players_out)}")
    print(f"  clean high-conf: {n_clean}")
    print(f"  confound-flagged: {n_confounded}")
    print(f"  league avg total: {league_total}  league pace ref: {league_pace_ref}")
    for b in ("total_over_movers", "total_under_movers", "pace_up", "pace_down"):
        head = out[b][:3]
        tag = ", ".join(f"{r['name']} ({r['total_swing'] if 'total' in b else r['pace_swing']:+})"
                        for r in head)
        print(f"  {b}[:3]: {tag}")


if __name__ == "__main__":
    main()
