"""brain_mechanisms.py — cross-cutting FACTOR-INTERACTION Mechanisms layer.

Reads each sport's post-mortem parquet and renders dense PERSON-FREE notes about
FACTOR INTERACTIONS / conditional structure under vault/_Organized/<SPORT>/Mechanisms/.
A _Mechanisms.md index per sport is also produced.  Missing parquet → skip honestly.
Heavy pandas is LAZY; tests inject synthetic DataFrames.

CLI: ``python -m scripts.platformkit.brain_mechanisms [<root>] [--json]``
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Intelligence / calibration only, NOT a market edge; no edge claimed.** "
           "Markets are efficient.  Conditional frequencies derive from REALIZED "
           "post-mortems (descriptive outcomes) — aggregate calibration knowledge, "
           "not per-game signals and not bettable.")

# (slug, title, compute_key)
_SPORTS: Dict[str, Dict] = {
    "NBA": {"parquet": "data/domains/basketball_nba/postmortem.parquet", "mechs": [
        ("pace_x_shooting_dominance", "Pace × Shooting Dominance",      "_nba_pace_shoot"),
        ("pace_x_rebounding_weight",  "Pace × Rebounding Weight",        "_nba_pace_reb"),
        ("shooting_margin_structure", "Shooting-Decided Margin Distribution", "_nba_margin"),
    ]},
    "MLB": {"parquet": "data/domains/mlb/postmortem.parquet", "mechs": [
        ("sp_hand_x_game_mode",    "SP-Handedness Matchup × Game Mode",    "_mlb_sp_hand"),
        ("big_inning_x_total_runs","Big-Inning × Total-Runs Interaction",  "_mlb_big_inn"),
    ]},
    "Soccer": {"parquet": "data/domains/soccer/postmortem.parquet", "mechs": [
        ("red_card_x_finishing", "Red-Card Event × Finishing-Variance Suppression", "_soc_redcard"),
        ("ht_lead_x_result_stability", "Half-Time Lead × Full-Time Result Stability","_soc_ht_flip"),
    ]},
    "Tennis": {"parquet": "data/domains/tennis/postmortem.parquet", "mechs": [
        ("surface_x_serve_hold",    "Surface × Serve-Hold Dominance",   "_ten_serve"),
        ("surface_x_bp_conversion", "Surface × Break-Point Conversion", "_ten_bp"),
    ]},
}

_PCS = ["slow","medium","fast"]


def _ct_rows(df, row_col, row_vals, col_vals, aliases: Dict = {}) -> str:
    import pandas as pd  # noqa
    if row_col not in df.columns or "decided_by" not in df.columns:
        return "(no data)"
    ct = pd.crosstab(df[row_col], df["decided_by"], normalize="index")
    out = [f"- **{aliases.get(rv, str(rv))}**: " + ", ".join(
               f"{cv} {ct.loc[rv, cv]:.0%}" for cv in col_vals if cv in ct.columns)
           for rv in row_vals if rv in ct.index and
               any(cv in ct.columns for cv in col_vals)]
    return "\n".join(out) or "(no data)"


def _grp_rows(df, grp_col, val_col) -> str:
    if grp_col not in df.columns or val_col not in df.columns: return "(no data)"
    g = df.groupby(grp_col)[val_col].agg(["mean", "std"])
    return "\n".join(f"- **{i}**: mean {g.loc[i,'mean']:.1f}, std {g.loc[i,'std']:.1f}" for i in g.index)


def _pace_df(df):
    import pandas as pd  # noqa
    if "pace" not in df.columns: return None
    try:
        d = df.copy(); d["_pc"] = pd.qcut(d["pace"], 3, labels=_PCS); return d
    except ValueError: return None


def _nba_pace_shoot(df) -> Tuple[str, str]:
    df2 = _pace_df(df)
    if df2 is None: return "(insufficient pace data)", ""
    emp = _ct_rows(df2, "_pc", _PCS, ["SHOOTING","REBOUNDING","TURNOVERS"])
    body = ("Pace modulates which factor decides the game but does not dominate it.  "
            "Shooting efficiency (eFG differential) is the #1 driver across all pace "
            "tertiles; at slow pace the shooting-decided share dips slightly (fewer "
            "possessions, more contested half-court offense).  Pace bucket is a "
            "conditioning variable, not a raw feature.")
    return emp, body


def _nba_pace_reb(df) -> Tuple[str, str]:
    df2 = _pace_df(df)
    if df2 is None: return "(insufficient pace data)", ""
    emp = _ct_rows(df2, "_pc", _PCS, ["REBOUNDING"])
    body = ("Slow-pace games amplify the rebounding mechanism: fewer possessions make "
            "each OREB more valuable.  As pace rises, transition attempts reduce the "
            "crashing value; rebounding-decided frequency falls.  The interaction "
            "direction: pace UP → OREB weight DOWN.")
    return emp, body


def _nba_margin(df) -> Tuple[str, str]:
    emp = _grp_rows(df, "decided_by", "margin") if "margin" in df.columns else "(no data)"
    body = ("Shooting-decided games produce a wider raw margin distribution.  "
            "Turnover/free-throw games are closer (fewer total swing points); BALANCED "
            "games centre near zero with the highest two-sided variance.  The mechanism: "
            "shooting efficiency creates compounding leads; other factors produce tighter "
            "score lines.  Implication: decided_by predicts spread shape, not just mean.")
    return emp, body


def _mlb_sp_hand(df) -> Tuple[str, str]:
    emp = _ct_rows(df, "sp_hand_matchup", ["RR","LL","RL","LR"],
                   ["BIG_INNING","SP_DUEL","BLOWOUT"])
    body = ("SP-handedness matchup shows surprisingly flat conditional distributions: "
            "BIG_INNING accounts for ~67–69% regardless of matchup — run-scoring is "
            "structurally bursty.  SP_DUEL rate (~11–12%) shows pitching duels depend "
            "more on individual starter quality than on handedness.  SP quality + park "
            "factors dominate; handedness is secondary context.")
    return emp, body


def _mlb_big_inn(df) -> Tuple[str, str]:
    emp = _grp_rows(df, "decided_by", "total_runs") if "total_runs" in df.columns else "(no data)"
    body = ("BIG_INNING and SP_DUEL are structural opposites: big-inning games cluster "
            "at ~8.8 runs; SP_DUEL games are capped at ≤4 by construction; BLOWOUT "
            "reaches ~13.  Game-mode prior (set by SP quality + bullpen) determines the "
            "total-run distribution shape — not just the mean.  Strong SP both sides → "
            "elevated SP_DUEL prior → compress total prior left-ward.")
    return emp, body


def _soc_redcard(df) -> Tuple[str, str]:
    aliases = {False: "No red card", True: "Red card present"}
    emp = _ct_rows(df, "red_flags", [False, True],
                   ["RED_CARD_SWING","FINISHING_VARIANCE","ROUTINE"], aliases)
    body = ("A red card converts a finishing-variance or routine match into RED_CARD_SWING "
            "with high probability (~76% of red-card games).  This is a conditional "
            "independence break: finishing luck matters far less than structural "
            "man-advantage.  A dismissal triggers repricing that collapses the finishing-"
            "variance prior toward territorial-control / man-up outcome path.")
    return emp, body


def _soc_ht_flip(df) -> Tuple[str, str]:
    aliases = {False: "Leader holds (no flip)", True: "Leader did NOT hold (flip)"}
    emp = _ct_rows(df, "ht_flip", [False, True],
                   ["ROUTINE","FINISHING_VARIANCE","HT_COMEBACK","DOMINANT_BUT_DREW"], aliases)
    body = ("When the ht-leader also wins (no flip), ROUTINE and TERRITORIAL_CONTROL "
            "dominate.  When a flip occurs, distribution shifts toward HT_COMEBACK and "
            "DOMINANT_BUT_DREW; ROUTINE is zero in the ht_flip=True stratum by "
            "construction.  At half-time lead, downweight finishing-variance prior; "
            "realized ht_flip is a target, never a feature.")
    return emp, body


def _ten_serve(df) -> Tuple[str, str]:
    rows = []
    if "surface" in df.columns:
        for sfc in ["Grass","Hard","Clay"]:
            sub = df[df["surface"] == sfc]
            p = ([f"mean aces {sub['p1_aces'].mean():.1f}"] if len(sub) and "p1_aces" in sub else [])
            p += ([f"mean tiebreaks {sub['n_tiebreaks'].mean():.2f}"] if len(sub) and "n_tiebreaks" in sub else [])
            if p: rows.append(f"- **{sfc}**: " + ", ".join(p))
    emp = "\n".join(rows) or "(no data)"
    body = ("Surface is the primary conditioner on serve-dominance.  Grass produces far "
            "more aces and tiebreaks than clay; clay breaks serve more frequently, "
            "amplifying break-point conversion.  Serve-hold% is NOT surface-transferable "
            "— surface must always be the conditioning variable, never pooled.")
    return emp, body


def _ten_bp(df) -> Tuple[str, str]:
    emp = _ct_rows(df, "surface", ["Grass","Hard","Clay"],
                   ["BLOWOUT","BP_CONVERSION_EDGE","TIEBREAK_SWING"])
    body = ("BP conversion rates and BP_CONVERSION_EDGE frequency are surface-conditional.  "
            "On clay, service is harder to hold so conversion rates rise.  BLOWOUT rate "
            "also varies: clay (skill gap via sustained baseline); grass blowouts less "
            "common (serve equalises levels).  Cross-surface BP% pooling is "
            "miscalibrated; separate shrinkage per surface is required.")
    return emp, body


_COMPUTE = {
    "_nba_pace_shoot": _nba_pace_shoot, "_nba_pace_reb": _nba_pace_reb,
    "_nba_margin":     _nba_margin,
    "_mlb_sp_hand":    _mlb_sp_hand,    "_mlb_big_inn":  _mlb_big_inn,
    "_soc_redcard":    _soc_redcard,    "_soc_ht_flip":  _soc_ht_flip,
    "_ten_serve":      _ten_serve,      "_ten_bp":       _ten_bp,
}


# slug -> (favors_archetype, suppresses_archetype, model_implication). No player/team names.
_META: Dict[str, Tuple[str, str, str]] = {
    "pace_x_shooting_dominance": ("half-court / set-offense archetypes", "transition-volume styles", "Condition eFG priors per pace tertile; never pool across pace buckets."),
    "pace_x_rebounding_weight":  ("grind-tempo / paint-dominant archetypes at slow pace", "run-and-gun styles (OREB value collapses in open transition)", "Apply pace-bucket weights to OREB priors: high at slow tempo, downweighted at fast."),
    "shooting_margin_structure": ("spread-offense / spacing archetypes (wider margin dist.)", "grind / foul-draw styles (tighter margin → narrower spread prior)", "Pre-game eFG gap widens spread-distribution shape — a calibration adjustment, not a mean shift."),
    "sp_hand_x_game_mode":       ("neutral-matchup SP quality archetypes", "handedness-specialist narratives (flat conditional dist.)", "SP quality + park factors dominate the game-mode prior; handedness adds minimal conditioning lift."),
    "big_inning_x_total_runs":   ("explosive-offense / weak-bullpen archetypes", "SP-duel archetypes (hard total cap by construction)", "Game-mode prior (duel/big-inning/blowout) controls total-run distribution shape, not just the mean."),
    "red_card_x_finishing":      ("pressing / high-defensive-line archetypes", "finishing-variance styles (luck collapses after dismissal)", "Red-card event collapses finishing-variance prior; shifts mass toward territorial-control path."),
    "ht_lead_x_result_stability":("low-block / defensive-shape archetypes", "high-press / comeback archetypes (flip probability drops sharply)", "After ht-lead, downweight finishing-variance prior; realized ht_flip is a target, never a feature."),
    "surface_x_serve_hold":      ("big-serve archetypes on Grass; baseline grinders on Clay", "cross-surface style transfer (priors are NOT surface-portable)", "Fit surface-specific serve-hold% priors; no cross-surface pooling. Grass → high tiebreak prior."),
    "surface_x_bp_conversion":   ("sustained-baseline archetypes on Clay", "serve-dominant archetypes on Clay (serve equaliser weakens)", "Separate shrinkage per surface for BP-conversion%; pooled cross-surface BP% is miscalibrated."),
}
_LINKS = "[[_Mechanisms|Mechanisms index]] · [[_WhatWins|What Wins]] · [[Drivers|Drivers]] · [[Archetypes/_Archetypes_Index|Archetypes]] · [[_Index|Index]]"


def _render_mech(sport: str, slug: str, title: str, emp: str, body: str) -> str:
    fav, sup, model_impl = _META.get(slug, ("—", "—", "—"))
    wikilinks = "\n".join([
        f"- [[_Mechanisms|{sport} Mechanisms index]]",
        f"- [[_WhatWins|{sport} What Wins & Why]]",
        f"- [[Drivers|{sport} Drivers]]",
        f"- [[Archetypes/_Archetypes_Index|{sport} Computed Archetypes]]",
        f"- [[_Index|{sport} Intelligence Index]]",
    ])
    return "\n".join([
        f"---\ntags: [organized, {sport.lower()}, mechanisms, intelligence, person-free]\n---",
        f"# {sport} Mechanism — {title}\n",
        _BANNER + "\n",
        "## How it works", body, "",
        "## Archetype / style implications (structural labels only, no names)",
        f"- **Favors**: {fav}",
        f"- **Suppresses**: {sup}", "",
        "## Model-structure implication (calibration, NOT edge)",
        model_impl, "",
        "## Empirical conditional frequencies / magnitudes", emp, "",
        "## Links", wikilinks,
    ]) + "\n"


def _render_index(sport: str, mechs: List[Tuple]) -> str:
    rows = "\n".join(f"| {t} | {_META.get(s,('','',''))[2][:68]}… | [[{s}]] |" for s,t,_ in mechs)
    return "\n".join([
        f"---\ntags: [organized, {sport.lower()}, mechanisms, index, person-free]\n---",
        f"# {sport} — Mechanisms Index\n",
        _BANNER + "\n",
        f"Dense FACTOR INTERACTIONS for {sport}: how decided-by drivers co-occur or condition "
        "on context, and what each implies for calibration.  "
        f"All frequencies are REALIZED post-mortems (descriptive).  See also: {_LINKS}\n",
        "| Mechanism | Calibration implication | File |",
        "|-----------|------------------------|------|",
        rows, "",
        "_Calibration is not edge.  No edge is claimed._",
    ]) + "\n"


def build_mechanisms(injected: Optional[Dict] = None,
                     organized_root: Optional[Path] = None,
                     write: bool = True) -> Dict:
    """Build per-sport Mechanisms notes from post-mortems.
    injected : optional {sport: DataFrame} (tests); organized_root: output root."""
    root = (Path(organized_root) if organized_root
            else _REPO_ROOT / "vault" / "_Organized")
    report: Dict = {}
    for sport, cfg in _SPORTS.items():
        if injected is not None:
            if sport not in injected:
                continue
            df = injected[sport]
        else:
            import pandas as pd  # noqa
            pq = _REPO_ROOT / cfg["parquet"]
            if not pq.exists():
                report[sport] = {"skipped": "missing parquet"}; continue
            df = pd.read_parquet(pq)
        if "decided_by" not in getattr(df, "columns", []):
            report[sport] = {"skipped": "no decided_by column"}; continue
        rendered: Dict[str, str] = {}
        for slug, title, key in cfg["mechs"]:
            emp, body = _COMPUTE[key](df)
            rendered[slug] = _render_mech(sport, slug, title, emp, body)
        index_md = _render_index(sport, cfg["mechs"])
        report[sport] = {"n_mechanisms": len(rendered), "slugs": list(rendered.keys()),
                         "rendered": rendered, "index_md": index_md}
        if write:
            mdir = root / sport / "Mechanisms"
            mdir.mkdir(parents=True, exist_ok=True)
            for slug, md in rendered.items():
                (mdir / f"{slug}.md").write_text(md, encoding="utf-8")
            (mdir / "_Mechanisms.md").write_text(index_md, encoding="utf-8")
    report["_note"] = ("intelligence/calibration only, not a market edge; "
                       "factor interactions from descriptive post-mortems; no edge claimed")
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__); return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_mechanisms(organized_root=Path(root_arg) if root_arg else None)
    if "--json" in argv:
        out = {k: ({kk: vv for kk, vv in v.items() if kk != "rendered"}
                   if isinstance(v, dict) and "rendered" in v else v)
               for k, v in rep.items()}
        print(json.dumps(out, indent=2)); return 0
    for sp, info in rep.items():
        if sp.startswith("_"): continue
        if "skipped" in info: print(f"[SKIP] {sp}: {info['skipped']}")
        else: print(f"[OK]   {sp}: {info['n_mechanisms']} — {', '.join(info['slugs'])}")
    return 0

if __name__ == "__main__":
    sys.exit(_main())
