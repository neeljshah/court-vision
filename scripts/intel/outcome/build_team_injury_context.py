"""
build_team_injury_context.py  --  TEAM INJURY-CONTEXT / FRAGILITY layer
=======================================================================

OUTCOME-IMPACT campaign deliverable: for each of the 30 teams, quantify how much
its outcome strength collapses when its load-bearing players sit, and identify the
single most INDISPENSABLE player on the roster.

This is a TEAM-LEVEL AGGREGATION on top of the player-level "who decides games"
artifact. It does NOT recompute any IN/OUT split or touch box scores -- it reads
the already-validated, leak-safe, opponent-adjusted player margin swings and rolls
them up per team.

INPUT (preferred, opponent-ADJUSTED -- cleaner):
  data/cache/intel_outcome/player_availability_v2.json
    Per player: margin_swing_adj (opponent-SRS-neutralized IN-vs-OUT margin swing,
    leak-safe as-of opponent strength), n_in / n_out, role, confidence, confound_flag.
  (falls back to player_availability.json -> margin_swing_raw / margin_out if v2 absent)

  data/cache/intel_outcome/team_strength.json
    Per team: srs_rating (opponent-adjusted simple rating system, point scale) + rank.

METHOD (per team)
-----------------
1. MOST LOAD-BEARING players. Among the team's roster members that clear the
   inclusion floor (n_out >= MIN_OUT), the most indispensable are those with the
   LARGEST POSITIVE opponent-adjusted margin swing -- the team falls the most in
   the games they miss. We rank each team's top-3 by margin_swing_adj and carry the
   confidence (high/medium/low) and n_out so a reader can gate small samples.

2. TEAM FRAGILITY SCORE. = the adjusted margin swing of the team's single most
   indispensable player (the #1 above). It answers: "how many points of margin does
   this team lose when its most load-bearing player sits?" Bigger => more fragile
   (the team collapses without one man). Smaller / negative => more robust (depth
   absorbs the absence, or no single player is decisive in the data). All 30 teams
   are ranked most-fragile -> most-robust on this score.

   We deliberately anchor fragility on the BEST player's swing rather than an
   average over the roster: injury fragility is about the worst-case single absence,
   and averaging would dilute a genuine star dependency with bench noise. A
   depth_note flags teams whose #2/#3 swings are also large (multiple load-bearers)
   vs teams with one decisive star and a flat tail.

HONEST CAVEATS (carried into the artifact + note)
-------------------------------------------------
* ASSOCIATION, NOT CAUSATION. A margin swing is confounded by co-absences (stars
  often sit together), schedule, rest / load-management spots, and home/road
  balance. The opponent-QUALITY confound is removed (v2 adjusts via opponent SRS,
  leak-safe), but the others remain.
* Small n_out games are noisy -- gate on confidence / n_out before trusting a rank.
* SCOUTING intelligence only. Availability-based betting was REJECTED in this repo
  (see memory: availability props were not a graded edge); this layer is for
  context / scouting, not a bet signal.

OUTPUT: data/cache/intel_outcome/team_injury_context.json
  { meta:{season, source, method, caveats},
    teams:{ "<TRI>": { fragility_score, srs_baseline, srs_rank,
                       most_indispensable:[{pid,name,margin_swing_adj,n_out,confidence,role}],
                       depth_note } },
    fragility_ranking:[ {rank, team, fragility_score, srs_baseline,
                         top_player, top_player_pid, confidence} ] }

DISCIPLINE: new file only. Read-only on all inputs. No note edits, no git.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
INTEL = os.path.join(ROOT, "data", "cache", "intel_outcome")

AVAIL_V2 = os.path.join(INTEL, "player_availability_v2.json")
AVAIL_V1 = os.path.join(INTEL, "player_availability.json")
TEAM_STRENGTH = os.path.join(INTEL, "team_strength.json")
OUT_PATH = os.path.join(INTEL, "team_injury_context.json")

# Inclusion floor: a player needs at least this many OUT games for the IN/OUT
# margin swing to be worth ranking (mirrors the availability artifact's min_out).
MIN_OUT = 4
# Rotation-minutes floor. A deep-bench player who only suits up when the team is
# already healthy/winning shows a huge positive "swing" that is a CO-AVAILABILITY
# artifact (reverse causation), not indispensability. We require real rotation
# minutes so the indispensable board surfaces genuine load-bearers, not garbage-time
# bodies. (Matches the v2 'who decides games' leaderboard's min_in>=20 gate.)
MIN_MINUTES = 20.0
# A "decisive" swing for the depth note (points of margin lost when a player sits).
DECISIVE_SWING = 3.0
TOP_N = 3


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _swing_fields(avail_meta: Dict[str, Any]) -> Dict[str, str]:
    """Pick the swing key + label depending on whether v2 (adjusted) is in use."""
    artifact = (avail_meta or {}).get("artifact", "")
    if artifact == "player_availability_v2":
        return {"swing_key": "margin_swing_adj", "source": "v2_opponent_adjusted"}
    # v1 raw fallback
    return {"swing_key": "margin_swing_raw", "source": "v1_raw"}


def main() -> None:
    # --- inputs --------------------------------------------------------------
    if os.path.exists(AVAIL_V2):
        avail = _load(AVAIL_V2)
        used = "player_availability_v2.json"
    else:
        avail = _load(AVAIL_V1)
        used = "player_availability.json"

    swing_cfg = _swing_fields(avail.get("meta", {}))
    swing_key = swing_cfg["swing_key"]

    strength = _load(TEAM_STRENGTH)
    team_strength = strength.get("teams", {})

    players: Dict[str, Dict[str, Any]] = avail.get("players", {})

    # --- bucket players by team, keep only gate-clearing rows ----------------
    # Gate on n_out (sample) AND rotation minutes (min_in>=MIN_MINUTES) so the
    # indispensable board surfaces real load-bearers, not deep-bench bodies whose
    # high swing is a co-availability artifact.
    by_team: Dict[str, List[Dict[str, Any]]] = {}
    for pid, p in players.items():
        team = p.get("team")
        if not team:
            continue
        n_out = int(p.get("n_out", 0) or 0)
        if n_out < MIN_OUT:
            continue
        min_in = float(p.get("min_in", 0.0) or 0.0)
        if min_in < MIN_MINUTES:
            continue
        # swing value (adjusted where available); skip rows missing it
        swing = p.get(swing_key)
        if swing is None:
            continue
        by_team.setdefault(team, []).append(
            {
                "pid": pid,
                "name": p.get("name", pid),
                "vault_slug": p.get("vault_slug", ""),
                "role": p.get("role", ""),
                "min_in": round(min_in, 1),
                "margin_swing_adj": round(float(swing), 3),
                "n_in": int(p.get("n_in", 0) or 0),
                "n_out": n_out,
                "confidence": p.get("confidence", "low"),
                "confound_flag": bool(p.get("confound_flag", False)),
            }
        )

    # --- per-team rollup -----------------------------------------------------
    teams_out: Dict[str, Any] = {}
    ranking_rows: List[Dict[str, Any]] = []

    # iterate over the full strength roster so all 30 teams appear even if a team
    # somehow has no qualifying player row.
    for tri in sorted(team_strength.keys()):
        ts = team_strength[tri]
        srs = round(float(ts.get("srs_rating", 0.0) or 0.0), 3)
        srs_rank = ts.get("srs_rank")

        roster = by_team.get(tri, [])
        # most load-bearing = largest POSITIVE adjusted swing first
        roster_sorted = sorted(
            roster, key=lambda r: r["margin_swing_adj"], reverse=True
        )
        top = roster_sorted[:TOP_N]

        if top and top[0]["margin_swing_adj"] > 0:
            fragility = top[0]["margin_swing_adj"]
            lead = top[0]
        else:
            # No single player has a positive (team-falls-without-him) swing.
            # Treat as maximally robust in the ranking; fragility = best available
            # swing (could be <=0) so the score is still a real number, not None.
            fragility = top[0]["margin_swing_adj"] if top else 0.0
            lead = top[0] if top else None

        # depth_note: how many of the top-3 are decisive (>=DECISIVE_SWING), and
        # whether this is a one-man dependency or a multi-load-bearer roster.
        decisive = [
            r for r in top if r["margin_swing_adj"] >= DECISIVE_SWING
        ]
        if not lead or lead["margin_swing_adj"] <= 0:
            depth_note = (
                "robust: no single player shows a positive opponent-adjusted "
                "margin swing on this sample -- depth absorbs absences (or no "
                "decisive absence pattern is detectable)."
            )
        elif len(decisive) >= 2:
            depth_note = (
                f"multiple load-bearers: {len(decisive)} players each cost "
                f">= {DECISIVE_SWING:.0f} margin pts when out -- "
                "fragility is spread across the core, not one star."
            )
        elif len(decisive) == 1:
            depth_note = (
                f"single-point dependency: {lead['name']} is the lone decisive "
                f"absence (+{lead['margin_swing_adj']:.1f} swing); the next "
                "tier drops off -- thin behind the star."
            )
        else:
            depth_note = (
                "balanced: top absence swings are modest (< "
                f"{DECISIVE_SWING:.0f} pts) -- no one player is decisive."
            )

        most_indispensable = [
            {
                "pid": r["pid"],
                "name": r["name"],
                "vault_slug": r["vault_slug"],
                "role": r["role"],
                "min_in": r["min_in"],
                "margin_swing_adj": r["margin_swing_adj"],
                "n_out": r["n_out"],
                "n_in": r["n_in"],
                "confidence": r["confidence"],
                "confound_flag": r["confound_flag"],
            }
            for r in top
        ]

        # Confidence-gated lead: the team's best indispensable player restricted to
        # high/medium confidence (drops still-schedule-confounded / small-n leaders).
        # This is the credible companion to the raw-adjusted fragility score.
        gated = [
            r
            for r in roster_sorted
            if r["confidence"] in ("high", "medium") and r["margin_swing_adj"] > 0
        ]
        lead_gated = gated[0] if gated else None
        fragility_gated = (
            round(float(lead_gated["margin_swing_adj"]), 3) if lead_gated else None
        )

        teams_out[tri] = {
            "fragility_score": round(float(fragility), 3),
            "fragility_score_high_conf": fragility_gated,
            "srs_baseline": srs,
            "srs_rank": srs_rank,
            "most_indispensable": most_indispensable,
            "most_indispensable_high_conf": (
                {
                    "pid": lead_gated["pid"],
                    "name": lead_gated["name"],
                    "vault_slug": lead_gated["vault_slug"],
                    "role": lead_gated["role"],
                    "margin_swing_adj": lead_gated["margin_swing_adj"],
                    "n_out": lead_gated["n_out"],
                    "confidence": lead_gated["confidence"],
                }
                if lead_gated
                else None
            ),
            "depth_note": depth_note,
            "n_qualifying_players": len(roster),
        }

        ranking_rows.append(
            {
                "team": tri,
                "fragility_score": round(float(fragility), 3),
                "srs_baseline": srs,
                "srs_rank": srs_rank,
                "top_player": lead["name"] if lead else None,
                "top_player_pid": lead["pid"] if lead else None,
                "top_player_n_out": lead["n_out"] if lead else None,
                "confidence": lead["confidence"] if lead else None,
            }
        )

    # most-fragile -> most-robust
    ranking_rows.sort(key=lambda r: r["fragility_score"], reverse=True)
    for i, row in enumerate(ranking_rows, start=1):
        row["rank"] = i
    # reorder dict for readability (rank first)
    fragility_ranking = [
        {
            "rank": r["rank"],
            "team": r["team"],
            "fragility_score": r["fragility_score"],
            "srs_baseline": r["srs_baseline"],
            "srs_rank": r["srs_rank"],
            "top_player": r["top_player"],
            "top_player_pid": r["top_player_pid"],
            "top_player_n_out": r["top_player_n_out"],
            "confidence": r["confidence"],
        }
        for r in ranking_rows
    ]

    # Confidence-gated companion ranking: only teams whose top indispensable player
    # clears high/medium confidence. Teams with no credible single-absence signal
    # are listed at the bottom with a null score (read as "robust / undetectable").
    gated_rows = []
    for tri, t in teams_out.items():
        lead_g = t.get("most_indispensable_high_conf")
        gated_rows.append(
            {
                "team": tri,
                "fragility_score_high_conf": t.get("fragility_score_high_conf"),
                "srs_baseline": t["srs_baseline"],
                "srs_rank": t["srs_rank"],
                "top_player": lead_g["name"] if lead_g else None,
                "top_player_pid": lead_g["pid"] if lead_g else None,
                "top_player_n_out": lead_g["n_out"] if lead_g else None,
                "confidence": lead_g["confidence"] if lead_g else None,
            }
        )
    # sort: real scores most-fragile first, nulls (no credible signal) last
    gated_rows.sort(
        key=lambda r: (r["fragility_score_high_conf"] is not None,
                       r["fragility_score_high_conf"] or 0.0),
        reverse=True,
    )
    for i, row in enumerate(gated_rows, start=1):
        row["rank"] = i
    fragility_ranking_high_conf = [
        {
            "rank": r["rank"],
            "team": r["team"],
            "fragility_score_high_conf": r["fragility_score_high_conf"],
            "srs_baseline": r["srs_baseline"],
            "srs_rank": r["srs_rank"],
            "top_player": r["top_player"],
            "top_player_pid": r["top_player_pid"],
            "top_player_n_out": r["top_player_n_out"],
            "confidence": r["confidence"],
        }
        for r in gated_rows
    ]

    out = {
        "meta": {
            "artifact": "team_injury_context",
            "agent": "OUTCOME-IMPACT / team injury-context & fragility",
            "season": avail.get("meta", {}).get("season", "2025-26"),
            "source": {
                "availability": used,
                "swing_field": swing_key,
                "swing_basis": swing_cfg["source"],
                "team_strength": "team_strength.json (srs_rating, opponent-adjusted point scale)",
            },
            "method": (
                "Team-level rollup of the player 'who decides games' artifact. "
                "MOST INDISPENSABLE = roster members with the largest positive "
                "opponent-adjusted IN-vs-OUT margin swing (margin_swing_adj), gated "
                f"at n_out >= {MIN_OUT} AND rotation minutes min_in >= {MIN_MINUTES:.0f} "
                "(the minutes gate drops deep-bench bodies whose swing is a "
                "co-availability artifact, not indispensability); top-"
                f"{TOP_N} per team. FRAGILITY SCORE = the "
                "adjusted swing of the team's #1 player = points of margin the team "
                "loses when its most load-bearing player sits. Teams ranked "
                "most-fragile (collapses without its star) -> most-robust (depth "
                "absorbs absences). Opponent SRS baseline carried for context."
            ),
            "definitions": {
                "fragility_score": "adjusted margin swing (pts) of the team's single most indispensable player; higher = more fragile. PRIMARY ranking uses this on the best player regardless of confidence (confidence is carried so the reader can discount noisy leaders).",
                "fragility_score_high_conf": "same, but restricted to the team's best HIGH/MEDIUM-confidence indispensable player (drops still-schedule-confounded or small-sample leaders); null if the team has no credible single-absence signal. This is the conservative companion -- prefer it when a team's primary leader is low-confidence.",
                "margin_swing_adj": "opponent-SRS-neutralized (leak-safe as-of) IN-minus-OUT team margin for a player; positive => team is better with him",
                "srs_baseline": "team's opponent-adjusted simple rating (point scale)",
                "confidence": "carried from availability artifact: high (n_out>=8 & n_in>=25 & not schedule-confounded), medium, or low (small-n or |opp_adjustment|>=2 schedule-confounded)",
            },
            "gates": {"min_out_games": MIN_OUT, "min_rotation_minutes": MIN_MINUTES, "top_n_per_team": TOP_N, "decisive_swing_pts": DECISIVE_SWING},
            "coverage": {
                "n_teams": len(teams_out),
                "n_teams_with_qualifying_player": sum(
                    1 for t in teams_out.values() if t["n_qualifying_players"] > 0
                ),
            },
            "caveats": [
                "ASSOCIATION, NOT CAUSATION: margin swings are confounded by co-absences (stars sit together), rest/load-management spots, and home/road balance. The opponent-QUALITY confound is removed (opponent-SRS adjusted, leak-safe) but the rest remain.",
                "Small n_out is noisy -- gate on confidence / n_out before trusting a single team's rank.",
                "SCOUTING ONLY: availability-based betting was REJECTED in this repo; this layer is context/scouting, not a bet signal.",
                "Fragility anchors on the single worst-case absence (the #1 player), so a team with a flat, deep roster scores low even if 'losing any 2 of 5' would hurt; read depth_note alongside the score.",
                f"CO-AVAILABILITY: a player's margin swing measures team-margin with-vs-without him, which entangles his value with WHO ELSE is available. Deep-bench players who only suit up when the team is healthy show inflated swings (reverse causation); we gate them out with a min_in >= {MIN_MINUTES:.0f} rotation-minutes floor, but residual co-availability among rotation players remains.",
            ],
        },
        "teams": teams_out,
        "fragility_ranking": fragility_ranking,
        "fragility_ranking_high_conf": fragility_ranking_high_conf,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {OUT_PATH}")
    print(f"  availability source: {used}  (swing field: {swing_key})")
    print(f"  teams: {len(teams_out)}")
    print("  most-fragile 5:")
    for r in fragility_ranking[:5]:
        print(
            f"    {r['rank']:>2}. {r['team']}  frag={r['fragility_score']:+.2f}  "
            f"{r['top_player']} (n_out={r['top_player_n_out']}, {r['confidence']})"
        )
    print("  most-robust 5:")
    for r in fragility_ranking[-5:]:
        print(
            f"    {r['rank']:>2}. {r['team']}  frag={r['fragility_score']:+.2f}  "
            f"{r['top_player']} (n_out={r['top_player_n_out']}, {r['confidence']})"
        )
    print("  HIGH/MED-confidence ranking, most-fragile 5:")
    for r in fragility_ranking_high_conf[:5]:
        fs = r["fragility_score_high_conf"]
        print(
            f"    {r['rank']:>2}. {r['team']}  frag={fs:+.2f}  "
            f"{r['top_player']} (n_out={r['top_player_n_out']}, {r['confidence']})"
        )


if __name__ == "__main__":
    main()
