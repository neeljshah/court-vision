# -*- coding: utf-8 -*-
"""
build_signal_stability.py  --  OUTCOME-IMPACT: cross-season stability / reliability

CourtVision intel/outcome campaign (VALIDATION agent) deliverable.

QUESTION
--------
Are the "who decides games" outcome signals -- availability margin-swing,
on/off, on/off-adjusted impact, and RAPM -- STABLE and PREDICTIVE, or are they
mostly scouting noise that does not persist?  A signal that does not persist
across seasons / across an internal split-half is noise, not a forward prior.

THREE INDEPENDENT RELIABILITY ARMS (all leak-free, descriptive)
--------------------------------------------------------------
1. CROSS-SEASON predictiveness (Spearman):
     2024-25 RAPM (rapm_2024_25.players[pid].rapm_per100)        ]  do LAST year's
     2024-25 on/off (player_onoff.players[pid].onoff_swing)      ]  impact metrics
   vs
     2025-26 on/off-adjusted impact (player_plusminus.players[pid].adj_impact)
     2025-26 availability margin swing (player_availability.players[pid].margin_swing)
   Players present in both seasons only.  A real impact signal in 2024-25
   should rank-predict 2025-26 impact.

2. SPLIT-HALF reliability WITHIN 2025-26 (odd/even games):
   Reconstructed straight from the truth game log so the halves use the SAME
   method as the shipped artifacts:
     - AVAILABILITY SWING: for each player, split his team's games into
       odd/even chronological halves; recompute margin_swing = mean(margin IN) -
       mean(margin OUT) on each half; correlate the two halves across players.
       (This is the exact build_player_availability method, per half.)
     - ON/OFF (PLUS-MINUS) SWING: the 2025-26 adj_impact is built from per-game
       PLUS_MINUS in the same log.  Its descriptive base is the player's mean
       on-court +/- per game; we split each player's GAMES odd/even, take mean
       +/- on each half, correlate.  (Honest reconstruction of the plus-minus
       signal's internal consistency; the team-baseline adjustment is a monotone
       per-player shift that does not change a within-player split-half rank
       correlation, so this is a faithful reliability proxy for adj_impact.)
   A low split-half r => the metric is mostly sampling noise.
   We also report Spearman-Brown stepped-up reliability (full-season estimate).

3. CONVERGENT validity within 2025-26 (Spearman, shared players):
   Do the THREE independent 2025-26 methods agree on the top difference-makers?
     availability margin_swing  vs  on/off-adjusted adj_impact  vs
     clutch_impact (clutch_outcome.players[pid].clutch_impact)
   Agreement => the signal is real; disagreement => method artifact.

OUTPUT
------
  data/cache/intel_outcome/outcome_signal_stability.json
  docs/_audits/OUTCOME_SIGNAL_STABILITY_2026-06-01.md

All inputs read-only.  No vault edits, no betting code, no other artifacts.
SCOUTING ONLY -- a reliability audit, not a betting signal.

Run:  python scripts/intel/outcome/build_signal_stability.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def rp(*p):
    return os.path.join(ROOT, *p)


INTEL = rp("data", "cache", "intel_outcome")
GAMELOG = rp("data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")
OUT_JSON = os.path.join(INTEL, "outcome_signal_stability.json")
OUT_MD = rp("docs", "_audits", "OUTCOME_SIGNAL_STABILITY_2026-06-01.md")

MIN_IN_HALF = 5   # min IN games per half for an availability split-half point
MIN_OUT_HALF = 2  # min OUT games per half
MIN_GP_HALF = 5   # min games per half for a plus-minus split-half point


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def _load(name):
    with open(os.path.join(INTEL, name), "r", encoding="utf-8") as f:
        return json.load(f)


def spearman(x, y):
    """Spearman rho with paired finite filtering; returns (rho, p, n)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(m.sum())
    if n < 5 or np.allclose(x, x[0]) or np.allclose(y, y[0]):
        return (None, None, n)
    rho, p = stats.spearmanr(x, y)
    if not np.isfinite(rho):
        return (None, None, n)
    return (round(float(rho), 4), round(float(p), 6), n)


def pearson(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(m.sum())
    if n < 5 or np.allclose(x, x[0]) or np.allclose(y, y[0]):
        return (None, n)
    r, _ = stats.pearsonr(x, y)
    return (round(float(r), 4), n)


def spearman_brown(r):
    """Step a split-half r up to the full-length reliability estimate."""
    if r is None:
        return None
    if r <= -0.999:
        return None
    return round(2 * r / (1 + r), 4)


def verdict_from_r(r, stable=0.5, weak=0.3):
    """Map a reliability/predictiveness coefficient to a label."""
    if r is None:
        return "INSUFFICIENT"
    a = abs(r)
    if a >= stable:
        return "STABLE/RELIABLE"
    if a >= weak:
        return "WEAK/MIXED"
    return "NOISY"


# --------------------------------------------------------------------------- #
# split-half reconstruction from the truth game log
# --------------------------------------------------------------------------- #
def build_team_games(gl):
    """One row per team-game: GAME_ID, TEAM, GAME_DATE, margin (team-opp)."""
    tg = (
        gl.groupby(["GAME_ID", "TEAM_ABBREVIATION"], as_index=False)
        .agg(team_pts=("PTS", "sum"), game_date=("GAME_DATE", "first"))
    )
    rows = []
    for gid, sub in tg.groupby("GAME_ID"):
        if len(sub) != 2:
            continue
        a, b = sub.iloc[0], sub.iloc[1]
        for me, opp in ((a, b), (b, a)):
            rows.append(
                {
                    "GAME_ID": gid,
                    "TEAM": me["TEAM_ABBREVIATION"],
                    "GAME_DATE": str(me["game_date"]),
                    "margin": int(me["team_pts"]) - int(opp["team_pts"]),
                }
            )
    return pd.DataFrame(rows)


def availability_splithalf(gl, tgf):
    """For each player: split his (primary-team) games odd/even by date and
    recompute availability margin_swing on each half.  Returns arrays of paired
    half-A / half-B swings (one pair per qualifying player)."""
    gl = gl.copy()
    gl["GAME_ID"] = gl["GAME_ID"].astype(str)
    gl["GAME_DATE"] = gl["GAME_DATE"].astype(str)

    # primary team per player (most appearances)
    pt = gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"]).size().reset_index(name="n")
    primary = pt.sort_values("n").groupby("PLAYER_ID").tail(1).set_index("PLAYER_ID")

    # player-team roster window + played game ids
    ptg = (
        gl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"])
        .agg(gids=("GAME_ID", lambda s: set(s)),
             first_date=("GAME_DATE", "min"),
             last_date=("GAME_DATE", "max"))
    )

    team_idx = {t: sub.sort_values(["GAME_DATE", "GAME_ID"]).set_index("GAME_ID")
                for t, sub in tgf.groupby("TEAM")}

    a_swings, b_swings, names = [], [], []
    for pid in primary.index:
        team = primary.loc[pid, "TEAM_ABBREVIATION"]
        idx = team_idx.get(team)
        if idx is None:
            continue
        try:
            row = ptg.loc[(pid, team)]
        except KeyError:
            continue
        first_d, last_d, played = row["first_date"], row["last_date"], row["gids"]
        cand = idx[(idx["GAME_DATE"] >= first_d) & (idx["GAME_DATE"] <= last_d)]
        cand = cand.sort_values(["GAME_DATE", "GAME_ID"]).reset_index()
        if len(cand) < 2 * (MIN_IN_HALF + MIN_OUT_HALF):
            continue
        cand["is_in"] = cand["GAME_ID"].isin(played)
        # odd/even split on chronological order
        even = cand.iloc[0::2]
        odd = cand.iloc[1::2]

        def half_swing(h):
            hin = h[h["is_in"]]["margin"]
            hout = h[~h["is_in"]]["margin"]
            if len(hin) < MIN_IN_HALF or len(hout) < MIN_OUT_HALF:
                return None
            return float(hin.mean() - hout.mean())

        sa, sb = half_swing(even), half_swing(odd)
        if sa is None or sb is None:
            continue
        a_swings.append(sa)
        b_swings.append(sb)
        names.append(str(pid))
    return np.array(a_swings), np.array(b_swings), names


def plusminus_splithalf(gl):
    """For each player: split his GAMES odd/even by date, take mean on-court
    PLUS_MINUS per game on each half, correlate.  This is the descriptive base
    of the 2025-26 adj_impact signal."""
    gl = gl.copy()
    gl["GAME_DATE"] = gl["GAME_DATE"].astype(str)
    gl["GAME_ID"] = gl["GAME_ID"].astype(str)
    gl = gl.sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"])

    a_vals, b_vals, names = [], [], []
    for pid, sub in gl.groupby("PLAYER_ID"):
        sub = sub.reset_index(drop=True)
        if len(sub) < 2 * MIN_GP_HALF:
            continue
        even = sub.iloc[0::2]["PLUS_MINUS"].astype(float)
        odd = sub.iloc[1::2]["PLUS_MINUS"].astype(float)
        if len(even) < MIN_GP_HALF or len(odd) < MIN_GP_HALF:
            continue
        a_vals.append(float(even.mean()))
        b_vals.append(float(odd.mean()))
        names.append(str(pid))
    return np.array(a_vals), np.array(b_vals), names


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    av = _load("player_availability.json")
    pm = _load("player_plusminus.json")
    oo = _load("player_onoff.json")
    cl = _load("clutch_outcome.json")

    av_p = av["players"]                       # 2025-26 availability
    adj_p = pm["players"]                       # 2025-26 onoff-adjusted (adj_impact)
    rapm_p = pm["rapm_2024_25"]["players"]      # 2024-25 RAPM (rapm_per100)
    oo_p = oo["players"]                        # 2024-25 on/off (onoff_swing)
    cl_p = cl["players"]                        # 2025-26 clutch (clutch_impact)

    # ---------------------------------------------------------------- ARM 1
    # cross-season: pid -> value maps
    rapm_v = {pid: d.get("rapm_per100") for pid, d in rapm_p.items()}
    oo24_v = {pid: d.get("onoff_swing") for pid, d in oo_p.items()}
    adj25_v = {pid: d.get("adj_impact") for pid, d in adj_p.items()}
    av25_v = {pid: d.get("margin_swing") for pid, d in av_p.items()}

    def paired(src, dst):
        ids = sorted(set(src) & set(dst))
        xs = [src[i] for i in ids]
        ys = [dst[i] for i in ids]
        return xs, ys

    cross = {}
    for label, src, dst in [
        ("rapm24_25_vs_adj25_26", rapm_v, adj25_v),
        ("rapm24_25_vs_avail_marginswing25_26", rapm_v, av25_v),
        ("onoff24_25_vs_adj25_26", oo24_v, adj25_v),
        ("onoff24_25_vs_avail_marginswing25_26", oo24_v, av25_v),
        # within-year 2024-25 sanity: RAPM vs on/off (should be strongly +)
        ("rapm24_25_vs_onoff24_25_sanity", rapm_v, oo24_v),
    ]:
        xs, ys = paired(src, dst)
        rho, p, n = spearman(xs, ys)
        pr, _ = pearson(xs, ys)
        cross[label] = {
            "spearman_rho": rho,
            "spearman_p": p,
            "pearson_r": pr,
            "n_players_both": n,
            "verdict": verdict_from_r(rho),
        }

    # ---------------------------------------------------------------- ARM 2
    gl = pd.read_parquet(GAMELOG)
    gl["GAME_ID"] = gl["GAME_ID"].astype(str)
    gl["GAME_DATE"] = gl["GAME_DATE"].astype(str)
    tgf = build_team_games(gl)

    a_av, b_av, _ = availability_splithalf(gl, tgf)
    rho_av, p_av, n_av = spearman(a_av, b_av)
    pr_av, _ = pearson(a_av, b_av)
    sb_av = spearman_brown(rho_av)

    a_pm, b_pm, _ = plusminus_splithalf(gl)
    rho_pm, p_pm, n_pm = spearman(a_pm, b_pm)
    pr_pm, _ = pearson(a_pm, b_pm)
    sb_pm = spearman_brown(rho_pm)

    splithalf = {
        "availability_margin_swing": {
            "method": "odd/even chronological split of each player's team-games; "
                      "margin_swing = mean(margin IN) - mean(margin OUT) per half; "
                      "Spearman across players of half-A vs half-B swings.",
            "n_players": n_av,
            "split_half_spearman": rho_av,
            "split_half_pearson": pr_av,
            "spearman_p": p_av,
            "spearman_brown_full_season": sb_av,
            "verdict": verdict_from_r(sb_av if sb_av is not None else rho_av),
        },
        "onoff_plusminus_swing": {
            "method": "odd/even chronological split of each player's games; mean "
                      "on-court PLUS_MINUS per game per half (descriptive base of "
                      "2025-26 adj_impact); Spearman across players of the halves.",
            "n_players": n_pm,
            "split_half_spearman": rho_pm,
            "split_half_pearson": pr_pm,
            "spearman_p": p_pm,
            "spearman_brown_full_season": sb_pm,
            "verdict": verdict_from_r(sb_pm if sb_pm is not None else rho_pm),
        },
    }

    # ---------------------------------------------------------------- ARM 3
    # convergent validity: 3 independent 2025-26 methods, shared players
    cl_v = {pid: d.get("clutch_impact") for pid, d in cl_p.items()}
    conv_pairs = {
        "avail_marginswing_vs_adj_impact": (av25_v, adj25_v),
        "avail_marginswing_vs_clutch_impact": (av25_v, cl_v),
        "adj_impact_vs_clutch_impact": (adj25_v, cl_v),
    }
    convergent = {}
    for label, (s, d) in conv_pairs.items():
        xs, ys = paired(s, d)
        rho, p, n = spearman(xs, ys)
        convergent[label] = {
            "spearman_rho": rho,
            "spearman_p": p,
            "n_players_both": n,
            "verdict": verdict_from_r(rho, stable=0.4, weak=0.2),
        }

    # do they agree on the TOP difference-makers (top-20 by each)?
    def topset(vmap, k=20):
        items = [(pid, v) for pid, v in vmap.items() if v is not None and np.isfinite(v)]
        items.sort(key=lambda kv: -kv[1])
        return set(pid for pid, _ in items[:k])

    shared3 = set(av25_v) & set(adj25_v) & set(cl_v)
    av_s = {p: av25_v[p] for p in shared3 if av25_v[p] is not None}
    adj_s = {p: adj25_v[p] for p in shared3 if adj25_v[p] is not None}
    cl_s = {p: cl_v[p] for p in shared3 if cl_v[p] is not None and np.isfinite(cl_v[p])}
    top_av, top_adj, top_cl = topset(av_s), topset(adj_s), topset(cl_s)
    name_of = {pid: av_p.get(pid, {}).get("name") or adj_p.get(pid, {}).get("name")
               or cl_p.get(pid, {}).get("name") for pid in shared3}

    def named(idset):
        return sorted(name_of.get(p, p) for p in idset)

    top_overlap = {
        "n_shared_players": len(shared3),
        "k": 20,
        "avail_top20_and_adj_top20": named(top_av & top_adj),
        "avail_top20_and_clutch_top20": named(top_av & top_cl),
        "adj_top20_and_clutch_top20": named(top_adj & top_cl),
        "all_three_top20": named(top_av & top_adj & top_cl),
        "n_avail_and_adj": len(top_av & top_adj),
        "n_avail_and_clutch": len(top_av & top_cl),
        "n_adj_and_clutch": len(top_adj & top_cl),
        "n_all_three": len(top_av & top_adj & top_cl),
        "expected_overlap_if_random": round(20 * 20 / max(len(shared3), 1), 2),
    }

    # ---------------------------------------------------------------- VERDICTS
    def signal_verdict(name, coeff, kind, note):
        return {
            "signal": name,
            "coefficient": coeff,
            "coefficient_kind": kind,
            "verdict": verdict_from_r(coeff),
            "note": note,
        }

    verdicts = [
        signal_verdict(
            "availability_margin_swing (2025-26 who-decides-games)",
            sb_av,
            "split-half reliability (Spearman-Brown full-season)",
            "Internal reliability of the marquee 'who decides games' swing. "
            "Low n_out per half makes per-half swings noisy by construction; "
            "read this as the honest ceiling on how much of the swing is signal.",
        ),
        signal_verdict(
            "onoff_plusminus_swing (2025-26, base of adj_impact)",
            sb_pm,
            "split-half reliability (Spearman-Brown full-season)",
            "Internal reliability of the per-game on-court +/- the adjusted "
            "impact rests on.",
        ),
        signal_verdict(
            "RAPM 2024-25 -> 2025-26 adj_impact (cross-season predictiveness)",
            cross["rapm24_25_vs_adj25_26"]["spearman_rho"],
            "cross-season Spearman",
            "Does last year's TRUE RAPM rank-predict this year's adjusted impact?",
        ),
        signal_verdict(
            "on/off 2024-25 -> 2025-26 adj_impact (cross-season predictiveness)",
            cross["onoff24_25_vs_adj25_26"]["spearman_rho"],
            "cross-season Spearman",
            "Does last year's on/off rank-predict this year's adjusted impact?",
        ),
        signal_verdict(
            "RAPM/on-off 2024-25 -> 2025-26 availability margin swing",
            max(
                [c for c in (cross["rapm24_25_vs_avail_marginswing25_26"]["spearman_rho"],
                             cross["onoff24_25_vs_avail_marginswing25_26"]["spearman_rho"])
                 if c is not None] or [None],
                key=lambda v: abs(v) if v is not None else -1,
            ) if any(cross[k]["spearman_rho"] is not None for k in
                     ("rapm24_25_vs_avail_marginswing25_26", "onoff24_25_vs_avail_marginswing25_26"))
            else None,
            "cross-season Spearman (best of RAPM / on-off)",
            "Does prior-year impact predict this year's noisy availability swing? "
            "Expected to be WEAKER because availability swing is teammate-and-"
            "schedule-confounded and small-n per player.",
        ),
        signal_verdict(
            "convergent validity (avail vs adj_impact, 2025-26)",
            convergent["avail_marginswing_vs_adj_impact"]["spearman_rho"],
            "convergent Spearman",
            "Two independent 2025-26 methods agreeing => real signal.",
        ),
    ]

    payload = {
        "_meta": {
            "artifact": "outcome_signal_stability",
            "agent": "VALIDATION / cross-season stability + reliability",
            "campaign": "intel/outcome (outcome-impact)",
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "scouting_only": True,
            "question": "Are availability swing / on-off / adj-impact / RAPM STABLE "
                        "and PREDICTIVE, or scouting noise that does not persist?",
            "sources": [
                "data/cache/intel_outcome/player_availability.json (2025-26 swing)",
                "data/cache/intel_outcome/player_plusminus.json (2025-26 adj_impact + rapm_2024_25)",
                "data/cache/intel_outcome/player_onoff.json (2024-25 on/off)",
                "data/cache/intel_outcome/clutch_outcome.json (2025-26 clutch_impact, 3rd method)",
                "data/cache/cv_fix/leaguegamelog_regular_season.parquet (truth game log, split-half)",
            ],
            "method_notes": {
                "leak_free": "All correlations are descriptive reliability checks; "
                             "cross-season uses disjoint seasons; split-half uses "
                             "odd/even games within 2025-26. No future leakage.",
                "split_half_caps": {"MIN_IN_HALF": MIN_IN_HALF, "MIN_OUT_HALF": MIN_OUT_HALF,
                                    "MIN_GP_HALF": MIN_GP_HALF},
                "verdict_thresholds": "STABLE/RELIABLE |r|>=0.5 (convergent>=0.4); "
                                      "WEAK/MIXED |r|>=0.3 (>=0.2); else NOISY.",
            },
        },
        "arm1_cross_season": cross,
        "arm2_split_half_reliability": splithalf,
        "arm3_convergent_validity": {
            "pairwise_spearman": convergent,
            "top_difference_maker_overlap": top_overlap,
        },
        "per_signal_verdicts": verdicts,
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    write_markdown(payload)

    # console summary
    print("Wrote", OUT_JSON)
    print("Wrote", OUT_MD)
    print("\n=== CROSS-SEASON (Spearman) ===")
    for k, v in cross.items():
        print(f"  {k:42s} rho={v['spearman_rho']} (p={v['spearman_p']}) n={v['n_players_both']} -> {v['verdict']}")
    print("\n=== SPLIT-HALF RELIABILITY (2025-26) ===")
    for k, v in splithalf.items():
        print(f"  {k:28s} split-half rho={v['split_half_spearman']} "
              f"SB-full={v['spearman_brown_full_season']} n={v['n_players']} -> {v['verdict']}")
    print("\n=== CONVERGENT VALIDITY (2025-26) ===")
    for k, v in convergent.items():
        print(f"  {k:42s} rho={v['spearman_rho']} (p={v['spearman_p']}) n={v['n_players_both']} -> {v['verdict']}")
    print(f"  TOP-20 overlap: avail&adj={top_overlap['n_avail_and_adj']} "
          f"avail&clutch={top_overlap['n_avail_and_clutch']} "
          f"adj&clutch={top_overlap['n_adj_and_clutch']} "
          f"ALL3={top_overlap['n_all_three']} "
          f"(random~{top_overlap['expected_overlap_if_random']})")
    print("\n=== PER-SIGNAL VERDICTS ===")
    for v in verdicts:
        print(f"  [{v['verdict']:16s}] {v['signal']}  ({v['coefficient_kind']} = {v['coefficient']})")


def write_markdown(payload):
    m = payload["_meta"]
    cross = payload["arm1_cross_season"]
    sh = payload["arm2_split_half_reliability"]
    conv = payload["arm3_convergent_validity"]["pairwise_spearman"]
    top = payload["arm3_convergent_validity"]["top_difference_maker_overlap"]
    verds = payload["per_signal_verdicts"]

    def fmt(v):
        return "n/a" if v is None else f"{v}"

    L = []
    L.append("# Outcome Signal Stability / Reliability Audit (2026-06-01)")
    L.append("")
    L.append(f"_Agent: {m['agent']} - campaign {m['campaign']}. **SCOUTING ONLY.**_")
    L.append("")
    L.append(f"**Question.** {m['question']}")
    L.append("")
    L.append("A signal that does not persist across seasons or across an internal "
             "split-half is scouting noise, not a forward prior. We test the four "
             "outcome signals -- availability margin-swing ('who decides games'), "
             "on/off, on/off-adjusted impact, and RAPM -- on three independent "
             "reliability arms. All checks are leak-free (disjoint seasons; "
             "odd/even games within-season).")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Arm 1 - Cross-season predictiveness (Spearman)")
    L.append("")
    L.append("Do last year's (2024-25) impact metrics rank-predict this year's "
             "(2025-26)?")
    L.append("")
    L.append("| pairing | Spearman rho | p | Pearson r | n players in both | verdict |")
    L.append("|---|---|---|---|---|---|")
    order = [
        ("2024-25 RAPM -> 2025-26 adj_impact", "rapm24_25_vs_adj25_26"),
        ("2024-25 RAPM -> 2025-26 availability margin-swing", "rapm24_25_vs_avail_marginswing25_26"),
        ("2024-25 on/off -> 2025-26 adj_impact", "onoff24_25_vs_adj25_26"),
        ("2024-25 on/off -> 2025-26 availability margin-swing", "onoff24_25_vs_avail_marginswing25_26"),
        ("2024-25 RAPM vs 2024-25 on/off (within-year sanity)", "rapm24_25_vs_onoff24_25_sanity"),
    ]
    for label, key in order:
        v = cross[key]
        L.append(f"| {label} | {fmt(v['spearman_rho'])} | {fmt(v['spearman_p'])} | "
                 f"{fmt(v['pearson_r'])} | {v['n_players_both']} | {v['verdict']} |")
    L.append("")
    L.append("**Read.** A positive cross-season rho means the metric carries a real, "
             "persistent player skill component into the next season. The within-year "
             "RAPM-vs-on/off row is a sanity floor (two 2024-25 methods of the same "
             "thing should agree strongly).")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Arm 2 - Split-half reliability within 2025-26 (odd/even games)")
    L.append("")
    L.append("Each player's games are split odd/even chronologically; the swing is "
             "recomputed on each half and the halves are correlated across players. "
             "Spearman-Brown steps the split-half r up to a full-season reliability "
             "estimate. **Low r = the metric is mostly sampling noise.**")
    L.append("")
    L.append("| signal | n players | split-half Spearman | split-half Pearson | "
             "Spearman-Brown (full-season) | verdict |")
    L.append("|---|---|---|---|---|---|")
    for key, label in [
        ("availability_margin_swing", "availability margin-swing (who decides games)"),
        ("onoff_plusminus_swing", "on/off plus-minus swing (base of adj_impact)"),
    ]:
        v = sh[key]
        L.append(f"| {label} | {v['n_players']} | {fmt(v['split_half_spearman'])} | "
                 f"{fmt(v['split_half_pearson'])} | "
                 f"{fmt(v['spearman_brown_full_season'])} | {v['verdict']} |")
    L.append("")
    L.append(f"- availability method: {sh['availability_margin_swing']['method']}")
    L.append(f"- plus-minus method: {sh['onoff_plusminus_swing']['method']}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Arm 3 - Convergent validity within 2025-26 (3 independent methods)")
    L.append("")
    L.append("Do availability margin-swing, on/off-adjusted impact, and clutch impact "
             "agree on who the difference-makers are? Agreement across independent "
             "methods => real signal; disagreement => method artifact.")
    L.append("")
    L.append("| method pair | Spearman rho | p | n players in both | verdict |")
    L.append("|---|---|---|---|---|")
    for label, key in [
        ("availability swing vs adj_impact", "avail_marginswing_vs_adj_impact"),
        ("availability swing vs clutch_impact", "avail_marginswing_vs_clutch_impact"),
        ("adj_impact vs clutch_impact", "adj_impact_vs_clutch_impact"),
    ]:
        v = conv[key]
        L.append(f"| {label} | {fmt(v['spearman_rho'])} | {fmt(v['spearman_p'])} | "
                 f"{v['n_players_both']} | {v['verdict']} |")
    L.append("")
    L.append(f"**Top difference-maker agreement** (top-20 by each method, "
             f"n={top['n_shared_players']} shared players, random overlap "
             f"~{top['expected_overlap_if_random']}):")
    L.append("")
    L.append(f"- availability top-20 INTERSECT adj_impact top-20: "
             f"**{top['n_avail_and_adj']}** -> {', '.join(top['avail_top20_and_adj_top20']) or '(none)'}")
    L.append(f"- availability top-20 INTERSECT clutch top-20: "
             f"**{top['n_avail_and_clutch']}** -> {', '.join(top['avail_top20_and_clutch_top20']) or '(none)'}")
    L.append(f"- adj_impact top-20 INTERSECT clutch top-20: "
             f"**{top['n_adj_and_clutch']}** -> {', '.join(top['adj_top20_and_clutch_top20']) or '(none)'}")
    L.append(f"- ALL THREE top-20: **{top['n_all_three']}** -> "
             f"{', '.join(top['all_three_top20']) or '(none)'}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Per-signal verdicts")
    L.append("")
    L.append("| # | signal | coefficient | kind | verdict |")
    L.append("|---|---|---|---|---|")
    for i, v in enumerate(verds, 1):
        L.append(f"| {i} | {v['signal']} | {fmt(v['coefficient'])} | "
                 f"{v['coefficient_kind']} | **{v['verdict']}** |")
    L.append("")
    for i, v in enumerate(verds, 1):
        L.append(f"{i}. **{v['signal']}** - {v['verdict']} "
                 f"({v['coefficient_kind']} = {fmt(v['coefficient'])}). {v['note']}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Discipline notes")
    L.append("")
    L.append("- **SCOUTING ONLY.** This is a reliability audit of descriptive "
             "outcome signals, not a betting edge. None of these coefficients are "
             "graded against market lines.")
    L.append("- **Availability swing is small-n by construction**: most players "
             "have few OUT games, so per-half swings are noisy and the split-half "
             "reliability is a *floor*, not a refutation of the full-season number. "
             "Where the floor is low, the honest read is that much of the per-player "
             "swing is sampling noise and it should be sized down accordingly. It "
             "stays scouting either way.")
    L.append("- The plus-minus split-half uses raw on-court +/- (the descriptive "
             "base of adj_impact). The team-baseline adjustment is a monotone "
             "per-player shift and does not change a within-player split-half rank "
             "correlation, so this is a faithful reliability proxy.")
    L.append("- Verdict thresholds: " + m["method_notes"]["verdict_thresholds"])
    L.append("")
    L.append(f"_Generated {m['generated']} by build_signal_stability.py._")
    L.append("")

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
