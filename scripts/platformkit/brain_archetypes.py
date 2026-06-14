"""scripts.platformkit.brain_archetypes — PERSON-FREE as-of archetype clustering.

Clusters each sport's entities by their LEAK-FREE as-of feature profiles into a
small set of NAMED archetypes via a SIMPLE DETERMINISTIC method (quantile/tertile
bucketing on 2-3 key as-of dims), then renders dense person-free brain notes
``vault/_Organized/<SPORT>/Archetypes/_Computed_<kind>.md`` (``_Computed_`` prefix
keeps them distinct from legacy hand-curated playstyle notes) + ``_Computed_Index.md``.

PERSON-FREE: notes carry ONLY archetype labels, numeric centroids and shares — no
entity names.  HONEST: archetypes are calibration / understanding context, NOT a
market edge; no edge claimed.  Heavy imports LAZY; missing corpus skips honestly.
DETERMINISTIC (no randomness; tertile cuts reproducible) so rebuilds are byte-stable.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.atlas.obsidian_emit import frontmatter, write_note

_HONEST = ("intelligence / calibration context, NOT a market edge; "
           "markets are efficient; no edge claimed")

# (profile_sentence, model_implication) — person-free, centroid-derived, no edge claims.
_SP_PROFILES: Dict[str, Tuple[str, str]] = {
    "ace_workhorse":         ("Low trailing RA, deep prior-start record; consistent suppressor.",
                              "Tight low-variance Poisson mean well below league average."),
    "front_line_arm":        ("Low trailing RA, moderate sample; suppression established.",
                              "Moderate shrinkage toward population mean; wider tails than ace."),
    "emerging_suppressor":   ("Low trailing RA, shallow sample; quality signal but sparse.",
                              "High posterior uncertainty; strong prior pull toward population."),
    "steady_innings_eater":  ("Mid RA, deep sample; reliable volume without elite suppression.",
                              "Near-average Poisson mean, low variance; sample reduces uncertainty."),
    "mid_rotation_arm":      ("Mid RA, moderate sample; typical rotation, no directional signal.",
                              "Calibrate to population mean; standard variance appropriate."),
    "unproven_mid":          ("Mid RA, shallow sample; limited calibration information.",
                              "Default to population prior; wide distribution reflects sparse data."),
    "volatile_veteran":      ("High RA despite deep sample; persistent high-scoring outcomes.",
                              "Above-average Poisson mean; fat right tail — shape matters."),
    "volatile_short_outing": ("High RA, moderate sample; short outings and run concession cluster.",
                              "Above-average mean; model early-exit probability for inning-count skew."),
    "raw_volatile":          ("High RA, shallow sample; volatile results, minimal track record.",
                              "Maximum prior weight; very wide distribution — NegBinom over-dispersion."),
}

_TEAM_PROFILES: Dict[str, Tuple[str, str]] = {
    "high_press_attacker":   ("High SoT-for, low SoT-against; dominant attack, strong defensive shape.",
                              "Skew Poisson high for attack, low for concede; finishing regression applies."),
    "front_foot_attacker":   ("High SoT-for, mid SoT-against; consistent attack, ordinary defensive exposure.",
                              "Above-average attack Poisson; moderate concede variance."),
    "open_end_to_end":       ("High SoT on both sides; attacking but porous, high-volume games.",
                              "Both Poisson means elevated; NegBinom over-dispersion for totals."),
    "balanced_control":      ("Mid SoT-for, low SoT-against; controlled style limiting opponent threat.",
                              "Near-average attack, low concede mean; narrow total distribution."),
    "balanced_midtable":     ("Mid SoT on both sides; no strong directional signal.",
                              "Both means near population average; standard-variance calibration."),
    "leaky_neutral_attack":  ("Mid SoT-for, high SoT-against; neither dominant nor defensively sound.",
                              "Elevated concede mean; heavier right tail on opposition goals."),
    "low_block_grinder":     ("Low SoT-for, low SoT-against; deep block, limited offensive output.",
                              "Low Poisson means both sides; finishing regression compresses outcomes."),
    "cautious_midtable":     ("Low SoT-for, mid SoT-against; passive, concedes moderate volume.",
                              "Below-average attack mean; under-total lean needs careful calibration."),
    "outshot_strugglers":    ("Low SoT-for, high SoT-against; outshot in both phases.",
                              "Low attack, elevated concede mean; fat right tail on goals-against."),
}


def _tertiles(vals: Sequence[float]) -> Tuple[float, float]:
    """Return (lo_cut, hi_cut) 33/66 quantiles; degenerate -> NaN cuts."""
    xs = sorted(float(v) for v in vals if v == v)
    if not xs:
        return float("nan"), float("nan")
    n = len(xs)
    return xs[max(0, int(round(0.3333 * (n - 1))))], xs[max(0, int(round(0.6667 * (n - 1))))]


def _bucket(v: float, lo: float, hi: float) -> int:
    """0=low, 1=mid, 2=high relative to tertile cuts (NaN -> mid)."""
    if v != v or lo != lo:
        return 1
    return 0 if v <= lo else 2 if v >= hi else 1


# ---------------------------------------------------------------------------
# MLB starting-pitcher archetypes
# ---------------------------------------------------------------------------
_SP_LABELS = {
    (0, 2): "ace_workhorse", (0, 1): "front_line_arm", (0, 0): "emerging_suppressor",
    (1, 2): "steady_innings_eater", (1, 1): "mid_rotation_arm", (1, 0): "unproven_mid",
    (2, 2): "volatile_veteran", (2, 1): "volatile_short_outing", (2, 0): "raw_volatile",
}


def _mlb_sp_entities() -> Optional[List[Dict[str, float]]]:
    """Per-SP as-of rows: {form_ra, starts, hand} — None if source absent."""
    try:
        from domains.mlb.asof_sp_form import build_sp_form_features  # lazy
        df = build_sp_form_features()
    except Exception:  # noqa: BLE001
        return None
    rows: List[Dict[str, float]] = []
    for side in ("home", "away"):
        ew, starts, hand = (df[f"{side}_sp_first6_ew"], df[f"{side}_sp_starts_prior"],
                            df[f"{side}_sp_hand"])
        for i in range(len(df)):
            n, v = int(starts.iloc[i]), float(ew.iloc[i])
            if n <= 0 or v != v:
                continue
            rows.append({"form_ra": v, "starts": float(n), "hand": str(hand.iloc[i]) or "?"})
    return rows or None


def _cluster_mlb_sp(rows: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    ra_lo, ra_hi = _tertiles([r["form_ra"] for r in rows])
    n_lo, n_hi = _tertiles([r["starts"] for r in rows])
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        label = _SP_LABELS[(_bucket(r["form_ra"], ra_lo, ra_hi), _bucket(r["starts"], n_lo, n_hi))]
        a = agg.setdefault(label, {"n": 0.0, "form_ra": 0.0, "starts": 0.0, "lhp": 0.0})
        a["n"] += 1.0; a["form_ra"] += r["form_ra"]; a["starts"] += r["starts"]
        a["lhp"] += 1.0 if r["hand"] == "L" else 0.0
    return agg


# ---------------------------------------------------------------------------
# Soccer team-style archetypes
# ---------------------------------------------------------------------------
_TEAM_LABELS = {
    (2, 0): "high_press_attacker", (2, 1): "front_foot_attacker", (2, 2): "open_end_to_end",
    (1, 0): "balanced_control", (1, 1): "balanced_midtable", (1, 2): "leaky_neutral_attack",
    (0, 0): "low_block_grinder", (0, 1): "cautious_midtable", (0, 2): "outshot_strugglers",
}


def _soccer_team_entities() -> Optional[List[Dict[str, float]]]:
    """Per-team as-of style rows: {attack, concede} — None if source absent."""
    repo = Path(__file__).resolve().parents[2]
    src = repo / "data" / "domains" / "soccer" / "match_stats.parquet"
    if not src.exists():
        return None
    try:
        from domains.soccer.asof_features import build_asof_frame  # lazy
        import pyarrow.parquet as pq  # lazy
        df = build_asof_frame(pq.read_table(src).to_pandas())
    except Exception:  # noqa: BLE001
        return None
    rows: List[Dict[str, float]] = []
    for side in ("home", "away"):
        att, conc, npr = (df[f"{side}_sot_for_asof"], df[f"{side}_sot_against_asof"],
                         df[f"{side}_n_prior"])
        for i in range(len(df)):
            if int(npr.iloc[i]) <= 0:
                continue
            a, c = float(att.iloc[i]), float(conc.iloc[i])
            if a != a or c != c:
                continue
            rows.append({"attack": a, "concede": c})
    return rows or None


def _cluster_soccer_team(rows: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    a_lo, a_hi = _tertiles([r["attack"] for r in rows])
    c_lo, c_hi = _tertiles([r["concede"] for r in rows])
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        label = _TEAM_LABELS[(_bucket(r["attack"], a_lo, a_hi), _bucket(r["concede"], c_lo, c_hi))]
        a = agg.setdefault(label, {"n": 0.0, "attack": 0.0, "concede": 0.0})
        a["n"] += 1.0; a["attack"] += r["attack"]; a["concede"] += r["concede"]
    return agg


_SignatureRow = Tuple[str, int, float, List[Tuple[str, float]]]


def _signatures(agg: Dict[str, Dict[str, float]],
                cols: Sequence[Tuple[str, str]]) -> Tuple[int, List[_SignatureRow]]:
    total = int(sum(a["n"] for a in agg.values())) or 1
    out = [(label, int(a["n"]), int(a["n"]) / total,
            [(disp, a[key] / a["n"] if a["n"] else float("nan")) for key, disp in cols])
           for label, a in agg.items()]
    out.sort(key=lambda r: (-r[1], r[0]))
    return total, out


# (sport, kind_id, title, dims, entities_fn_NAME, cluster_fn, sig_cols, mechanism, profiles)
_KINDS: List[Tuple] = [
    ("MLB", "starting_pitchers", "Starting-Pitcher Archetypes",
     "trailing EW first-6-innings runs-allowed x prior-start depth",
     "_mlb_sp_entities", _cluster_mlb_sp,
     [("form_ra", "EW first-6 RA"), ("starts", "prior starts"), ("lhp", "left-handed share")],
     "Buckets each starter's leak-free trailing run-suppression form against its "
     "track-record depth: low RA + deep sample => ace tier; high RA + shallow sample => raw/volatile.",
     _SP_PROFILES),
    ("Soccer", "team_styles", "Team-Style Archetypes",
     "as-of shots-on-target FOR x shots-on-target AGAINST",
     "_soccer_team_entities", _cluster_soccer_team,
     [("attack", "SoT-for as-of"), ("concede", "SoT-against as-of")],
     "Buckets each team's leak-free trailing attack (SoT created) against suppression (SoT conceded): "
     "high-create/low-concede => high-press attacker; low-create/high-concede => outshot strugglers.",
     _TEAM_PROFILES),
]

_WIKILINKS = "[[Archetypes/_Computed_Index]] | [[_WhatWins]] | [[_Mechanisms]] | [[_Index]]"


def _render(sport: str, title: str, dims: str, total: int,
            sigs: List[_SignatureRow], cols: Sequence[Tuple[str, str]],
            mechanism: str, profiles: Dict[str, Tuple[str, str]]) -> str:
    """Render a dense person-free archetype note body with profiles + interlinks."""
    fm = frontmatter({"tags": [f"sport/{sport.lower()}", "archetype", "computed", "honest"],
                      "generated": time.strftime("%Y-%m-%d"),
                      "kind": title, "entities_clustered": total, "archetypes": len(sigs)})
    head = [disp for _, disp in cols]
    L: List[str] = [
        fm, "", f"# Computed Archetypes — {sport} {title}", "",
        f"up:: {_WIKILINKS}", "",
        f"> **Honest framing:** {_HONEST}.  PERSON-FREE: only archetype labels,",
        "> numeric centroids and population shares — no entity names.", "",
        "## Method", "",
        f"Deterministic tertile bucketing on **{dims}** over **{total:,}** leak-free as-of profiles.",
        "No randomness; reproducible.", "",
        "## Mechanism", "", mechanism, "",
        "## Archetypes (centroid signatures + share)", "",
        "| Archetype | n | Share | " + " | ".join(head) + " |",
        "|-----------|---|-------|" + "|".join("-" * (len(h) + 2) for h in head) + "|",
    ]
    for label, n, share, centroids in sigs:
        L.append("| " + label + " | " + f"{n:,}" + " | " + f"{share * 100:.1f}%" + " | " +
                 " | ".join(f"{v:.3f}" if v == v else "N/A" for _, v in centroids) + " |")
    L += ["", "## Stylistic Profiles and Model Implications", "",
          "_Person-free descriptions from centroid; model implication = distribution-shape/"
          "calibration guidance, NOT an edge claim._", ""]
    for label, n, share, _ in sigs:
        prof, impl = profiles.get(label, ("No profile defined.", "No implication defined."))
        L += [f"### {label}", f"**Stylistic profile:** {prof}",
              f"**Model implication:** {impl}", ""]
    L += ["## Reading the Signature", "",
          "Each row is a CLUSTER CENTROID — mean as-of profile of every entity in that "
          "quantile cell, not any single entity.  No entity names stored.", "", "---", "",
          f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · {len(sigs)} archetypes · "
          f"{total:,} entities · person-free · no edge claimed*", "",
          f"_PRIVATE research.  {_HONEST}._", ""]
    return "\n".join(L) + "\n"


def _render_index(sport: str, kinds: List[Tuple[str, str, int, int]]) -> str:
    """Per-sport index linking to each computed archetype note."""
    fm = frontmatter({"tags": [f"sport/{sport.lower()}", "archetype", "computed", "index"],
                      "generated": time.strftime("%Y-%m-%d")})
    L = [fm, "", f"# {sport} — Computed Archetype Index", "",
         f"up:: [[_Index]] | [[_WhatWins]] | [[_Mechanisms]]", "",
         f"> {_HONEST}.  PERSON-FREE.", "",
         "| Kind | Archetypes | Entities |", "|------|-----------|----------|"]
    for fname, title, n_arch, n_ent in kinds:
        L.append(f"| [[Archetypes/{fname}\\|{title}]] | {n_arch} | {n_ent:,} |")
    L += ["", "## Notes", ""]
    for fname, title, _, _ in kinds:
        L.append(f"- [[Archetypes/{fname}]] — {title}")
    L += ["", f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · person-free · no edge claimed*", ""]
    return "\n".join(L) + "\n"


def build_archetypes(vault_organized_dir: Optional[Path] = None) -> List[Path]:
    """Cluster each sport's as-of profiles into person-free archetype notes.

    Writes ``_Computed_<kind>.md`` + ``_Computed_Index.md`` per sport under
    ``<vault>/<SPORT>/Archetypes/``; absent corpora skip honestly.  Deterministic.
    """
    if vault_organized_dir is None:
        vault_organized_dir = Path(__file__).resolve().parents[2] / "vault" / "_Organized"
    root = Path(vault_organized_dir)
    written: List[Path] = []
    by_sport: Dict[str, List[Tuple[str, str, int, int]]] = {}
    for sport, kind_id, title, dims, ent_name, cl_fn, cols, mech, profs in _KINDS:
        rows = globals()[ent_name]()
        if not rows:
            continue
        total, sigs = _signatures(cl_fn(rows), cols)
        fname = f"_Computed_{kind_id}"
        out = root / sport / "Archetypes" / f"{fname}.md"
        written.append(write_note(out, _render(sport, title, dims, total, sigs, cols, mech, profs)))
        by_sport.setdefault(sport, []).append((fname, title, len(sigs), total))
    for sport, kinds in by_sport.items():
        idx = root / sport / "Archetypes" / "_Computed_Index.md"
        written.append(write_note(idx, _render_index(sport, kinds)))
    return written


if __name__ == "__main__":
    import sys
    for _p in build_archetypes(Path(sys.argv[1]) if len(sys.argv) > 1 else None):
        print(f"Written: {_p}")
