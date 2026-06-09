"""Capstone: the Matchup Effect Engine — how coverage + scheme + player combine to
affect a game. Inverts the scheme-effects to a PER-TEAM view: facing each team's
defense, what happens to opposing players by position. One master note.
"""
import os, re
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
PSI = pd.read_parquet(ROOT/"data"/"intelligence"/"position_scheme_interactions.parquet")
DS = pd.read_parquet(ROOT/"data"/"intelligence"/"defensive_schemes.parquet")
OUT = ROOT/"vault"/"Intelligence"/"_Matchup_Effect_Engine.md"
SF = {"BALANCED":"balanced","DROP COVERAGE":"drop_coverage","HELP DEFENSE":"help_defense","ISO FORCE":"iso_force","PACE CONTROL":"pace_control","PAINT-FIRST DEFENSE":"paint_first_defense","SWITCH HEAVY":"switch_heavy","ACTIVE CLOSEOUTS":"active_closeouts","PERIMETER DENIAL":"perimeter_denial"}

def scheme_effect_summary(scheme):
    sub = PSI[(PSI.opp_scheme==scheme)&(PSI.significant)].copy()
    sub["a"]=sub.mean_dev.abs(); sub=sub.sort_values("a",ascending=False)
    supp=[f"{r.position} {r.stat} {r.mean_dev:+.2f}" for r in sub[sub.mean_dev<0].head(3).itertuples(index=False)]
    conc=[f"{r.position} {r.stat} {r.mean_dev:+.2f}" for r in sub[sub.mean_dev>0].head(3).itertuples(index=False)]
    return supp, conc

L=["# Matchup Effect Engine — how coverage, scheme & players affect games",
   "",
   "> The moat in one place: combine three layers to read any game before tip.",
   "",
   "## The three layers",
   "1. **Coverage/scheme effect** (`Schemes/_Scheme_Effects_Matrix.md` + each `Schemes/<x>.md`): how a defensive scheme moves each POSITION's box-score line vs baseline (quantified, p-valued).",
   "2. **Team scheme identity** (`Teams/<TEAM>.md` → scheme axes + dominant tag): which scheme each team actually runs, and how hard.",
   "3. **Player scheme sensitivity & H2H** (`Players/<pid>.md` → by-scheme line, best/worst scheme, 'guarded by' tough/feasts): how THIS player responds to that coverage and to specific defenders.",
   "",
   "**Read a game:** Team A's dominant scheme → look up its position effects → overlay Team B's key scorers' positions + their best/worst-scheme sensitivity + who A's stoppers are (`Scouts/_Stopper_Index`). Net = where B's production bends.",
   "",
   "## Per-team defensive effect (what facing them does to opposing positions)",
   "*Team → its dominant scheme → the positions/stats that scheme significantly suppresses (defense working) vs concedes (attack here).*",
   "",
   "| Team | Scheme identity | Suppresses (def edge) | Concedes (attack here) |",
   "|---|---|---|---|"]
for r in DS.sort_values("team").itertuples(index=False):
    scheme=r.dominant_tag
    supp,conc=scheme_effect_summary(scheme)
    fn=SF.get(scheme,"")
    L.append(f"| [[Teams/{r.team}]] | [[Schemes/{fn}|{scheme.title()}]] | {', '.join(supp) or '—'} | {', '.join(conc) or '—'} |")
L+=["", "## Worked example",
    "*Facing OKC (DROP COVERAGE + length): drop concedes a hair to SF/PF mid-range but the rim wall (Holmgren) suppresses C finishing; their DReb% (28th) is the real attack point — crash the glass. A switch-heavy opponent erases OKC's mismatch-hunting (J-Williams/Hartenstein worst-vs-switch). See [[Teams/OKC]].*",
    "",
    "> CAVEAT: these effects are season-aggregate descriptive priors — scouting/game-planning intelligence, NOT a validated betting signal. The only prop edge that survives out-of-sample is gated AST ~+5% (reg-season only); no matchup conditioner beat closing lines OOS (see `docs/_audits/INTEL_CAMPAIGN_PUNCHLIST.md`)."]
OUT.write_text("\n".join(L), encoding="utf-8")
print("wrote", OUT, "(", len(DS), "teams )")
