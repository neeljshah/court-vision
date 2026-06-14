"""scripts.platformkit.brain_archetypes — PERSON-FREE as-of archetype clustering.

Clusters each sport's entities by their LEAK-FREE as-of feature profiles into a
small set of NAMED archetypes via a SIMPLE DETERMINISTIC method (quantile/tertile
bucketing on 2-3 key as-of dims), then renders dense person-free brain notes
``vault/_Organized/<SPORT>/Archetypes/_Computed_<kind>.md`` (the ``_Computed_``
prefix keeps them distinct from the legacy hand-curated playstyle notes) + a
``_Computed_Index.md`` per sport.

KINDS shipped:
  * MLB starting pitchers (justified role-grain: the SP is MLB's biggest predictor)
    from ``domains.mlb.asof_sp_form.build_sp_form_features`` — store the ARCHETYPE
    (ace / innings-eater / volatile-short ...) + numeric signature, NEVER names.
  * Soccer teams from ``domains.soccer.asof_features`` — store the STYLE archetype +
    signature, never the team.

PERSON-FREE: notes carry ONLY archetype labels, numeric centroids and shares — no
entity names.  HONEST: archetypes are calibration / understanding context, NOT a
market edge; no edge claimed.  Heavy pandas + source builders import LAZILY (a
missing corpus skips that kind honestly).  DETERMINISTIC (no randomness; tertile
cuts reproducible) so brain rebuilds are byte-stable.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.atlas.obsidian_emit import frontmatter, write_note
_HONEST = ("intelligence / calibration context, NOT a market edge; "
           "markets are efficient; no edge claimed")


def _tertiles(vals: Sequence[float]) -> Tuple[float, float]:
    """Return (lo_cut, hi_cut) 33/66 quantiles; degenerate -> equal cuts."""
    xs = sorted(float(v) for v in vals if v == v)  # drop NaN
    if not xs:
        return float("nan"), float("nan")
    n = len(xs)
    lo = xs[max(0, int(round(0.3333 * (n - 1))))]
    hi = xs[max(0, int(round(0.6667 * (n - 1))))]
    return lo, hi


def _bucket(v: float, lo: float, hi: float) -> int:
    """0=low, 1=mid, 2=high relative to tertile cuts (NaN -> mid)."""
    if v != v or lo != lo:
        return 1
    if v <= lo:
        return 0
    if v >= hi:
        return 2
    return 1


# ---------------------------------------------------------------------------
# MLB starting-pitcher archetypes (role-grain justified: SP = biggest predictor)
# ---------------------------------------------------------------------------

# bucket(form_ra) x bucket(starts) -> archetype label.  form low == fewer runs.
_SP_LABELS = {
    (0, 2): "ace_workhorse",      # suppresses runs, deep track record
    (0, 1): "front_line_arm",     # suppresses runs, moderate sample
    (0, 0): "emerging_suppressor",
    (1, 2): "steady_innings_eater",
    (1, 1): "mid_rotation_arm",
    (1, 0): "unproven_mid",
    (2, 2): "volatile_veteran",   # allows more runs despite long sample
    (2, 1): "volatile_short_outing",
    (2, 0): "raw_volatile",
}


def _mlb_sp_entities() -> Optional[List[Dict[str, float]]]:
    """Per-SP as-of rows: {form_ra, starts, hand} — None if source/corpus absent.

    PERSON-FREE: never key on the SP name; each per-game side-snapshot with >=1
    prior start is one as-of entity profile (handedness kept as a categorical).
    """
    try:
        from domains.mlb.asof_sp_form import build_sp_form_features  # lazy
        df = build_sp_form_features()
    except Exception:  # noqa: BLE001
        return None
    rows: List[Dict[str, float]] = []
    for side in ("home", "away"):
        ew = df[f"{side}_sp_first6_ew"]
        starts = df[f"{side}_sp_starts_prior"]
        hand = df[f"{side}_sp_hand"]
        for i in range(len(df)):
            n = int(starts.iloc[i])
            v = float(ew.iloc[i])
            if n <= 0 or v != v:
                continue
            rows.append({"form_ra": v, "starts": float(n),
                         "hand": str(hand.iloc[i]) or "?"})
    return rows or None


def _cluster_mlb_sp(rows: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """Bucket SP profiles into archetypes; return label -> signature dict."""
    ra_lo, ra_hi = _tertiles([r["form_ra"] for r in rows])
    n_lo, n_hi = _tertiles([r["starts"] for r in rows])
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        key = (_bucket(r["form_ra"], ra_lo, ra_hi), _bucket(r["starts"], n_lo, n_hi))
        label = _SP_LABELS[key]
        a = agg.setdefault(label, {"n": 0.0, "form_ra": 0.0, "starts": 0.0,
                                   "lhp": 0.0})
        a["n"] += 1.0
        a["form_ra"] += r["form_ra"]
        a["starts"] += r["starts"]
        a["lhp"] += 1.0 if r["hand"] == "L" else 0.0
    return agg


# ---------------------------------------------------------------------------
# Soccer team-style archetypes (store the style, never the team)
# ---------------------------------------------------------------------------

_TEAM_LABELS = {
    (2, 0): "high_press_attacker",   # creates a lot, concedes few
    (2, 1): "front_foot_attacker",
    (2, 2): "open_end_to_end",
    (1, 0): "balanced_control",
    (1, 1): "balanced_midtable",
    (1, 2): "leaky_neutral_attack",
    (0, 0): "low_block_grinder",
    (0, 1): "cautious_midtable",
    (0, 2): "outshot_strugglers",
}


def _soccer_team_entities() -> Optional[List[Dict[str, float]]]:
    """Per-team as-of style rows: {attack, concede} — None if source/corpus absent."""
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
        att = df[f"{side}_sot_for_asof"]
        conc = df[f"{side}_sot_against_asof"]
        npr = df[f"{side}_n_prior"]
        for i in range(len(df)):
            if int(npr.iloc[i]) <= 0:
                continue
            a, c = float(att.iloc[i]), float(conc.iloc[i])
            if a != a or c != c:
                continue
            rows.append({"attack": a, "concede": c})
    return rows or None


def _cluster_soccer_team(rows: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """Bucket team styles into archetypes; return label -> signature dict."""
    a_lo, a_hi = _tertiles([r["attack"] for r in rows])
    c_lo, c_hi = _tertiles([r["concede"] for r in rows])
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        key = (_bucket(r["attack"], a_lo, a_hi), _bucket(r["concede"], c_lo, c_hi))
        label = _TEAM_LABELS[key]
        a = agg.setdefault(label, {"n": 0.0, "attack": 0.0, "concede": 0.0})
        a["n"] += 1.0
        a["attack"] += r["attack"]
        a["concede"] += r["concede"]
    return agg


_SignatureRow = Tuple[str, int, float, List[Tuple[str, float]]]


def _signatures(agg: Dict[str, Dict[str, float]],
                cols: Sequence[Tuple[str, str]]) -> Tuple[int, List[_SignatureRow]]:
    """Convert raw sums -> (total_n, [(label, n, share, [(col_disp, centroid)])])."""
    total = int(sum(a["n"] for a in agg.values())) or 1
    out: List[_SignatureRow] = []
    for label in sorted(agg):
        a = agg[label]
        n = int(a["n"])
        centroids = [(disp, (a[key] / a["n"]) if a["n"] else float("nan"))
                     for key, disp in cols]
        out.append((label, n, n / total, centroids))
    out.sort(key=lambda r: (-r[1], r[0]))
    return total, out


# (sport, kind_id, title, dims, entities_fn_NAME, cluster_fn, sig_cols, mechanism)
# entities_fn stored by NAME, resolved via globals() at call time (monkeypatch-able).
_KINDS: List[Tuple] = [
    ("MLB", "starting_pitchers", "Starting-Pitcher Archetypes",
     "trailing EW first-6-innings runs-allowed x prior-start depth",
     "_mlb_sp_entities", _cluster_mlb_sp,
     [("form_ra", "EW first-6 RA"), ("starts", "prior starts"),
      ("lhp", "left-handed share")],
     "Buckets each starter's leak-free trailing run-suppression form against its "
     "track-record depth: low RA + deep sample => ace tier; high RA + shallow "
     "sample => raw / volatile tier."),
    ("Soccer", "team_styles", "Team-Style Archetypes",
     "as-of shots-on-target FOR x shots-on-target AGAINST",
     "_soccer_team_entities", _cluster_soccer_team,
     [("attack", "SoT-for as-of"), ("concede", "SoT-against as-of")],
     "Buckets each team's leak-free trailing attack (SoT created) against its "
     "suppression (SoT conceded): high-create / low-concede => high-press "
     "attacker; low-create / high-concede => outshot strugglers."),
]


def _render(sport: str, title: str, dims: str, total: int,
            sigs: List[_SignatureRow], cols: Sequence[Tuple[str, str]],
            mechanism: str) -> str:
    """Render a dense person-free archetype note body."""
    fm = frontmatter({
        "tags": [f"sport/{sport.lower()}", "archetype", "computed", "honest"],
        "generated": time.strftime("%Y-%m-%d"),
        "kind": title, "entities_clustered": total, "archetypes": len(sigs),
    })
    head = [disp for _, disp in cols]
    L: List[str] = [
        fm, "", f"# Computed Archetypes — {sport} {title}", "",
        "up:: [[Archetypes/_Computed_Index]] | [[_Index]]", "",
        f"> **Honest framing:** {_HONEST}.  PERSON-FREE: only archetype labels,",
        "> numeric centroids and population shares appear — no entity names.", "",
        "## Method", "",
        f"Deterministic tertile bucketing on **{dims}** over **{total:,}** leak-free "
        "as-of entity profiles.  No randomness; reproducible.", "",
        "## Mechanism", "", mechanism, "",
        "## Archetypes (centroid signatures + share)", "",
        "| Archetype | n | Share | " + " | ".join(head) + " |",
        "|-----------|---|-------|" + "|".join("-" * (len(h) + 2) for h in head) + "|",
    ]
    for label, n, share, centroids in sigs:
        cells = " | ".join(f"{v:.3f}" if v == v else "N/A" for _, v in centroids)
        L.append(f"| {label} | {n:,} | {share * 100:.1f}% | {cells} |")
    L += [
        "", "## Reading the Signature", "",
        "Each row is a CLUSTER CENTROID (mean as-of profile of every entity in that "
        "quantile cell), not any single entity.  Shares sum to the clustered "
        "population.  No entity names are stored.", "", "---", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · {len(sigs)} archetypes · "
        f"{total:,} entities · person-free · no edge claimed*", "",
        f"_PRIVATE research.  {_HONEST}._", "",
    ]
    return "\n".join(L) + "\n"


def _render_index(sport: str, kinds: List[Tuple[str, str, int, int]]) -> str:
    """Per-sport index of the _Computed_ archetype notes."""
    fm = frontmatter({"tags": [f"sport/{sport.lower()}", "archetype", "computed",
                               "index"], "generated": time.strftime("%Y-%m-%d")})
    L = [fm, "", f"# {sport} — Computed Archetype Index", "",
         "up:: [[_Index]]", "", f"> {_HONEST}.  PERSON-FREE.", "",
         "| Kind | Archetypes | Entities |", "|------|-----------|----------|"]
    for fname, title, n_arch, n_ent in kinds:
        L.append(f"| [[Archetypes/{fname}\\|{title}]] | {n_arch} | {n_ent:,} |")
    L += ["", f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · person-free · "
          "no edge claimed*", ""]
    return "\n".join(L) + "\n"


def build_archetypes(vault_organized_dir: Optional[Path] = None) -> List[Path]:
    """Cluster each sport's leak-free as-of profiles into person-free archetype notes.

    Writes ``_Computed_<kind>.md`` + ``_Computed_Index.md`` per sport under
    ``<vault>/<SPORT>/Archetypes/``; absent corpora skip honestly.  Returns the
    written paths.  Deterministic; person-free; no edge claimed.
    """
    if vault_organized_dir is None:
        vault_organized_dir = Path(__file__).resolve().parents[2] / "vault" / "_Organized"
    root = Path(vault_organized_dir)
    written: List[Path] = []
    by_sport: Dict[str, List[Tuple[str, str, int, int]]] = {}

    for sport, kind_id, title, dims, ent_name, cl_fn, cols, mech in _KINDS:
        rows = globals()[ent_name]()  # resolve by name -> stays monkeypatch-able
        if not rows:
            continue
        total, sigs = _signatures(cl_fn(rows), cols)
        body = _render(sport, title, dims, total, sigs, cols, mech)
        fname = f"_Computed_{kind_id}"
        out = root / sport / "Archetypes" / f"{fname}.md"
        written.append(write_note(out, body))
        by_sport.setdefault(sport, []).append((fname, title, len(sigs), total))

    for sport, kinds in by_sport.items():
        idx = root / sport / "Archetypes" / "_Computed_Index.md"
        written.append(write_note(idx, _render_index(sport, kinds)))
    return written


if __name__ == "__main__":
    import sys
    for _p in build_archetypes(Path(sys.argv[1]) if len(sys.argv) > 1 else None):
        print(f"Written: {_p}")
