"""Fold the FULL 87-attribute deep vault + the context-effect spine into EVERY player note.

The player notes exposed only category summaries; the attribute_vault holds 87 league-percentile
(0-99) attributes per player. This folds the COMPLETE vault (grouped) into every player note that has
vault data (league-wide depth) as `## Deep Attribute Vault`, plus the per-entity context-effect spine
(`player_effects_full`: rest/defense-tier/pace eFG sensitivities) into NYK/SAS notes as `## Context
Effect Spine`. So every player's memory carries every measured detail the matchup resolver composes.
Idempotent marker upsert.

  python scripts/team_system/fold_deep_attributes.py
"""
from __future__ import annotations
import glob, os, re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
VS, VE = "<!-- SIGNALS:deep-vault START -->", "<!-- SIGNALS:deep-vault END -->"
ES, EE = "<!-- SIGNALS:effect-spine START -->", "<!-- SIGNALS:effect-spine END -->"

# attribute prefix -> (group title, ordered nice labels). Anything unmatched falls into "Other".
GROUPS = [
    ("fin_", "Finishing"), ("shoot_", "Shooting"), ("play_", "Playmaking"), ("crea_", "Creation"),
    ("score_", "Scoring"), ("reb_", "Rebounding"), ("intd_", "Interior D"), ("perd_", "Perimeter D"),
    ("clutch_", "Clutch"), ("iq_", "IQ / Discipline"), ("form_", "Form"), ("sit_", "Situational"),
    ("motor_", "Motor"), ("durab_", "Durability"), ("phys_", "Physical"),
]
SKIP = {"pid", "player", "team", "season", "player_id", "mpg"}


def _label(col, prefix):
    return col[len(prefix):].replace("_", " ")


def vault_block(row, cols):
    L = [VS, "", "## Deep Attribute Vault",
         "*All 87 league-percentile (0-99) attributes the ratings + matchup resolver reason over "
         "(opponent-adjusted D, usage-adjusted efficiency, volume-gated). 50 = league average.*", ""]
    for prefix, title in GROUPS:
        items = [(c, row[c]) for c in cols if c.startswith(prefix) and pd.notna(row[c])]
        if not items:
            continue
        cells = " · ".join(f"{_label(c, prefix)} **{int(round(v))}**" for c, v in items)
        L.append(f"- **{title}:** {cells}")
    L += ["", VE, ""]
    return "\n".join(L)


def spine_block(e):
    def arrow(x):
        return f"x{x:.3f}" + (" (+)" if x > 1.015 else " (-)" if x < 0.985 else "")
    L = [ES, "", "## Context Effect Spine",
         "*Per-entity, confidence-weighted context multipliers (empirical-Bayes shrink, sharpen with "
         "data) that the matchup resolver composes. Descriptive matchup intelligence — not a standalone "
         "betting edge (see EDGE_GATE).*", "",
         f"**Rest / B2B:** eFG on short rest {arrow(e.b2b_xfg)} (n={e.b2b_n}); production {arrow(e.b2b_use)}.",
         f"**Vs defense tier:** vs TOUGH D {arrow(e.vs_strongD_xfg)} (n={e.strongD_n}) · vs WEAK D "
         f"{arrow(e.vs_weakD_xfg)} (n={e.weakD_n}) → matchup-sensitivity **{e.matchup_sensitivity:+.3f}** "
         f"(high = feasts on weak D, struggles vs elite).",
         f"**Pace:** fast games {arrow(e.fast_xfg)} (n={e.fast_n}) · slow games {arrow(e.slow_xfg)} (n={e.slow_n}).",
         "", EE, ""]
    return "\n".join(L)


def upsert(fp, blk, S, E):
    txt = open(fp, encoding="utf-8").read()
    if S in txt and E in txt:
        txt = re.sub(re.escape(S) + r".*?" + re.escape(E) + r"\n?", "", txt, flags=re.S)
    open(fp, "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)


def main():
    v = pd.read_parquet(os.path.join(TS, "attribute_vault.parquet"))
    cols = [c for c in v.columns if c not in SKIP]
    eff = pd.read_parquet(os.path.join(TS, "player_effects_full.parquet")).set_index("pid")
    vault_folded = spine_folded = skipped = 0
    for row in v.itertuples(index=False):
        d = row._asdict()
        pid = int(d.get("pid") or d.get("player_id") or 0)
        if not pid:
            skipped += 1; continue
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped += 1; continue
        upsert(cands[0], vault_block(d, cols), VS, VE); vault_folded += 1
        if pid in eff.index:
            upsert(cands[0], spine_block(eff.loc[pid]), ES, EE); spine_folded += 1
    print(f"DONE: deep vault folded into {vault_folded} player notes ({skipped} had no note); "
          f"context effect spine into {spine_folded} NYK/SAS notes.")


if __name__ == "__main__":
    main()
