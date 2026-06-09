"""Role-aware 2K ratings v2 — deep attribute vault -> category ratings -> impact-weighted OVERALL.

Every player is graded from 87 context-adjusted attributes (attribute_vault.parquet), aggregated
into 13 category ratings, modulated by ATTRIBUTE INTERACTIONS (skills work with/against each
other), weighted by his ROLE (archetype) with a uniform floor so one-dimensional specialists
can't grade like well-rounded stars, nudged by IMPACT (offensive load), and mapped through a
FIXED anchored curve (corpus-independent) calibrated to real anchors: Wemby #1, SGA/Jokic/Luka
top tier, Brunson >> Fox, role players sensible.

Output: data/cache/team_system/player_ratings.parquet
  python scripts/team_system/build_player_ratings.py
"""
from __future__ import annotations

import glob
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START, END = "<!-- SIGNALS:ratings START -->", "<!-- SIGNALS:ratings END -->"

# category -> [(vault_attr, within-category weight)]
CAT = {
    "SCORING":     [("score_ppm", 2.5), ("score_volume", 2.5), ("score_ts_usage_adj", 2.5), ("score_ts", 1), ("score_diversity", 1)],
    "SHOOTING":    [("shoot_above3", 2.5), ("shoot_catch_shoot3", 2), ("shoot_catch_shoot_efg", 1.5), ("shoot_corner3", 1),
                    ("shoot_mid", 1), ("shoot_ft", 1.5), ("shoot_offdribble3", 1.5), ("shoot_3_volume", 1.5),
                    ("shoot_pts_from_3", 0.5), ("score_spotup_ppp", 0.5)],
    "PLAYMAKING":  [("play_ast_pct", 2.5), ("play_pts_created", 2), ("play_potential_ast", 1.5), ("play_ast_per_pass", 1.5),
                    ("play_secondary_ast", 1), ("play_drive_kick", 1), ("play_creation_conv", 1.5), ("play_ball_security", 1.5),
                    ("play_passes_volume", 0.5), ("play_screen_ast", 0.5)],
    "CREATION":    [("crea_iso_ppp", 2.5), ("crea_usage", 2), ("crea_pnr_ppp", 2), ("crea_unassisted2", 1.5),
                    ("crea_drives_vol", 1.5), ("crea_post_ppp", 1), ("crea_late_clock_ts", 1), ("shoot_offdribble3", 1),
                    ("crea_drive_pts_share", 1)],
    "FINISHING":   [("fin_rim_pct", 3), ("fin_drive_pct", 2), ("fin_paint_pct", 1.5), ("fin_drive_pts", 1.5),
                    ("fin_contact_ft", 1.5), ("fin_transition", 1), ("fin_2nd_chance", 1), ("fin_rim_volume", 0.5), ("fin_paint_pts", 0.5)],
    "REBOUNDING":  [("reb_total_pct", 2), ("reb_dreb_pct", 1.5), ("reb_oreb_pct", 1.5), ("reb_box_outs", 1), ("motor_box_outs", 0.5)],
    "INTERIOR_D":  [("intd_block", 3), ("perd_blocks_per100", 1), ("intd_fg_suppress", 1.5), ("intd_contested", 1.5),
                    ("reb_contested", 1), ("intd_stops", 0.5)],
    "PERIMETER_D": [("perd_stops", 2.5), ("perd_steal", 1.5), ("perd_fg3_suppress", 1.5), ("perd_versatility", 1.5),
                    ("perd_foul_disc", 1), ("perd_matchup_load", 1)],
    "CLUTCH":      [("clutch_pts36", 2), ("clutch_fg", 1.5), ("clutch_plusminus", 1.5), ("clutch_ft", 1), ("clutch_3", 1),
                    ("sit_trail_efg", 1), ("sit_q4_scoring", 0.5), ("iq_q4_tilt", 0.5)],
    "IQ":          [("play_ball_security", 1.5), ("play_ato", 1.5), ("iq_foul_disc", 1), ("iq_foul_trouble", 1),
                    ("form_consistency_pts", 1.5), ("sit_b2b_resilience", 1), ("iq_late_clock_rate", 1),
                    ("sit_road_scoring", 0.5), ("form_trend_pts", 0.5), ("form_hot_pts", 0.5)],
    # shown on the card but flow into OVERALL only through the value categories above:
    "SIZE":        [("phys_height", 2), ("phys_size_pos", 1.5), ("phys_strength", 1.5), ("phys_weight", 1)],
    "ATHLETICISM": [("phys_agility", 2), ("phys_youth", 1), ("fin_transition", 1.5), ("fin_drive_pct", 1)],
    "DURABILITY":  [("durab_avail", 2), ("durab_peak", 1), ("durab_minload", 1), ("motor_minutes", 1)],
}
OVR_CATS = ["SCORING", "SHOOTING", "PLAYMAKING", "CREATION", "FINISHING", "REBOUNDING",
            "INTERIOR_D", "PERIMETER_D", "CLUTCH", "IQ"]
# archetype -> weights over OVR_CATS (same order). Defines WHICH skills make the player good.
ROLE_W = {
    "LEAD_GUARD":      [.24, .10, .20, .18, .04, .02, .01, .10, .07, .04],
    "SCORING_GUARD":   [.28, .13, .10, .17, .05, .02, .01, .12, .08, .04],
    "FLOOR_GENERAL":   [.15, .12, .26, .12, .03, .04, .01, .14, .07, .06],
    "OFF_GUARD":       [.15, .26, .08, .06, .04, .04, .03, .20, .08, .06],
    "BENCH_SCORER":    [.30, .15, .09, .16, .05, .02, .01, .10, .08, .04],
    "CONNECTOR_GUARD": [.12, .13, .18, .05, .05, .10, .03, .20, .06, .08],
    "WING_CREATOR":    [.26, .13, .08, .15, .08, .04, .02, .14, .07, .03],
    "THREE_D_WING":    [.14, .24, .06, .05, .07, .07, .05, .24, .04, .04],
    "CONNECTOR_WING":  [.12, .13, .12, .04, .07, .15, .06, .22, .04, .05],
    "ROLE_WING":       [.13, .20, .06, .04, .10, .12, .08, .20, .03, .04],
    "STRETCH_BIG":     [.20, .20, .06, .06, .12, .14, .12, .04, .03, .03],
    "PRIMARY_BIG":     [.24, .07, .08, .07, .14, .15, .15, .03, .04, .03],
    "TWO_WAY_BIG":     [.20, .07, .07, .08, .10, .15, .20, .04, .05, .04],
    "ANCHOR_BIG":      [.07, .03, .04, .03, .16, .24, .28, .07, .03, .05],
    "ROLE_BIG":        [.10, .08, .05, .04, .16, .20, .22, .08, .03, .04],
}
# FIXED raw(0-99) -> OVERALL curve (corpus-independent; calibrated to real anchors:
# Wemby 99 #1, SGA/Kawhi 98, Curry/Edwards 97, Brunson 92 >> Fox 86, role players sensible)
CURVE_X = [33, 39, 47, 55, 60, 66, 72, 76, 80, 83, 86, 88, 89]
CURVE_Y = [58, 62, 68, 73, 77, 81, 85, 88, 92, 95, 97, 98, 99]


def _cat(row, items):
    num = den = 0.0
    for a, w in items:
        v = row.get(a, np.nan)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            num += w * v; den += w
    return num / den if den > 0 else 50.0


def main():
    v = pd.read_parquet(os.path.join(TS, "attribute_vault.parquet"))
    ro = pd.read_parquet(os.path.join(TS, "player_roles.parquet")).set_index("pid")
    rows = []
    for r in v.itertuples(index=False):
        d = r._asdict()
        pid = int(d["player_id"])
        arch = ro.loc[pid].archetype if pid in ro.index else "ROLE_WING"
        c = {k: _cat(d, items) for k, items in CAT.items()}
        # --- ATTRIBUTE INTERACTIONS (skills work with / against each other) ---
        size, ts_adj, ppm = c["SIZE"], d.get("score_ts_usage_adj", 50), d.get("score_ppm", 50)
        # rim protection scales with size: a small fluke shot-blocker is capped, a 7'5" anchor isn't
        c["INTERIOR_D"] *= float(np.clip(0.72 + 0.0048 * (d.get("phys_height", 50) - 40), 0.72, 1.12))
        # scoring: efficiency x volume — efficient high-volume is elite; empty volume is dinged
        combo = (ppm / 99.0) * (ts_adj / 99.0)
        c["SCORING"] *= float(np.clip(0.90 + 0.18 * combo, 0.85, 1.12))
        # creation: usage is only worth it if efficient (empty-usage chucker penalized)
        c["CREATION"] *= float(np.clip(0.84 + 0.32 * (ts_adj / 99.0), 0.84, 1.16))
        # shooting gravity amplifies finishing/creation room (elite shooter -> blow-by)
        grav = max(0.0, (c["SHOOTING"] - 60) / 39.0)
        c["FINISHING"] *= (1.0 + 0.05 * grav); c["CREATION"] *= (1.0 + 0.04 * grav)
        c = {k: float(np.clip(val, 1, 99)) for k, val in c.items()}
        # --- role-weighted skill with uniform floor (penalize one-dimensionality) ---
        w = np.array(ROLE_W.get(arch, ROLE_W["ROLE_WING"]), float); w /= w.sum()
        w = 0.78 * w + 0.22 * (np.ones(len(OVR_CATS)) / len(OVR_CATS))
        raw = float(np.dot(w, [c[k] for k in OVR_CATS]))
        # offensive completeness: a top scorer who ALSO has a second elite offensive skill
        offv = max(c["SCORING"], c["CREATION"], c["PLAYMAKING"])
        second_off = sorted([c["SCORING"], c["CREATION"], c["PLAYMAKING"], c["SHOOTING"] + 12], reverse=True)[1]
        raw += 0.05 * max(0.0, min(offv, second_off) - 60)
        # two-way value: being simultaneously elite on offense AND defense is rare and
        # irreplaceable. Convex: a small broad credit, plus a steep bonus only when BOTH ends
        # are truly elite (>72) — this is what puts a unicorn (Wemby/Giannis) above a
        # pure-offense star (Curry) whose defense is merely good.
        defv = max(c["INTERIOR_D"], c["PERIMETER_D"])
        raw += 0.06 * max(0.0, min(offv, defv) - 50) + 0.20 * max(0.0, min(offv, defv) - 72)
        # unicorn premium: rare HEIGHT/length carrying real offensive skill is unguardable /
        # switch-proof in a way box stats miss (Wemby/Jokic/Giannis/Embiid). Keyed off height,
        # not the SIZE category (which blends in bulk — Wemby is elite-tall but skinny).
        raw += 3.2 * np.clip((d.get("phys_height", 50) - 78) / 21, 0, 1) * np.clip((offv - 68) / 31, 0, 1)
        # impact: heavy offensive load separates stars from equally-skilled role players
        impact = (d.get("crea_usage", 50) + d.get("score_volume", 50)) / 2.0 / 99.0
        raw *= (0.92 + 0.10 * impact)
        # role/minutes trust (context: stats aren't everything) — an efficient 19-mpg bench
        # scorer is not a 94. Trust = best of full-season 24-25 minutes OR current-season mpg,
        # so rookies in a big current role (Castle/Harper) aren't unfairly dampened.
        mpg = d.get("mpg")
        # current-season role is the relevant context (a bench player NOW is not a star, even
        # if he started last year); fall back to full-season 24-25 minutes only when mpg absent.
        if mpg == mpg and mpg is not None:
            trust = float(np.clip((mpg - 8) / 28.0, 0, 1))
        else:
            trust = d.get("durab_minload", 50) / 99.0
        raw *= float(np.clip(0.85 + 0.17 * trust, 0.85, 1.02))
        out = {"pid": pid, "player": d["player"], "team": d.get("team"), "mpg": d.get("mpg"),
               "archetype": arch, "raw": raw}
        out.update({k: int(round(c[k])) for k in CAT})
        out["OVERALL"] = int(round(np.interp(raw, CURVE_X, CURVE_Y)))
        rows.append(out)
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(TS, "player_ratings.parquet"), index=False)
    _fold(df); _report(df)


# deep card: category headline -> the standout underlying vault attributes
CARD_CATS = ["SCORING", "SHOOTING", "PLAYMAKING", "CREATION", "FINISHING", "REBOUNDING",
             "INTERIOR_D", "PERIMETER_D", "CLUTCH", "IQ", "SIZE", "ATHLETICISM", "DURABILITY"]
CARD_GROUPS = [
    ("Scoring", [("rate", "score_ppm"), ("eff(usg-adj)", "score_ts_usage_adj"), ("volume", "score_volume"),
                 ("3-level", "score_diversity")]),
    ("Shooting", [("ab-break3", "shoot_above3"), ("catch&shoot", "shoot_catch_shoot3"), ("corner3", "shoot_corner3"),
                  ("midrange", "shoot_mid"), ("FT", "shoot_ft"), ("off-dribble3", "shoot_offdribble3")]),
    ("Creation/Handle", [("iso PPP", "crea_iso_ppp"), ("PnR PPP", "crea_pnr_ppp"), ("usage", "crea_usage"),
                         ("unassisted", "crea_unassisted2"), ("drives", "crea_drives_vol"), ("late-clock", "crea_late_clock_ts")]),
    ("Playmaking", [("AST%", "play_ast_pct"), ("pts created", "play_pts_created"), ("potential ast", "play_potential_ast"),
                    ("drive&kick", "play_drive_kick"), ("AST:TO", "play_ato"), ("ball security", "play_ball_security")]),
    ("Finishing", [("rim FG%", "fin_rim_pct"), ("drive FG%", "fin_drive_pct"), ("paint", "fin_paint_pct"),
                   ("contact/FTr", "fin_contact_ft"), ("transition", "fin_transition")]),
    ("Defense", [("rim protect", "intd_block"), ("FG suppress", "intd_fg_suppress"), ("perim stops(opp-adj)", "perd_stops"),
                 ("steals", "perd_steal"), ("versatility", "perd_versatility"), ("foul disc", "perd_foul_disc")]),
    ("Rebounding", [("total%", "reb_total_pct"), ("dreb%", "reb_dreb_pct"), ("oreb%", "reb_oreb_pct"), ("box-outs", "reb_box_outs")]),
    ("Clutch/Context", [("clutch pts/36", "clutch_pts36"), ("clutch FG%", "clutch_fg"), ("clutch +/-", "clutch_plusminus"),
                        ("B2B resilience", "sit_b2b_resilience"), ("consistency", "form_consistency_pts")]),
    ("Physical", [("height", "phys_height"), ("strength", "phys_strength"), ("agility", "phys_agility"),
                  ("durability", "durab_avail")]),
]


def _fold(df):
    vault = pd.read_parquet(os.path.join(TS, "attribute_vault.parquet")).set_index("player_id")
    folded = 0
    for r in df[(df.team.isin(["NYK", "SAS"])) & (df.mpg >= 8)].itertuples(index=False):
        cands = glob.glob(os.path.join(PLAYERS, f"{int(r.pid)}_*.md"))
        if not cands or int(r.pid) not in vault.index:
            continue
        d = r._asdict(); va = vault.loc[int(r.pid)]
        head = " · ".join(f"{k.replace('_', ' ').title()} **{d[k]}**" for k in (["OVERALL"] + CARD_CATS) if pd.notna(d.get(k)))
        lines = []
        for label, attrs in CARD_GROUPS:
            cells = [f"{nm} {int(va[a])}" for nm, a in attrs if a in va.index and pd.notna(va[a])]
            if cells:
                lines.append(f"- **{label}:** " + " · ".join(cells))
        blk = (f"{START}\n\n## 2K-Style Ratings\n*Role-aware card — OVERALL **{d['OVERALL']}**, graded as a "
               f"**{d['archetype'].replace('_', ' ').title()}**. Built from 87 context-adjusted attributes -> "
               f"13 categories with skill interactions (size x rim-protection, efficiency x volume, handle x usage); "
               f"defense & rebounding are position-relative, defense opponent-adjusted.*\n\n"
               f"{head}\n\n**Underlying attributes (0-99 league percentile):**\n" + "\n".join(lines) + f"\n\n{END}\n")
        txt = open(cands[0], encoding="utf-8").read()
        if START in txt and END in txt:
            txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
        open(cands[0], "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)
        folded += 1
    print(f"DONE: ratings for {len(df)} players; folded DEEP cards into {folded} NYK/SAS notes.")


def _report(df):
    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print("\nLeague top-20 (mpg>=20 where known, else all):")
    pool = df[(df.mpg >= 20) | (df.mpg.isna())]
    for x in pool.sort_values("OVERALL", ascending=False).head(20).itertuples(index=False):
        print(f"  {asc(x.player):24s} {str(x.team):3s} {x.archetype:14s} OVR {x.OVERALL} (raw {x.raw:.1f})")
    print("\nNYK/SAS (role-aware):")
    for x in df[df.team.isin(["NYK", "SAS"]) & (df.mpg >= 10)].sort_values("OVERALL", ascending=False).itertuples(index=False):
        print(f"  {asc(x.player):22s} {x.team} {x.archetype:14s} OVR {x.OVERALL:2d} | SCOR {x.SCORING:2d} SHOOT {x.SHOOTING:2d} "
              f"PLAY {x.PLAYMAKING:2d} CREA {x.CREATION:2d} FIN {x.FINISHING:2d} REB {x.REBOUNDING:2d} intD {x.INTERIOR_D:2d} perD {x.PERIMETER_D:2d} CL {x.CLUTCH:2d}")
    for nm in ("Brunson", "Fox"):
        x = df[df.player.astype(str).str.contains(nm, na=False)].sort_values("mpg", ascending=False)
        if len(x):
            print(f"  CHECK {nm}: {x.iloc[0].OVERALL}")


if __name__ == "__main__":
    main()
