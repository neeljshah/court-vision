"""
build_player_availability.py  --  MARQUEE intel: "WHO DECIDES GAMES"
====================================================================

For each NBA player with enough games sat out, quantify the team's OUTCOME
when he plays (IN) vs when he is absent (OUT): win%, average margin, average
game total, and pace -- and the IN-vs-OUT DELTAS ("swings").

This is SCOUTING / ASSOCIATION, *not proven causation*. When a star sits, the
schedule and other injuries change too, so we also compute the opponent
strength of the OUT games vs the IN games and flag players whose OUT sample
ran into a materially softer/harder schedule (a likely confound).

LEAK SAFETY
-----------
* The primary IN/OUT comparison is DESCRIPTIVE (team outcomes in games a player
  played vs sat). It uses the full 2025-26 sample. As a *summary statistic of
  the past* it is fine as scouting and, applied to FUTURE games, is a valid
  pregame prior (it never peeks at the game being predicted).
* We ALSO emit an explicitly leak-safe AS-OF predictive swing per player
  ("asof_margin_swing"): for each game in the season, in chronological order,
  we compare it only against the player's IN/OUT averages accumulated from
  STRICTLY PRIOR games (expanding, shift(1)). This is the number you could have
  used pregame on that date. The two are kept in separate fields.

SOURCES (all read-only; recon'd, not assumed):
  data/cache/cv_fix/leaguegamelog_regular_season.parquet
        -> WHO PLAYED each 2025-26 team-game + per-player PTS (=> team score,
           WL, margin, total). SEASON_ID 22025 only. Source of truth for
           scores/availability.
  data/nba/season_games_2025-26.json  ({"v":..,"rows":[...]})
        -> per (game_id, team) PACE (home_pace / away_pace). No actual scores
           live here, so margins/totals come from the game log.
  data/dnp_rows.parquet
        -> dnp_reason / expected_to_play context for the OUT games (injury vs
           coach vs personal); used to annotate, not to define the OUT set.
  data/player_adv_stats.parquet
        -> player display-name / minutes fallback. (Contains NO 2025-26 rows --
           max date 2025-04-13 -- so it is reference only, never used for pace.)

OUTPUT: data/cache/intel_outcome/player_availability.json
Player-id keys are the NBA stats player_id (string), matching the vault
filename convention  vault/Intelligence/Players/<player_id>_<slug>.md .

Run:  python scripts/intel/outcome/build_player_availability.py
"""
from __future__ import annotations

import json
import pathlib
import re
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[3]
GL_PATH = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
SG_PATH = ROOT / "data/nba/season_games_2025-26.json"
DNP_PATH = ROOT / "data/dnp_rows.parquet"
ADV_PATH = ROOT / "data/player_adv_stats.parquet"
VAULT_PLAYERS = ROOT / "vault/Intelligence/Players"
OUT_PATH = ROOT / "data/cache/intel_outcome/player_availability.json"

SEASON = "2025-26"
MIN_OUT = 4    # minimum sat-out games for inclusion
MIN_IN = 10    # minimum played games for inclusion
HIGH_CONF_OUT = 8       # >= this many OUT games => high confidence
HIGH_CONF_IN = 25       # >= this many IN games => high confidence
CONFOUND_OPP_WINPCT = 0.06   # |opp_winpct_out - opp_winpct_in| above this => flag


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = s.replace(".", "").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _vault_slug_map() -> dict[str, str]:
    """player_id -> slug actually used in vault filenames (best effort)."""
    out: dict[str, str] = {}
    if not VAULT_PLAYERS.exists():
        return out
    for p in VAULT_PLAYERS.glob("*.md"):
        m = re.match(r"^(\d+)_(.+)$", p.stem)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def load_team_games(gl: pd.DataFrame):
    """Return per team-game frame: GAME_ID, TEAM, GAME_DATE, team_pts, opp, opp_pts,
    margin, total, win. Built purely from the box-score game log (truth source)."""
    tg = (
        gl.groupby(["GAME_ID", "TEAM_ABBREVIATION"], as_index=False)
        .agg(team_pts=("PTS", "sum"), game_date=("GAME_DATE", "first"))
    )
    # attach opponent (the other team in the same GAME_ID)
    rows = []
    for gid, sub in tg.groupby("GAME_ID"):
        if len(sub) != 2:
            continue  # malformed game; skip
        a, b = sub.iloc[0], sub.iloc[1]
        for me, opp in ((a, b), (b, a)):
            rows.append(
                {
                    "GAME_ID": gid,
                    "TEAM": me["TEAM_ABBREVIATION"],
                    "GAME_DATE": str(me["game_date"]),
                    "team_pts": int(me["team_pts"]),
                    "OPP": opp["TEAM_ABBREVIATION"],
                    "opp_pts": int(opp["team_pts"]),
                }
            )
    tgf = pd.DataFrame(rows)
    tgf["margin"] = tgf["team_pts"] - tgf["opp_pts"]
    tgf["total"] = tgf["team_pts"] + tgf["opp_pts"]
    tgf["win"] = (tgf["margin"] > 0).astype(int)
    return tgf


def load_pace(sg_rows) -> dict[tuple[str, str], float]:
    pace: dict[tuple[str, str], float] = {}
    for r in sg_rows:
        ht, at = r.get("home_team"), r.get("away_team")
        gid = r.get("game_id")
        if not (ht and at and gid):
            continue
        hp, ap = r.get("home_pace"), r.get("away_pace")
        if hp not in (None, 0):
            pace[(gid, ht)] = float(hp)
        if ap not in (None, 0):
            pace[(gid, at)] = float(ap)
    return pace


def main() -> None:
    gl = pd.read_parquet(GL_PATH)
    gl["GAME_DATE"] = gl["GAME_DATE"].astype(str)
    gl["GAME_ID"] = gl["GAME_ID"].astype(str)

    sg_rows = json.loads(SG_PATH.read_text())["rows"]
    pace_lookup = load_pace(sg_rows)

    tgf = load_team_games(gl)  # one row per team-game (truth)
    tgf["pace"] = [pace_lookup.get((g, t)) for g, t in zip(tgf["GAME_ID"], tgf["TEAM"])]

    # team -> opponent season win% (strength of schedule helper)
    team_winpct = tgf.groupby("TEAM")["win"].mean().to_dict()

    # team -> list of its team-game rows (sorted by date) keyed by GAME_ID
    tgf = tgf.sort_values(["TEAM", "GAME_DATE", "GAME_ID"]).reset_index(drop=True)
    team_game_index = {t: sub.set_index("GAME_ID") for t, sub in tgf.groupby("TEAM")}

    # who played each (player) -> set of GAME_IDs, with the team they played for
    played = (
        gl.groupby("PLAYER_ID")
        .agg(
            game_ids=("GAME_ID", lambda s: set(s)),
            name=("PLAYER_NAME", "first"),
        )
    )
    # player -> primary team (most appearances) and whether traded
    pt = gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"]).size().reset_index(name="n")
    primary = pt.sort_values("n").groupby("PLAYER_ID").tail(1).set_index("PLAYER_ID")
    n_teams = pt.groupby("PLAYER_ID").size()

    # game-log appearances per player-team (to know which of a team's games a
    # traded player was actually rostered/active for): we use the player's games
    # WITH the primary team as IN, and the primary team's OTHER games (while the
    # player was plausibly rostered) as OUT. To avoid charging a traded player
    # for games before he joined / after he left, we bound OUT to the date span
    # between the player's first and last appearance for that team.
    player_team_games = (
        gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"])
        .agg(gids=("GAME_ID", lambda s: set(s)),
             first_date=("GAME_DATE", "min"),
             last_date=("GAME_DATE", "max"))
    )

    # per (player, game) minutes -> avg minutes in IN games (role / starter gate)
    pg_min = {
        (int(r.PLAYER_ID), str(r.GAME_ID)): float(r.MIN)
        for r in gl[["PLAYER_ID", "GAME_ID", "MIN"]].itertuples(index=False)
    }

    # dnp reason context per (player, game)
    dnp = pd.read_parquet(DNP_PATH)
    dnp = dnp[dnp["season"] == SEASON].copy()
    dnp["game_id"] = dnp["game_id"].astype(str)
    dnp_reason = {
        (int(r.player_id), r.game_id): r.dnp_reason
        for r in dnp.itertuples(index=False)
    }

    # minutes fallback name source (adv has no 2025-26 but gives clean names)
    vault_slugs = _vault_slug_map()

    players_out: dict[str, dict] = {}
    iron_men: list[dict] = []

    for pid in primary.index:
        team = primary.loc[pid, "TEAM_ABBREVIATION"]
        name = str(played.loc[pid, "name"])
        traded = bool(n_teams.get(pid, 1) > 1)

        team_idx = team_game_index.get(team)
        if team_idx is None:
            continue

        # date window the player was rostered with this team
        ptg = player_team_games.loc[(pid, team)]
        first_d, last_d = ptg["first_date"], ptg["last_date"]
        played_gids = ptg["gids"]

        # candidate team games within the roster window
        cand = team_idx[(team_idx["GAME_DATE"] >= first_d) & (team_idx["GAME_DATE"] <= last_d)]

        in_mask = cand.index.isin(played_gids)
        in_games = cand[in_mask]
        out_games = cand[~in_mask]

        n_in, n_out = len(in_games), len(out_games)

        if n_out == 0:
            # never missed a game while rostered -> iron-man
            if n_in >= MIN_IN:
                iron_men.append({"player_id": str(pid), "name": name, "team": team, "n_in": int(n_in)})
            continue

        if n_in < MIN_IN or n_out < MIN_OUT:
            continue  # insufficient sample for a stable swing

        def agg(df):
            return {
                "win": float(df["win"].mean()),
                "margin": float(df["margin"].mean()),
                "margin_var": float(df["margin"].var(ddof=1)) if len(df) > 1 else 0.0,
                "total": float(df["total"].mean()),
                "pace": float(df["pace"].dropna().mean()) if df["pace"].notna().any() else None,
                "opp_winpct": float(np.mean([team_winpct.get(o, np.nan) for o in df["OPP"]])),
            }

        a_in, a_out = agg(in_games), agg(out_games)

        winpct_swing = a_in["win"] - a_out["win"]
        margin_swing = a_in["margin"] - a_out["margin"]

        # Welch standard error of the margin swing (difference of two means) so we
        # can rank the leaderboard by SIGNAL not tiny-sample noise. margin_z is a
        # t-like statistic; |z|>=~2 means the swing clears its own noise.
        se_margin = float(np.sqrt(a_in["margin_var"] / n_in + a_out["margin_var"] / n_out))
        margin_z = float(margin_swing / se_margin) if se_margin > 0 else 0.0
        total_swing = a_in["total"] - a_out["total"]
        pace_swing = (
            (a_in["pace"] - a_out["pace"])
            if (a_in["pace"] is not None and a_out["pace"] is not None)
            else None
        )
        opp_in, opp_out = a_in["opp_winpct"], a_out["opp_winpct"]
        opp_diff = opp_in - opp_out  # >0 => player's IN games faced TOUGHER opp

        # confound flag: OUT schedule materially different from IN schedule
        confound = bool(abs(opp_diff) >= CONFOUND_OPP_WINPCT)
        if confound:
            if opp_out < opp_in:
                confound_note = (
                    f"OUT games faced SOFTER schedule (opp win% {opp_out:.3f} vs "
                    f"{opp_in:.3f} IN); swing may understate his value / be schedule-aided."
                )
            else:
                confound_note = (
                    f"OUT games faced TOUGHER schedule (opp win% {opp_out:.3f} vs "
                    f"{opp_in:.3f} IN); swing may overstate his value."
                )
        else:
            confound_note = ""

        # confidence
        if n_out >= HIGH_CONF_OUT and n_in >= HIGH_CONF_IN and not confound:
            confidence = "high"
        elif n_out >= MIN_OUT and n_in >= MIN_IN:
            confidence = "medium" if not confound else "low"
        else:
            confidence = "low"

        # avg minutes in IN games -> role tag (separates difference-makers from
        # deep-bench players whose swing is a rotation-context artifact)
        in_mins = [pg_min.get((int(pid), gid)) for gid in in_games.index]
        in_mins = [m for m in in_mins if m is not None]
        min_in = float(np.mean(in_mins)) if in_mins else 0.0
        if min_in >= 28:
            role = "star_starter"
        elif min_in >= 20:
            role = "starter"
        elif min_in >= 12:
            role = "rotation"
        else:
            role = "deep_bench"

        # ---- leak-safe AS-OF expanding swing (margin) ----
        # walk the player's team games chronologically; at each game compute the
        # margin swing using ONLY strictly-prior games, then average the per-game
        # as-of swings. This never uses the current/future game.
        asof = _asof_margin_swing(cand, played_gids)

        # OUT-game reason breakdown (context, not used to define OUT)
        reasons = defaultdict(int)
        for gid in out_games.index:
            r = dnp_reason.get((int(pid), gid))
            reasons[r if r else "not_listed"] += 1

        pid_s = str(pid)
        players_out[pid_s] = {
            "name": name,
            "team": team,
            "vault_slug": vault_slugs.get(pid_s, _slug(name)),
            "traded_midseason": traded,
            "min_in": round(min_in, 1),
            "role": role,
            "n_in": int(n_in),
            "n_out": int(n_out),
            "win_in": round(a_in["win"], 4),
            "win_out": round(a_out["win"], 4),
            "winpct_swing": round(winpct_swing, 4),
            "margin_in": round(a_in["margin"], 3),
            "margin_out": round(a_out["margin"], 3),
            "margin_swing": round(margin_swing, 3),
            "margin_swing_se": round(se_margin, 3),
            "margin_swing_z": round(margin_z, 3),
            "total_in": round(a_in["total"], 3),
            "total_out": round(a_out["total"], 3),
            "total_swing": round(total_swing, 3),
            "pace_in": round(a_in["pace"], 3) if a_in["pace"] is not None else None,
            "pace_out": round(a_out["pace"], 3) if a_out["pace"] is not None else None,
            "pace_swing": round(pace_swing, 3) if pace_swing is not None else None,
            "opp_strength_in": round(opp_in, 4),
            "opp_strength_out": round(opp_out, 4),
            "opp_strength_diff": round(opp_diff, 4),
            "confidence": confidence,
            "confound_flag": confound,
            "confound_note": confound_note,
            "out_reasons": dict(reasons),
            "asof_margin_swing": (round(asof, 3) if asof is not None else None),
            "asof_note": (
                "Leak-safe expanding swing from STRICTLY-PRIOR games only; "
                "usable as a pregame prior. None => not enough prior IN&OUT games "
                "had accumulated before any decision point."
            ),
        }

    # ---- leaderboards ----
    def _entry(pid, d, metric):
        return {
            "player_id": pid,
            "name": d["name"],
            "team": d["team"],
            "role": d["role"],
            "min_in": d["min_in"],
            metric: d[metric],
            "winpct_swing": d["winpct_swing"],
            "margin_swing": d["margin_swing"],
            "margin_swing_z": d["margin_swing_z"],
            "n_in": d["n_in"],
            "n_out": d["n_out"],
            "confidence": d["confidence"],
            "confound_flag": d["confound_flag"],
        }

    def board(metric, key, items=None):
        items = items if items is not None else list(players_out.items())
        ranked = sorted(items, key=key, reverse=True)
        return [_entry(pid, d, metric) for pid, d in ranked]

    # PRIMARY "who decides games": large AND credible margin swing for genuine
    # rotation difference-makers. We (a) require >=20 mpg in IN games so deep-bench
    # players -- whose swing is a rotation/garbage-time CONTEXT artifact, not impact
    # -- are excluded, (b) require n_out>=MIN_OUT and |z|>=1, and (c) rank by the
    # stabilized score |margin_swing_z| (swing relative to its own sampling noise).
    credible = [
        (pid, d) for pid, d in players_out.items()
        if d["n_out"] >= MIN_OUT and abs(d["margin_swing_z"]) >= 1.0 and d["min_in"] >= 20.0
    ]
    who_decides = board("margin_swing", lambda kv: abs(kv[1]["margin_swing_z"]), credible)[:40]
    # raw |margin swing| board (unfiltered -- includes deep-bench/tiny-sample extremes)
    who_decides_raw = board("margin_swing", lambda kv: abs(kv[1]["margin_swing"]))[:40]
    who_decides_winpct = board("winpct_swing", lambda kv: abs(kv[1]["winpct_swing"]))[:40]

    payload = {
        "_meta": {
            "artifact": "player_availability",
            "agent": "MARQUEE / who-decides-games",
            "season": SEASON,
            "generated_from": [
                "data/cache/cv_fix/leaguegamelog_regular_season.parquet (truth: who played + scores)",
                "data/nba/season_games_2025-26.json (pace)",
                "data/dnp_rows.parquet (OUT reason context)",
            ],
            "definitions": {
                "IN": "team-games (within the player's roster window with this team) in which the player appeared in the box score",
                "OUT": "team-games in the same window in which the player did NOT appear",
                "win_in/out": "team win fraction in IN/OUT games (0-1)",
                "margin_in/out": "avg team point margin (team_pts - opp_pts) in IN/OUT games",
                "total_in/out": "avg combined game total points in IN/OUT games",
                "pace_in/out": "avg possessions-per-40 (from season_games) in IN/OUT games",
                "*_swing": "IN minus OUT (positive margin_swing => team is BETTER with him)",
                "margin_swing_se": "Welch standard error of margin_swing (difference-of-means sampling noise)",
                "margin_swing_z": "margin_swing / margin_swing_se; t-like statistic, |z|>=2 ~ clears its own noise",
                "opp_strength_in/out": "avg season win% of the OPPONENTS faced in IN/OUT games (schedule strength)",
                "opp_strength_diff": "opp_strength_in - opp_strength_out (>0 => he played the tougher slate)",
                "confound_flag": f"True when |opp_strength_diff| >= {CONFOUND_OPP_WINPCT} (OUT schedule materially different)",
                "asof_margin_swing": "leak-safe expanding margin swing using only strictly-prior games (pregame-usable prior)",
                "min_in": "avg minutes played in IN games",
                "role": "star_starter(>=28) / starter(>=20) / rotation(>=12) / deep_bench(<12 mpg); deep_bench swings are context artifacts",
                "confidence": f"high = n_out>={HIGH_CONF_OUT} & n_in>={HIGH_CONF_IN} & no confound; else medium/low",
            },
            "inclusion": {"min_out_games": MIN_OUT, "min_in_games": MIN_IN},
            "leaderboards": {
                "who_decides_games": "PRIMARY. Genuine rotation difference-makers (min_in>=20 mpg) ranked by |margin_swing_z| (credible: n_out>=4 & |z|>=1). Excludes deep-bench players whose swing is a rotation/garbage-time CONTEXT artifact.",
                "who_decides_games_raw": "Ranked by raw |margin_swing| with NO role/sample gate -- includes deep-bench & tiny-sample extremes; read with role/min_in/n_out/z in hand.",
                "who_decides_games_by_winpct": "Ranked by |winpct_swing| (does the team win/lose with vs without him).",
            },
            "caveat": (
                "ASSOCIATION, NOT CAUSATION. When a player sits, opponent quality, "
                "other injuries, rest, and tank/load-management spots co-vary. We "
                "quantify and flag the schedule confound but cannot isolate the "
                "player's causal effect. This is scouting intelligence; it becomes a "
                "betting edge only if graded vs real totals/spreads on >=2 corpora."
            ),
            "n_players": len(players_out),
            "n_iron_men": len(iron_men),
        },
        "players": players_out,
        "who_decides_games": who_decides,            # stabilized: |margin_swing_z|, credible only
        "who_decides_games_raw": who_decides_raw,    # raw |margin_swing| (incl. tiny-sample extremes)
        "who_decides_games_by_winpct": who_decides_winpct,
        "iron_men": sorted(iron_men, key=lambda d: -d["n_in"]),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))

    # ---- console summary ----
    print(f"Wrote {OUT_PATH}")
    print(f"  players with measurable absence-impact: {len(players_out)}")
    print(f"  iron-men (>= {MIN_IN} IN, 0 OUT): {len(iron_men)}")
    print(f"  flagged as schedule-confounded: {sum(d['confound_flag'] for d in players_out.values())}")
    print("\nTOP-15 WHO DECIDES GAMES (rotation difference-makers >=20mpg, stabilized by |margin_swing_z|):")
    print(f"  {'name':22s} {'tm':3s} {'mpg':>4s} {'mgn_sw':>7s} {'z':>5s} {'win_sw':>7s} {'n_in':>4s} {'n_out':>5s} {'conf':>6s}  confound")
    for e in who_decides[:15]:
        print(
            f"  {e['name'][:22]:22s} {e['team']:3s} {e['min_in']:4.0f} {e['margin_swing']:+7.2f} "
            f"{e['margin_swing_z']:+5.1f} {e['winpct_swing']:+7.3f} {e['n_in']:4d} {e['n_out']:5d} "
            f"{e['confidence']:>6s}  {'YES' if e['confound_flag'] else ''}"
        )


def _asof_margin_swing(cand: pd.DataFrame, played_gids: set) -> float | None:
    """Expanding, strictly-prior-only margin swing (leak-safe).

    Walk team games in date order. Before scoring game i, we know the IN-mean and
    OUT-mean of games 0..i-1. The per-game as-of swing is (IN_mean_prior -
    OUT_mean_prior); we average these over games where both priors exist.
    """
    sub = cand.sort_values(["GAME_DATE", "GAME_ID"])
    in_margins: list[float] = []
    out_margins: list[float] = []
    swings: list[float] = []
    for gid, row in sub.iterrows():
        if in_margins and out_margins:
            swings.append(np.mean(in_margins) - np.mean(out_margins))
        if gid in played_gids:
            in_margins.append(row["margin"])
        else:
            out_margins.append(row["margin"])
    return float(np.mean(swings)) if swings else None


if __name__ == "__main__":
    main()
