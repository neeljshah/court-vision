"""ATTRIBUTE CLASH — resolve a matchup FACET-BY-FACET from the 87-attribute vault.

The matchup resolver (build_matchup_resolution) composes the SCORING projection. This composes the
MATCHUP ITSELF: when team A faces team B, clash each offensive facet against the opponent's corresponding
defensive facet (rim finishing vs rim protection, catch-&-shoot vs closeout, OREB vs DREB, drives vs
perimeter D, drawing fouls vs foul discipline...). Every facet edge = off attribute - opp defensive
attribute (0-99 league percentile, 50 = average; positive = the offense wins that facet). Works league-wide
off attribute_vault, so ANY A-vs-B is fully determined facet by facet.

Folds `## Attribute Clash` into the War Room: a team-level facet grid (minute-weighted) + the sharpest
per-player facet mismatches. Descriptive scouting intelligence (the vault is opponent/usage-adjusted,
volume-gated) -- it explains WHERE a matchup is won, alongside the sim's point projection.

  python scripts/team_system/build_attribute_clash.py [--home NYK --away SAS]
"""
from __future__ import annotations
import argparse, os, re
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
WARROOM = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
S, E = "<!-- SIGNALS:attribute-clash START -->", "<!-- SIGNALS:attribute-clash END -->"

# (facet label, offensive attr, opponent DEFENSIVE attr). Only CLEAN, well-opposed clashes where both
# attrs are on the 0-99 percentile scale AND the defensive attr genuinely defends that facet. (perd_versatility
# was dropped: it saturates at 99 in team aggregates -> meaningless edges; playmaking has no clean vault
# defensive opposition.) A per-facet saturation guard (def aggregate must be in [8,92]) skips any that degenerate.
FACETS = [
    ("Rim finishing", "fin_rim_pct", "intd_fg_suppress"),
    ("Rim pressure (vol)", "fin_rim_volume", "intd_block"),
    ("Paint scoring", "fin_paint_pts", "intd_stops"),
    ("Drives", "crea_drives_vol", "perd_stops"),
    ("Catch & shoot 3", "shoot_catch_shoot3", "perd_fg3_suppress"),
    ("Iso / PnR creation", "crea_pnr_ppp", "perd_stops"),
    ("Off. rebounding", "reb_oreb_pct", "reb_dreb_pct"),
    ("Drawing fouls", "fin_contact_ft", "perd_foul_disc"),
]
SAT_LO, SAT_HI = 8.0, 92.0          # skip a facet whose opponent defensive aggregate is saturated (non-discriminating)


def _wmean(df, col, w):
    v = df[col].values.astype(float); m = np.isfinite(v)
    return float(np.average(v[m], weights=w[m])) if m.any() and w[m].sum() > 0 else np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    a = ap.parse_args()
    v = pd.read_parquet(os.path.join(TS, "attribute_vault.parquet"))
    pidcol = "pid" if "pid" in v.columns else "player_id"
    v = v.set_index(pidcol)
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))

    def roster(tri):
        r = rates[(rates.team == tri) & (rates.mpg >= 12)].copy()
        r = r[r.pid.isin(v.index)]
        r["w"] = r["mpg"].values
        return r

    def team_attr(r, col):
        sub = v.loc[r.pid.values]
        return _wmean(sub.assign(_w=r.w.values), col, r.w.values) if col in v.columns else np.nan

    lines = [S, "", "## Attribute Clash — every facet, A vs B",
             f"*{a.away} @ {a.home}. Each offensive facet vs the opponent's defensive facet (0-99 vault "
             f"percentile, minute-weighted; edge = offense - defense, + = offense wins). Resolves WHERE the "
             f"matchup is won, league-wide off the deep vault.*", ""]

    for off_tri, def_tri in ((a.home, a.away), (a.away, a.home)):
        ro, rd = roster(off_tri), roster(def_tri)
        lines += ["", f"### {off_tri} offense vs {def_tri} defense", "",
                  "| facet | " + off_tri + " off | " + def_tri + " def | edge |", "|---|--:|--:|--:|"]
        for label, oc, dc in FACETS:
            o = team_attr(ro, oc); d = team_attr(rd, dc)
            if not np.isfinite(o) or not np.isfinite(d) or not (SAT_LO <= d <= SAT_HI):
                continue
            edge = o - d
            tag = " ✅" if edge >= 8 else " ⚠️" if edge <= -8 else ""
            lines.append(f"| {label} | {o:.0f} | {d:.0f} | **{edge:+.0f}**{tag} |")
        # sharpest per-player facet mismatches (his facet vs opp defensive aggregate)
        dagg = {dc: team_attr(rd, dc) for _, _, dc in FACETS}
        edges = []
        for r in ro.itertuples(index=False):
            if r.pid not in v.index:
                continue
            pv = v.loc[r.pid]
            for label, oc, dc in FACETS:
                d = dagg.get(dc, np.nan)
                # only facets the player ACTUALLY does (off pct >= 50) -> "exploit"/"contained" mean a real
                # strength won/neutralized, not a facet he never uses (a center's "drives 6").
                if oc in v.columns and np.isfinite(d) and (SAT_LO <= d <= SAT_HI) and pd.notna(pv[oc]) and float(pv[oc]) >= 50:
                    edges.append((float(pv[oc]) - d, r.player, label, float(pv[oc]), d))
        edges.sort(reverse=True)
        top = [e for e in edges if e[0] > 0][:4]; bot = [e for e in edges if e[0] < 0][-3:]
        if top:
            lines.append("")
            lines.append("**Exploit:** " + " · ".join(f"{n} {l} ({o:.0f} vs {d:.0f}, {e:+.0f})" for e, n, l, o, d in top))
        if bot:
            lines.append("**Contained:** " + " · ".join(f"{n} {l} ({o:.0f} vs {d:.0f}, {e:+.0f})" for e, n, l, o, d in reversed(bot)))

    lines += ["", "*Vault is opponent/usage-adjusted + volume-gated; this is scouting intelligence (where the "
              "matchup tilts), composed alongside the sim's point projection (§Matchup Resolution).*", "", E, ""]
    block = "\n".join(lines)

    if os.path.exists(WARROOM):
        txt = open(WARROOM, encoding="utf-8").read()
        if S in txt and E in txt:
            txt = re.sub(re.escape(S) + r".*?" + re.escape(E), block, txt, flags=re.S)
        else:
            txt = txt.rstrip() + "\n\n" + block + "\n"
        open(WARROOM, "w", encoding="utf-8").write(txt)
        print(f"folded ## Attribute Clash into the War Room ({a.away} @ {a.home}).")
    else:
        print(block[:1600])


if __name__ == "__main__":
    main()
