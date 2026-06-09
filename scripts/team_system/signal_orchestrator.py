"""SIGNAL ORCHESTRATOR -- drives the agentic signal loop: for each registered SIGNAL SPEC, build the
leak-free as-of panel, run it through signal_lab.validate_signal, record the verdict, log it. This is the
serial JUDGE of the agentic layer (panels can be built in parallel by agents; the registry write is serial).

Each spec = (name, grain, builder, baseline, feature, target, metric, note). Add a spec, the loop validates
it next run. Verdicts append to SIGNAL_LAB_LOG.md; the registry is the source of truth.

  python scripts/team_system/signal_orchestrator.py            # validate all untested specs
  python scripts/team_system/signal_orchestrator.py --all      # re-validate everything
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signal_lab import validate_signal, REG  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PIT = os.path.join(ROOT, "data", "cache", "pit")
LOG = os.path.join(TS, "SIGNAL_LAB_LOG.md")
WIRE_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WIRING_PROPOSALS.md")
WARROOM = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
ASOF = "2026-04-03"


def _asof_team(metric_cols=("pts", "poss", "opp_pts", "opp_poss")):
    """As-of expanding team aggregates keyed by (date, team); 'g' = prior game count (for as-of pace)."""
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet")).sort_values("date")
    out = {}; acc = {}
    for r in TG.itertuples(index=False):
        a = acc.setdefault(r.team, {c: 0.0 for c in metric_cols} | {"g": 0})
        out[(str(r.date)[:10], r.team)] = dict(a)
        for c in metric_cols:
            a[c] += getattr(r, c)
        a["g"] += 1
    L = {c: TG[c].sum() for c in metric_cols}; L["g"] = len(TG)
    return out, L


def _recency(arr):
    """Half-life-5 recency blend (0.6 recent + 0.4 mean) over a player's prior game rows."""
    ages = np.arange(len(arr))[::-1]; w = 0.5 ** (ages / 5); w /= w.sum()
    return lambda i: 0.6 * (arr[:, i] * w).sum() + 0.4 * arr[:, i].mean()


def _days(a, b):
    try:
        from datetime import date
        ya, ma, da = map(int, a.split("-")); yb, mb, db = map(int, b.split("-"))
        return abs((date(yb, mb, db) - date(ya, ma, da)).days)
    except Exception:
        return 999


def _gamelog_panel():
    """Player-game panel: as-of recency baseline + matchup context + vacated-load (same-day availability).

    Processed GAME BY GAME so the vacated load for game g uses ONLY prior-game recency + today's roster
    presence (both known at tip) -> leak-free. A teammate is 'OUT' if he is a recent regular
    (rec_min>=18, last game within 14 days) but absent from this game's box score.
    """
    G = pd.read_parquet(os.path.join(TS, "nyksas_player_gamelog.parquet")).sort_values(["date", "gid"])
    G["date"] = G.date.astype(str).str[:10]
    team, L = _asof_team()
    Ld = 100 * L["opp_pts"] / L["opp_poss"]; Lp = L["poss"] / max(L["g"], 1)
    try:
        attr = pd.read_parquet(os.path.join(TS, "player_attributes.parquet"))
        amap = attr.set_index("pid")["age"].to_dict() if "age" in attr.columns else {}
        _pb = {"G": "G", "F": "F", "WING": "F", "C": "C", "BIG": "C"}
        posmap = {pid: _pb.get(p, "F") for pid, p in attr.set_index("pid")["pos"].to_dict().items()} if "pos" in attr.columns else {}
    except Exception:
        amap = {}; posmap = {}
    # as-of opponent allowed-to-position (leak-free; keyed by the DEFENDING team + date)
    oppos = {}
    try:
        OP = pd.read_parquet(os.path.join(PIT, "opp_pos_allowed_asof_2025_26_reg.parquet"))
        OP["d"] = OP.game_date.astype(str).str[:10]
        for r in OP.itertuples(index=False):
            k = (r.d, r.team)                          # what THIS team allows to each position, as-of
            if k not in oppos:
                oppos[k] = dict(G=getattr(r, "opp_pts_allowed_to_G_asof", np.nan),
                                F=getattr(r, "opp_pts_allowed_to_F_asof", np.nan),
                                C=getattr(r, "opp_pts_allowed_to_C_asof", np.nan),
                                Gr=getattr(r, "opp_reb_allowed_to_G_asof", np.nan),
                                Fr=getattr(r, "opp_reb_allowed_to_F_asof", np.nan),
                                Cr=getattr(r, "opp_reb_allowed_to_C_asof", np.nan))
    except Exception:
        pass
    hist = {}                        # pid -> [[pts,reb,ast,mins], ...] prior games
    last_rec = {}                    # pid -> dict(rec_pts, rec_min, team, date) as-of his last game
    REG_MIN = 18.0                   # minutes that mark a rotation regular (so absence = a real vacancy)
    rows = []
    for gid, gdf in G.groupby("gid", sort=False):
        gdate = gdf.date.iloc[0]
        present = {t: set(sub.pid) for t, sub in gdf.groupby("team")}
        vac = {}                     # team -> vacated load from absent recent regulars (PRE-game, leak-free)
        for t in present:
            absent = [d for pid, d in last_rec.items()
                      if d["team"] == t and d["rec_min"] >= REG_MIN
                      and pid not in present[t] and _days(d["date"], gdate) <= 14]
            vac[t] = dict(vac_pts=float(sum(d["rec_pts"] for d in absent)),
                          vac_min=float(sum(d["rec_min"] for d in absent)), vac_n=len(absent))
        for r in gdf.itertuples(index=False):
            h = hist.get(r.pid, [])
            if len(h) >= 8:
                rec = _recency(np.array(h, float))
                od = team.get((gdate, r.opp), {}); md = team.get((gdate, r.team), {})
                opp_drtg = (100 * od.get("opp_pts", 0) / od["opp_poss"]) if od.get("opp_poss", 0) > 50 else Ld
                opp_pace = od["poss"] / od["g"] if od.get("g", 0) > 0 else Lp
                team_pace = md["poss"] / md["g"] if md.get("g", 0) > 0 else Lp
                age = amap.get(r.pid, 27.0); vt = vac.get(r.team, {})
                bk = posmap.get(r.pid, "F"); opd = oppos.get((gdate, r.opp), {})
                opp_pos_pts = opd.get(bk, np.nan); opp_pos_reb = opd.get(bk + "r", np.nan)
                rows.append(dict(gid=gid, pid=r.pid, a_pts=r.pts, a_reb=r.reb, a_ast=r.ast,
                                 rec_pts=rec(0), rec_reb=rec(1), rec_ast=rec(2), rec_min=rec(3), rec_pf=rec(4),
                                 opp_drtg=opp_drtg, rest=r.rest, is_b2b=r.is_b2b,
                                 pace_sum=opp_pace + team_pace, opp_pace=opp_pace,
                                 opp_pos_pts=opp_pos_pts, opp_pos_reb=opp_pos_reb,
                                 age=age, rest_x_age=r.rest * (age - 27),
                                 vac_pts=vt.get("vac_pts", 0.0), vac_min=vt.get("vac_min", 0.0),
                                 vac_n=vt.get("vac_n", 0)))
        for r in gdf.itertuples(index=False):       # update AS-OF snapshot AFTER the game
            hist.setdefault(r.pid, []).append([r.pts, r.reb, r.ast, r.mins, r.pf])
            h = hist[r.pid]
            if len(h) >= 5:
                rec = _recency(np.array(h, float))
                last_rec[r.pid] = dict(rec_pts=rec(0), rec_min=rec(3), team=r.team, date=gdate)
    P = pd.DataFrame(rows)
    return P[P.rec_min >= 12]                        # rotation players


def _possession_panel():
    """Possession-grain panel = the enriched PBP foundry output (state + origin + new context flags)."""
    D = pd.read_parquet(os.path.join(TS, "pbp_possessions.parquet"))
    D = D[D.pts <= 4].copy()
    D["late_clock"] = (D.poss_dur >= 16).astype(int)
    D["clutch"] = ((D.period >= 4) & (D.grem < 300) & (D.margin.abs() <= 5)).astype(int)
    D["trailing_big"] = (D.margin < -10).astype(int)
    return D


def _lineup_panel():
    """Stint-level lineup-game panel (the infrastructure last session flagged as missing). Re-parses each
    game's PBP into stints (h5/a5 + per-stint pts + possessions) via pbp_parse, attaches each on-court 5's
    COMPOSITION traits (spacing/rim-protect/creation from player_roles, off/def quality from player_ratings).
    One row per (gid, offense, stint) with poss>=3; target = on-court PPP; group = gid (leak-free 5-fold).
    *Caveat: composition traits are season-aggregate (a stable trait, not a same-game outcome) so this is a
    mild in-sample read; a strict version needs as-of traits. The split-half + orthogonality gates still bind.*"""
    import json
    from pbp_parse import parse_game, stint_poss
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    PBP_DIR, BOX_DIR = os.path.join(TS, "pbp"), os.path.join(TS, "box")
    roles = pd.read_parquet(os.path.join(TS, "player_roles.parquet")).set_index("pid")
    rat = pd.read_parquet(os.path.join(TS, "player_ratings.parquet")).set_index("pid")
    spc, rmp, sc = roles.spacing.to_dict(), roles.rim_protect.to_dict(), roles.self_create.to_dict()
    offq = rat.SCORING.to_dict()
    defq = ((rat.INTERIOR_D + rat.PERIMETER_D) / 2).to_dict()
    rows = []
    for gm in games:
        gid = gm["gid"]
        pf, bf = os.path.join(PBP_DIR, f"{gid}.json"), os.path.join(BOX_DIR, f"{gid}.json")
        if not (os.path.exists(pf) and os.path.exists(bf)):
            continue
        try:
            g = parse_game(json.load(open(pf)), json.load(open(bf)))
        except Exception:
            continue
        hid, aid = g["home_id"], g["away_id"]
        for s in g["stints"]:
            for off5, def5, opts, ev in ((s["h5"], s["a5"], s["h_pts"], s["ev"][hid]),
                                         (s["a5"], s["h5"], s["a_pts"], s["ev"][aid])):
                poss = stint_poss(ev)
                if poss < 3:
                    continue
                o, d = list(off5), list(def5)
                rows.append(dict(gid=gid, ppp=opts / poss, poss=poss,
                                 off_quality=float(np.mean([offq.get(i, 50) for i in o])),
                                 def_quality=float(np.mean([defq.get(i, 50) for i in d])),
                                 spacing=float(sum(spc.get(i, 0.45) for i in o)),         # total floor spacing (off)
                                 creation_load=float(sum(sc.get(i, 0.45) for i in o)),    # total shot-creation (off)
                                 rim_protect=float(max([rmp.get(i, 0) for i in d] + [0]))))  # best protector (def)
    return pd.DataFrame(rows)


def _teamgame_panel():
    """Team-game panel: as-of net-diff composition baseline + matchup/rest features. Leak-free (each gid's
    two rows are snapshotted PRE-game from prior games only). target = margin; group = gid."""
    T = pd.read_parquet(os.path.join(TS, "league_team_game.parquet")).sort_values(["date", "gid"])
    T["date"] = T.date.astype(str).str[:10]
    Lo = 100 * T.pts.sum() / T.poss.sum()
    acc = {}                                  # team -> running sums + last_date
    rows = []
    def snap(t):
        a = acc.get(t)
        if not a or a["g"] < 5:
            return None
        return dict(ortg=100 * a["pts"] / a["poss"], drtg=100 * a["opp_pts"] / a["opp_poss"],
                    oreb_rate=a["oreb"] / max(a["oreb"] + a["opp_dreb"], 1),
                    dreb_rate=a["dreb"] / max(a["dreb"] + a["opp_oreb"], 1), last=a["last"])
    for gid, gdf in T.groupby("gid", sort=False):
        gdate = gdf.date.iloc[0]
        snaps = {r.team: snap(r.team) for r in gdf.itertuples(index=False)}
        for r in gdf.itertuples(index=False):
            s, o = snaps.get(r.team), snaps.get(r.opp)
            if s and o:
                rest = _days(s["last"], gdate) if s["last"] else 3
                orest = _days(o["last"], gdate) if o["last"] else 3
                rows.append(dict(gid=gid, team=r.team, margin=r.pts - r.opp_pts,
                                 net_self=s["ortg"] - s["drtg"], net_opp=o["ortg"] - o["drtg"],
                                 oreb_matchup=s["oreb_rate"] * (1 - o["dreb_rate"]),   # own OREB% x opp's allowed OREB
                                 rest_adv=min(rest, 5) - min(orest, 5)))
        for r in gdf.itertuples(index=False):     # update AFTER (leak-free)
            a = acc.setdefault(r.team, dict(pts=0.0, poss=0.0, opp_pts=0.0, opp_poss=0.0,
                                            oreb=0.0, dreb=0.0, opp_oreb=0.0, opp_dreb=0.0, g=0, last=None))
            for c in ("pts", "poss", "opp_pts", "opp_poss", "oreb", "dreb", "opp_oreb", "opp_dreb"):
                a[c] += getattr(r, c)
            a["g"] += 1; a["last"] = gdate
    return pd.DataFrame(rows)


# possession baseline = the state + matchup + ORIGIN features the engine already reasons over, so a
# candidate must add lift ON TOP of what is known (not re-discover transition).
POSS_BASE = ["period", "grem", "margin", "abs_margin", "off_is_home", "off_ortg", "def_drtg",
             "off_pace", "def_pace", "transition", "second_chance"]

SPECS = [
    dict(name="opp_def_matchup", grain="player-game", panel="gamelog",
         baseline=["rec_pts"], feature=["opp_drtg"], target="a_pts", metric="rmse",
         note="opponent as-of defensive rating -> pts (does opp-D beat recency-only?)"),
    dict(name="rest_days_pts", grain="player-game", panel="gamelog",
         baseline=["rec_pts", "rec_min"], feature=["rest", "is_b2b"], target="a_pts", metric="rmse",
         note="rest / back-to-back -> pts"),
    dict(name="rest_x_age", grain="player-game", panel="gamelog",
         baseline=["rec_pts", "rec_min"], feature=["rest_x_age"], target="a_pts", metric="rmse",
         note="rest x age interaction (older players rest-sensitive)"),
    # --- this session's three (prompt: shot_clock_leverage + after_timeout, then same_day_availability) ---
    dict(name="shot_clock_leverage", grain="possession", panel="possession",
         baseline=POSS_BASE, feature=["poss_dur"], target="pts", metric="rmse",
         note="possession duration (shot-clock used) -> PPP; the xFG-by-clock shot-quality curve"),
    dict(name="after_timeout", grain="possession", panel="possession",
         baseline=POSS_BASE, feature=["ato"], target="pts", metric="rmse",
         note="first possession after a timeout (set play) -> PPP"),
    dict(name="clutch_possession", grain="possession", panel="possession",
         baseline=POSS_BASE, feature=["clutch"], target="pts", metric="rmse",
         note="clutch state (Q4, <5min, margin<=5) -> PPP beyond linear margin/clock"),
    dict(name="lead_state", grain="possession", panel="possession",
         baseline=POSS_BASE, feature=["trailing_big"], target="pts", metric="rmse",
         note="trailing big (margin<-10) -> PPP (non-linear lead effect beyond linear margin)"),
    dict(name="same_day_availability", grain="player-game", panel="gamelog",
         baseline=["rec_pts", "rec_min"], feature=["vac_pts"], target="a_pts", metric="rmse",
         note="teammates OUT (box-absence as-of) -> vacated scoring load re-routes to present players"),
    # --- next batch (un-mined detail; registry guarantees the done ones are never re-run) ---
    dict(name="post_made_vs_live", grain="possession", panel="possession",
         baseline=POSS_BASE, feature=["after_made"], target="pts", metric="rmse",
         note="possession after opp MADE FG (set defense) vs live ball -> PPP"),
    dict(name="foul_trouble_carryover", grain="player-game", panel="gamelog",
         baseline=["rec_pts", "rec_min"], feature=["rec_pf"], target="a_pts", metric="rmse",
         note="recent foul-proneness (as-of) -> pts (does foul risk beat recency?)"),
    dict(name="pace_matchup", grain="player-game", panel="gamelog",
         baseline=["rec_pts", "rec_min"], feature=["pace_sum"], target="a_pts", metric="rmse",
         note="combined as-of pace (team+opp poss/g) -> pts (more possessions -> more volume?)"),
    dict(name="opp_position_defense", grain="player-game", panel="gamelog",
         baseline=["rec_pts", "rec_min"], feature=["opp_pos_pts"], target="a_pts", metric="rmse",
         note="opp as-of allowed-pts to the player's position -> pts (positional matchup; absorbed by recency?)"),
    dict(name="opp_position_defense_reb", grain="player-game", panel="gamelog",
         baseline=["rec_reb", "rec_min"], feature=["opp_pos_reb"], target="a_reb", metric="rmse",
         note="opp as-of allowed-reb to the player's position -> reb (rebounding matchup, less-priced?)"),
    # --- team-game grain (4th grain; baseline = as-of net-diff composition) ---
    dict(name="oreb_matchup", grain="team-game", panel="teamgame",
         baseline=["net_self", "net_opp"], feature=["oreb_matchup"], target="margin", metric="rmse",
         note="own OREB% x opp allowed-OREB -> margin (orthogonal to net-diff, or double-counts?)"),
    dict(name="rest_advantage", grain="team-game", panel="teamgame",
         baseline=["net_self", "net_opp"], feature=["rest_adv"], target="margin", metric="rmse",
         note="rest-days differential (as-of) -> margin"),
    # --- lineup grain (stint-level; baseline = the lineup's own quality, so a signal must add over talent) ---
    dict(name="lineup_spacing", grain="lineup", panel="lineup",
         baseline=["off_quality"], feature=["spacing"], target="ppp", metric="rmse",
         note="total floor spacing of the offensive 5 -> on-court PPP (beyond the lineup's scoring talent?)"),
    dict(name="lineup_rim_protection", grain="lineup", panel="lineup",
         baseline=["def_quality"], feature=["rim_protect"], target="ppp", metric="rmse",
         note="best rim-protector on the defensive 5 -> opp on-court PPP (expect NEGATIVE: suppresses scoring)"),
    dict(name="two_creator_lineups", grain="lineup", panel="lineup",
         baseline=["off_quality"], feature=["creation_load"], target="ppp", metric="rmse",
         note="total shot-creation of the offensive 5 -> on-court PPP (self-creation beyond raw talent?)"),
]

# centered-at-neutral wiring recipe per VALIDATED signal: which sim NODE it modulates + the flag that
# gates it. Centered so an average/zero context leaves the prediction byte-identical (can't regress).
WIRE = {
    "shot_clock_leverage": ("xFG make probability (shot-quality by shot-clock state)",
                            "xfg *= 1 + SLOPE*(poss_clock_state - neutral)", "CV_SIG_SHOTCLOCK"),
    "after_timeout":       ("PPP on the after-timeout possession (set-play efficiency)",
                            "ppp *= 1 + SLOPE*ato (centered at ato=0)", "CV_SIG_ATO"),
    "same_day_availability": ("usage/minutes re-route when a recent regular is OUT (the freshness lever)",
                              "use_per_min *= 1 + SLOPE*(vac_pts/team_pts) for present players", "CV_SIG_AVAIL"),
    "pbp_origin_transition": ("next-possession PPP after a live TO/OREB (in-game reactive only)",
                              "ppp *= origin_mult (centered at half-court=1.0)", "CV_INGAME_ORIGIN"),
    "rest_x_age":          ("per-player pts target on high-rest games for older players",
                            "pts *= 1 + SLOPE*rest*(age-27) (centered at neutral)", "CV_SIG_RESTAGE"),
    "post_made_vs_live":   ("PPP on the possession after an opp make (set-defense penalty)",
                            "ppp *= 1 + SLOPE*after_made (centered at after_made=0)", "CV_SIG_SETDEF"),
    "foul_trouble_carryover": ("minutes/usage haircut for recently foul-prone players",
                              "min *= 1 - SLOPE*(rec_pf - league_pf) (centered)", "CV_SIG_FOULTROUBLE"),
    "pace_matchup":        ("possession count from the combined as-of pace",
                            "n_poss = (team_pace + opp_pace)/2 (already in engine; centered)", "CV_SIG_PACE"),
    "oreb_matchup":        ("second-chance points from own OREB% vs opp allowed-OREB",
                            "oreb_p *= 1 + SLOPE*(oreb_matchup - neutral)", "CV_SIG_OREB"),
    "rest_advantage":      ("team margin tilt from the rest-days differential",
                            "margin += SLOPE*rest_adv (centered at 0)", "CV_SIG_RESTADV"),
    "lineup_spacing":      ("on-court PPP from the lineup's total spacing (5-man synergy)",
                            "lineup_ppp *= 1 + SLOPE*(spacing - neutral)", "CV_SIG_SPACING"),
    "lineup_rim_protection": ("opp on-court PPP suppressed by the best rim-protector on the floor",
                             "opp_ppp *= 1 - SLOPE*(rim_protect - neutral)", "CV_SIG_RIMPROT"),
    "two_creator_lineups": ("on-court PPP from multiple self-creators (shot-creation synergy)",
                            "lineup_ppp *= 1 + SLOPE*(creation_load - neutral)", "CV_SIG_CREATORS"),
}


# per-signal caveats: the lab's orthogonality is RELATIVE TO ITS BASELINE; a coarse baseline can let a
# signal the production ENGINE already models pass the gate. Flag those so the A/B re-checks vs the engine.
CAVEATS = {
    "oreb_matchup": " CAVEAT: orthogonal only to the coarse net-diff baseline; the engine ALREADY models OREB "
                    "(`oreb_per_miss`) so this LIKELY DOUBLE-COUNTS (cf the M3 team-total finding) -- the A/B MUST "
                    "screen orthogonality vs the engine's OREB output before any flip.",
    "shot_clock_leverage": " CROSS-SEASON CONFIRMED (build_legacy_possessions.py, 560k possessions): replicates "
                           "league-wide 2022-23 (-2.12%) + 2023-24 (-2.08%) + 2025-26 (-2.86%), split-half stable "
                           "-0.17 each -> NOT a single-window peak; the strongest signal in the registry. NOTE: poss_dur "
                           "is co-determined with the shot, so wire it as the generative xFG-vs-clock-state CURVE, not a feature.",
    "opp_position_defense_reb": " CAVEAT: SIGN IS BACKWARDS (corr −0.19/−0.26: more-allowed -> FEWER reb) and n=190 "
                               "-- passes the gates but the effect is opposite the causal story = a likely pace/selection "
                               "confound or small-n artifact. DO NOT WIRE; resolve the sign (control for pace) first. "
                               "Illustrates that the lab's gates are necessary, NOT sufficient -- sign+n+engine-redundancy "
                               "need a judgment layer.",
}


def _propose_wiring(row):
    """For a VALIDATED signal, append a centered-at-neutral, GATED wiring proposal (never auto-applied)."""
    node, patch, flag = WIRE.get(row["name"], ("TBD (map the node)", "centered multiplier", f"CV_SIG_{row['name'].upper()}"))
    line = (f"- **{row['name']}** ({row['grain']}, {row['metric']} {row['oos_rel']:+.3%}, "
            f"split-half {row['split_half']}, ortho {row['ortho']}): modulate **{node}** via `{patch}` "
            f"behind `{flag}` (default OFF). Requires a board-green A/B before any flip; NOT auto-applied."
            f"{CAVEATS.get(row['name'], '')}")
    head = "# Signal Lab -- gated wiring proposals (validated signals only; nothing auto-applied)\n\n" \
        if not os.path.exists(WIRE_MD) else ""
    existing = open(WIRE_MD, encoding="utf-8").read() if os.path.exists(WIRE_MD) else ""
    if f"**{row['name']}**" in existing:                    # one proposal per signal (refresh)
        existing = "\n".join(l for l in existing.splitlines() if f"**{row['name']}**" not in l)
        open(WIRE_MD, "w", encoding="utf-8").write(existing.rstrip() + "\n" + line + "\n")
    else:
        open(WIRE_MD, "a", encoding="utf-8").write(head + line + "\n")


def _fold_warroom():
    """Idempotently fold the registry summary into the War Room as a `## Signal Lab` block."""
    if not (os.path.exists(REG) and os.path.exists(WARROOM)):
        return
    import re
    df = pd.read_parquet(REG)
    nval = int((df.verdict == "VALIDATED").sum()); nrej = int((df.verdict == "REJECTED").sum())
    lines = ["<!-- SIGNALS:signal-lab START -->", "",
             "## Signal Lab — surgically validated signals (agentic layer)", "",
             f"Each candidate is tested once against 4 leak-free gates (OOS lift on rmse/logloss, split-half "
             f"stability, orthogonality, materiality) and the verdict is recorded so it's never re-litigated. "
             f"**{nval} validated / {nrej} rejected** of {len(df)} tested.", "",
             "| Signal | Grain | OOS lift | Split-half | Ortho | Verdict |",
             "|---|---|---|---|---|---|"]
    for r in df.sort_values(["verdict", "oos_rel"]).itertuples(index=False):
        lines.append(f"| `{r.name}` | {r.grain} | {r.oos_rel:+.2%} | {r.split_half} | {r.ortho} | {r.verdict} |")
    lines += ["", "*Validated signals are flagged for GATED A/B wiring (`scripts/team_system/WIRING_PROPOSALS.md`); "
              "nothing is auto-applied — accuracy != edge.*", "", "<!-- SIGNALS:signal-lab END -->"]
    block = "\n".join(lines)
    txt = open(WARROOM, encoding="utf-8").read()
    pat = re.compile(r"<!-- SIGNALS:signal-lab START -->.*?<!-- SIGNALS:signal-lab END -->", re.S)
    txt = pat.sub(block, txt) if pat.search(txt) else txt.rstrip() + "\n\n" + block + "\n"
    open(WARROOM, "w", encoding="utf-8").write(txt)
    print(f"folded ## Signal Lab into War Room ({nval} validated / {nrej} rejected)")


# the SELF-ADVANCING queue: hypotheses still to BUILD (each needs a panel feature + a SPEC). The agentic
# loop pops the top one, builds it, validates, records -> the registry guarantees nothing here is ever redone.
NEXT_HYPOTHESES = [
    # BUILDABLE now (have the as-of data):
    "matchup_shot_diet_vs_rimD (player-game): z_rim x a clean as-of opp RIM-D metric (need rim-level allowed, "
    "not the coarse opp_blk proxy) -> pts",
    # BLOCKED on infrastructure (record honestly; build the substrate first, don't fake the discipline):
    "[UNBLOCKED - legacy foundry built] cross-season validation of any possession signal via "
    "build_legacy_possessions.py (560k poss, 2022-23 + 2023-24); shot_clock_leverage CONFIRMED replicating "
    "(-2.1%/-2.1%/-2.9% across 3 seasons). NEXT: cross-season-check origin/transition (after_to tagged)",
    "[DONE - stint panel built, all 3 REJECTED] lineup_spacing/rim_protection/two_creator: composition "
    "synergy adds NO material lift over the lineup's individual talent at stint grain (5411 stints) -> "
    "confirms 'lineup net emerges from the players' (engine design); _lineup_panel() now exists for reuse",
    "[engine-redundant] shot_area_xfg (possession): terminal-shot location = the sim's existing zone xFG "
    "curve + leaky -> skip as a feature; it's already a generative modulator",
    "edge: per-stat value-bet thresholds + freshness/CLV once open+close odds are captured (signal_edge.py)",
]


def status():
    done = pd.read_parquet(REG) if os.path.exists(REG) else pd.DataFrame()
    nval = int((done.verdict == "VALIDATED").sum()) if len(done) else 0
    untested = [s["name"] for s in SPECS if not len(done) or s["name"] not in set(done.name)]
    print(f"=== SIGNAL LAB STATUS ===  registry: {len(done)} tested / {nval} validated")
    print(f"specs wired: {len(SPECS)}  |  untested specs queued: {len(untested)} {untested or ''}")
    print(f"hypotheses to BUILD next ({len(NEXT_HYPOTHESES)}):")
    for h in NEXT_HYPOTHESES:
        print(f"  - {h}")
    print("nothing is ever re-validated (registry dedups); the loop only adds NET-NEW knowledge.")


def main():
    if "--status" in sys.argv:
        status(); return
    reval = "--all" in sys.argv
    done = set(pd.read_parquet(REG).name) if os.path.exists(REG) else set()
    panels = {}
    log_lines = []
    builders = {"gamelog": _gamelog_panel, "possession": _possession_panel,
                "teamgame": _teamgame_panel, "lineup": _lineup_panel}
    for spec in SPECS:
        if spec["name"] in done and not reval:
            continue
        if spec["panel"] not in panels:
            panels[spec["panel"]] = builders[spec["panel"]]()
        P = panels[spec["panel"]]
        try:
            v = validate_signal(P, spec["name"], spec["baseline"], spec["feature"], spec["target"],
                                group="gid", metric=spec["metric"], asof=ASOF, grain=spec["grain"], note=spec["note"])
            log_lines.append(f"- **{v['verdict']}** `{v['name']}` ({v['grain']}): {v['metric']} "
                             f"{v['base_err']}->{v['full_err']} (rel {v['oos_rel']:+.3%}), split-half {v['split_half']}, "
                             f"ortho {v['ortho']} -- {v['reason']}")
            if v["verdict"] == "VALIDATED":
                _propose_wiring(v)
        except Exception as e:
            log_lines.append(f"- ERROR `{spec['name']}`: {e}")
            print(f"ERROR {spec['name']}: {e}")
    if log_lines:
        head = "# Signal Lab Log\n\n" if not os.path.exists(LOG) else ""
        open(LOG, "a", encoding="utf-8").write(head + "\n".join(log_lines) + "\n")
    print(f"\norchestrator done; {len(log_lines)} verdicts -> {LOG}")
    from signal_lab import show
    show()
    _fold_warroom()


if __name__ == "__main__":
    main()
