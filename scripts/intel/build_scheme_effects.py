"""How each COVERAGE / SCHEME affects games — the quantified intelligence moat.

Sources:
  - position_scheme_interactions.parquet: position × opp_scheme × stat -> mean
    deviation from the position's baseline, with t-stat / p-value / significance.
    This DIRECTLY measures how facing a scheme moves a position's box-score line.
  - defensive_schemes.parquet: which teams run each scheme (dominant_tag/all_tags)
    + the scheme-axis z-scores (drop/switch/paint/perimeter/pace/iso/closeout).

Writes, per scheme, a "## How This Scheme Affects Games (quantified)" section into
vault/Intelligence/Schemes/<file>.md (creates notes for ACTIVE CLOSEOUTS /
PERIMETER DENIAL which lacked one), + a master matrix
vault/Intelligence/Schemes/_Scheme_Effects_Matrix.md (position×scheme pts/ast/reb
deviation heatmap). Idempotent (marker-wrapped). Non-conflicting with player/team waves.
"""
from __future__ import annotations
import os, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PSI = ROOT / "data" / "intelligence" / "position_scheme_interactions.parquet"
DS = ROOT / "data" / "intelligence" / "defensive_schemes.parquet"
SCHEMES_D = ROOT / "vault" / "Intelligence" / "Schemes"
MS, ME = "<!-- SCHEME-EFFECT-START -->", "<!-- SCHEME-EFFECT-END -->"

SCHEME_FILE = {
    "BALANCED": "balanced", "DROP COVERAGE": "drop_coverage", "HELP DEFENSE": "help_defense",
    "ISO FORCE": "iso_force", "PACE CONTROL": "pace_control",
    "PAINT-FIRST DEFENSE": "paint_first_defense", "SWITCH HEAVY": "switch_heavy",
    "ACTIVE CLOSEOUTS": "active_closeouts", "PERIMETER DENIAL": "perimeter_denial",
}
POS_ORDER = ["PG", "SG", "SF", "PF", "C"]
STAT_ORDER = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def teams_for_scheme(ds, scheme):
    prim = sorted(ds[ds.dominant_tag == scheme].team.tolist())
    sec = sorted(ds[ds.all_tags.fillna("").str.contains(re.escape(scheme)) & (ds.dominant_tag != scheme)].team.tolist())
    return prim, sec


def upsert(path: Path, block: str, title: str):
    if path.exists():
        txt = path.read_text(encoding="utf-8")
        if MS in txt and ME in txt:
            txt = re.sub(re.escape(MS) + r".*?" + re.escape(ME) + r"\n?", "", txt, flags=re.S)
        txt = txt.rstrip() + "\n\n" + block
    else:
        txt = f"# {title}\n\n*Defensive coverage / scheme — how it affects games.*\n\n" + block
    path.write_text(txt, encoding="utf-8")


def main():
    psi = pd.read_parquet(PSI)
    ds = pd.read_parquet(DS)
    matrix_rows = {}  # (scheme) -> {pos: pts_dev}

    for scheme, fname in SCHEME_FILE.items():
        sub = psi[psi.opp_scheme == scheme].copy()
        sig = sub[sub.significant].copy()
        sig["abs_dev"] = sig.mean_dev.abs()
        sig = sig.sort_values("abs_dev", ascending=False)
        prim, sec = teams_for_scheme(ds, scheme)

        L = [MS, "", "## How This Scheme Affects Games (quantified)",
             "*From position_scheme_interactions: mean deviation of each position's per-game stat vs its "
             "baseline when facing this scheme. Negative = the scheme SUPPRESSES it (defense working); "
             "positive = it CONCEDES more. Only statistically significant (p<0.05) effects listed.*", ""]
        if len(prim) or len(sec):
            L.append(f"**Teams whose identity is this scheme:** {', '.join('[[Teams/'+t+']]' for t in prim) or '—'}")
            if sec:
                L.append(f"**Teams that also show it (secondary tag):** {', '.join('[[Teams/'+t+']]' for t in sec)}")
            L.append("")
        if len(sig):
            L.append("| Position | Stat | Δ vs baseline | baseline → actual | p | reading |")
            L.append("|---|---|---|---|---|---|")
            for r in sig.head(20).itertuples(index=False):
                read = "suppresses" if r.mean_dev < 0 else "concedes"
                L.append(f"| {r.position} | {r.stat} | {r.mean_dev:+.2f} | {r.mean_baseline:.1f} → {r.mean_actual:.1f} | "
                         f"{r.p_value:.3f} | **{read}** (n={r.n}) |")
            # narrative
            supp = sig[sig.mean_dev < 0].head(4)
            conc = sig[sig.mean_dev > 0].head(4)
            L.append("")
            if len(supp):
                L.append("- **Most suppressed:** " + "; ".join(f"{r.position} {r.stat} {r.mean_dev:+.2f}" for r in supp.itertuples(index=False)))
            if len(conc):
                L.append("- **Most conceded:** " + "; ".join(f"{r.position} {r.stat} {r.mean_dev:+.2f}" for r in conc.itertuples(index=False)))
        else:
            L.append("*No statistically significant position effects in the current sample.*")
        L += ["", ME, ""]
        # matrix: pts deviation per position (sig or not, for heatmap)
        pts = sub[sub.stat == "pts"].set_index("position")["mean_dev"].to_dict()
        matrix_rows[scheme] = pts

        path = SCHEMES_D / f"{fname}.md"
        title = scheme.title().replace("-", "-")
        upsert(path, "\n".join(L), title + " Defense")
        print(f"  {scheme:22s} -> {fname}.md  ({len(sig)} sig effects, teams primary={len(prim)})")

    # master matrix (pts deviation, position × scheme)
    M = ["# Scheme Effects Matrix — points deviation by position",
         "*How each defensive scheme moves a position's scoring vs baseline (pts/g). "
         "Negative = scheme suppresses that position. From position_scheme_interactions.*", "",
         "| Scheme | " + " | ".join(POS_ORDER) + " |", "|---|" + "---|" * len(POS_ORDER)]
    for scheme in SCHEME_FILE:
        cells = []
        for pos in POS_ORDER:
            v = matrix_rows.get(scheme, {}).get(pos)
            cells.append(f"{v:+.2f}" if v is not None else "—")
        M.append(f"| [[Schemes/{SCHEME_FILE[scheme]}]] | " + " | ".join(cells) + " |")
    M += ["", "> Read down a column to see which scheme most hurts a position's scoring; "
          "across a row to see which positions a scheme controls. Pair with each player's best/worst "
          "scheme (in their note) and the team scheme identities (Teams/<TEAM>)."]
    (SCHEMES_D / "_Scheme_Effects_Matrix.md").write_text("\n".join(M), encoding="utf-8")
    print(f"  wrote _Scheme_Effects_Matrix.md")


if __name__ == "__main__":
    main()
