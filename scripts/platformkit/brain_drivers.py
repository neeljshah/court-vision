"""brain_drivers.py — per-sport "WHAT WINS & WHY" intelligence from post-mortems.

Ranked ``_WhatWins.md`` + dense ``Drivers/<driver>.md`` notes with [[wikilinks]] to
sibling nodes under ``vault/_Organized/<SPORT>/``. Post-mortems are DESCRIPTIVE
realized outcomes — aggregate knowledge, NOT a per-game signal, no edge claimed.
Heavy pandas is LAZY; tests inject synthetic frames.
CLI: ``python -m scripts.platformkit.brain_drivers [<organized_root>] [--json]``
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Intelligence / calibration only, NOT a market edge; no edge claimed.** "
           "Markets are efficient. Post-mortems are DESCRIPTIVE realized outcomes: "
           "AGGREGATE knowledge of what tends to decide games, NOT a per-game signal.")
_MAX_DRIVER_NOTES = 6
# Each driver: (mechanism, as_of_signal, why_it_wins_1line, model_implication_1line)
# All person-free; no edge tokens (roi / beats market / guaranteed / proven edge).
_NBA_D = {
    "SHOOTING":    ("eFG differential is the dominant Four-Factor swing — efficient shooting wins most games.",
                    "as-of rolling eFG / shot-quality priors (no realized eFG).",
                    "A 2-3% eFG gap compounds to ~3-5 pts/game via the possession-value equation.",
                    "Calibrate shot-distribution priors with as-of eFG; never feed realized eFG as a feature."),
    "REBOUNDING":  ("Offensive-rebound share converts misses into extra possessions; the glass decides close games.",
                    "as-of OREB% / lineup size & crash-rate priors.",
                    "Each offensive rebound is worth ~1 pt; a 5% OREB% gap adds ~1-2 extra attempts/game.",
                    "Weight lineup size and crash-rate in the possession sim; calibrate OREB% per lineup."),
    "TURNOVERS":   ("A turnover-rate edge denies shot attempts and fuels transition; live-ball giveaways swing games.",
                    "as-of TOV-rate / ball-handler & pressure priors.",
                    "Each turnover swings ~2 pts (1 pt lost + ~1.2 pt transition chance); structurally driven by ball-handler quality.",
                    "Model TOV-rate via ball-handler usage and defensive-pressure priors; calibrate against as-of TOV%."),
    "FREE_THROWS": ("A free-throw-rate differential is free points plus foul-trouble leverage; smallest factor, real at the margin.",
                    "as-of FT-rate / drive-rate & officiating-environment priors.",
                    "High-drive lineups earn ~0.75 pts/FTA with zero opponent possessions; foul trouble compounds via rotation disruption.",
                    "Include FT-rate and foul-trouble priors as structural modifiers; calibrate against as-of drive-rate."),
    "BALANCED":    ("No single factor exceeds ~35% of the swing: broad multi-factor outcome rather than one lever.",
                    "as-of full Four-Factor vector (no single dominant prior).",
                    "When no factor dominates, outcome variance is highest; joint Four-Factor distribution is the calibration lever.",
                    "Prioritize full Four-Factor vector priors; avoid single-factor reduction for balanced game shapes."),
}
_MLB_D = {
    "BIG_INNING":    ("One crooked inning (>=50% of runs) decides most games — run-scoring clusters; offense is bursty.",
                      "as-of lineup OBP/SLG & sequencing-variance priors.",
                      "Walks and XBH compound within an inning at far higher rates than across innings — over-dispersed vs Poisson.",
                      "Use Negative Binomial run-scoring on OBP/SLG sequencing priors; Poisson under-estimates big-inning tail."),
    "BLOWOUT":       ("A >=7-run margin: pitching collapsed or offense ran away early; low-information about a close-game prediction.",
                      "as-of starter/bullpen quality gap priors.",
                      "Blowout structure reflects a large quality gap that triggers early SP exit and burns the relief ladder.",
                      "Flag blowout games in calibration; down-weight them in close-game margin models."),
    "SP_DUEL":       ("Low total (<=4) and tight margin (<=2): starting pitching dominates and suppresses scoring on both sides.",
                      "as-of SP form / park-suppression & K-rate priors.",
                      "High K-rate keeps sequencing variance low; suppression is structural (SP quality, park factor).",
                      "Condition run model on SP K-rate and park priors; NegBinom dispersion should compress for duel games."),
    "ROUTINE":       ("No special structure — runs spread evenly; the base-rate game shape.",
                      "as-of team run-environment priors.",
                      "Routine games are the closest realization of the Poisson baseline: moderate sequencing, no compounding rally.",
                      "Routine games calibrate the base-rate run-environment prior; all other shapes are structural adjustments."),
    "BULLPEN_SWING": ("A late-innings (7-9) run gap >=3 flips the game — relief quality and leverage usage decide it.",
                      "as-of bullpen ERA / high-leverage usage priors.",
                      "Bullpen leverage compounds: high-stakes situations match higher-quality arms; a depth gap becomes decisive.",
                      "Model bullpen as a depth-weighted leverage distribution; calibrate late-inning probability against as-of usage."),
    "LATE_COMEBACK": ("Winner trailed through 6 then won — late offense overcomes an early deficit; high-variance.",
                      "as-of late-inning offense & opponent-pen fatigue priors.",
                      "The structural driver is pen-fatigue and platoon exposure, not raw talent; individual instances are noisy.",
                      "Model late-comeback via pen-fatigue and platoon-exposure priors; not reliable at game level."),
}
_SOC_D = {
    "ROUTINE":             ("Result follows the run of play — the base-rate match shape.",
                            "as-of team strength / xG-rate priors.",
                            "Routine matches are the closest realization of the xG model expectation without structural distortion.",
                            "Calibrate the xG-to-result model on routine matches as the base prior."),
    "FINISHING_VARIANCE":  ("Goals diverge from shots-on-target: finishing luck, not territory, decided the result — high noise.",
                            "as-of xG-vs-goals over/under-performance priors.",
                            "Finishing variance is a Poisson tail that REGRESSES toward xG over multiple matches — an O/U calibration signal.",
                            "Apply finishing-REGRESSION toward xG across multi-match samples; calibrate O/U with shot-quality-weighted xG."),
    "TERRITORIAL_CONTROL": ("The side dominating corners+SoT won — sustained territorial pressure converted to a deserved result.",
                            "as-of possession / chance-creation rate priors.",
                            "Territorial control is structural (pressing, passing efficiency); SoT+corners dominance is more predictive than recent goals.",
                            "Weight territorial control (SoT, corners, xG chain) in team-strength priors; calibrate against chance-creation rates."),
    "RED_CARD_SWING":      ("A dismissal tilted the match — the man-up side won or drew; discipline is a high-impact structural swing.",
                            "as-of foul/card-propensity & referee-strictness priors.",
                            "Numerical advantage converts to ~30-40% more shots while the reduced side compresses defensively.",
                            "Include foul/card-propensity and referee-strictness as structural priors; red-card probability is a calibratable modifier."),
    "HT_COLLAPSE":         ("A half-time leader failed to win — second-half regression or game management let the result slip.",
                            "as-of in-game-state & closing-strength priors.",
                            "Deep-block management invites sustained pressure that elevates opponent xG; closing-strength is the structural driver.",
                            "Model second-half goal probability conditioned on HT state and as-of closing-strength priors."),
    "DOMINANT_BUT_DREW":   ("A clear SoT edge yielded only a draw — chances created but not converted; finishing-tail risk realized.",
                            "as-of chance-quality vs conversion priors.",
                            "Shot volume vs shot quality (xG/shot) divergence is the structural explanation for this outcome.",
                            "Use shot-quality-weighted xG rather than raw SoT; volume and quality are distinct calibration signals."),
    "HT_COMEBACK":         ("A side behind at the half won at full time — substitution impact and opponent fatigue overturned the deficit.",
                            "as-of second-half scoring & bench-impact priors.",
                            "Comebacks are driven by tactical adjustment and opponent fatigue; bench-quality differential is the structural signal.",
                            "Model HT-comeback probability via bench-impact and second-half scoring priors."),
}
_TEN_D = {
    "BLOWOUT":               ("Straight sets with >=4 breaks — a clear level gap; serve dominance produced a one-sided result.",
                              "as-of Elo / surface-rating gap priors.",
                              "A 10% return-point advantage creates ~20-30% more break opportunities per set; surface amplifies the gap.",
                              "Use surface-conditioned Elo as the primary prior; blowout probability calibrates against the Elo gap."),
    "BP_CONVERSION_EDGE":    ("A >=20pt break-point conversion gap decided it — clutch performance on the biggest points won.",
                              "as-of historical BP-save/convert rate priors.",
                              "BP conversion is a partially stable clutch skill distinct from baseline serve capability.",
                              "Include as-of BP-save/convert rate as a structural modifier on serve-hold probabilities."),
    "BROKE_LATE":            ("One tiebreak plus a non-straight result — a single late break swung an otherwise even match.",
                              "as-of tiebreak win-rate & late-set stamina priors.",
                              "Late-set stamina and tiebreak composure are partially stable measurable skills that separate close-tier players.",
                              "Model late-set break probability using tiebreak win-rate and stamina priors."),
    "ROUTINE":               ("No standout structure — serve-and-hold with the stronger player edging it; the base-rate match shape.",
                              "as-of player-strength / form priors.",
                              "Routine matches are the base-rate realization of the Elo model without structural distortion.",
                              "Routine match rates calibrate the baseline Elo-to-win-probability conversion."),
    "THREE_SET_GRIND":       ("A full-distance grind — fitness and tactical adjustment over three sets decided a close contest.",
                              "as-of stamina / best-of-3 deciding-set priors.",
                              "Deciding-set record reflects fitness and mental resilience better than overall win-rate or Elo.",
                              "Condition three-set win probability on as-of stamina and deciding-set record; surface speed modifies."),
    "TIEBREAK_SWING":        ("Two-plus tiebreaks — razor margins on serve; a few points in breakers decided it.",
                              "as-of tiebreak record & serve-hold priors.",
                              "Each tiebreak is a 7-point sequence; tiebreak win-rate captures serve quality and composure simultaneously.",
                              "Use as-of tiebreak win-rate as the primary signal; avoid over-weighting full-match Elo in serve-dominated conditions."),
    "SURFACE_MISMATCH":      ("The ranking favorite lost on clay or grass — surface specialization overrode the ranking gap.",
                              "as-of surface-specific rating priors.",
                              "Surface-specific Elo diverges from overall ranking because physical demands favor different playing styles.",
                              "Weight surface-specific Elo over overall ranking for clay/grass; calibrate surface-adjustment from historical outcomes."),
    "RETIREMENT":            ("Match ended in retirement/walkover — outcome is censored by injury, carrying little tactical information.",
                              "as-of injury / recent-load flags (treat as noise).",
                              "Retirement events are injury-censored and driven by match load, not in-match tactical factors.",
                              "Exclude retirement outcomes from tactical calibration; model injury probability separately."),
    "SERVE_HELD_THROUGHOUT": ("Both players held serve throughout (<=1 break) — a serve-dominated match decided on tiny margins.",
                              "as-of serve-hold% & ace-rate priors.",
                              "Ace-rate and first-serve% become decisive when return quality cannot break through; fast surfaces produce this more.",
                              "Calibrate serve-hold using ace-rate and first-serve% priors stratified by surface."),
}

_ARC_MLB = "[[../Archetypes/_Computed_Index|Pitcher Archetypes]]"
_ARC_SOC = "[[../Archetypes/_Computed_Index|Team Style Archetypes]]"
_SPORTS: Dict[str, Dict] = {
    "NBA":    {"parquet": "data/domains/basketball_nba/postmortem.parquet",
               "mag_col": "margin",    "mag_label": "mean |margin| (pts)",   "archetype_link": None,     "drivers": _NBA_D},
    "MLB":    {"parquet": "data/domains/mlb/postmortem.parquet",
               "mag_col": "margin",    "mag_label": "mean |margin| (runs)",  "archetype_link": _ARC_MLB, "drivers": _MLB_D},
    "Soccer": {"parquet": "data/domains/soccer/postmortem.parquet",
               "mag_col": "sot_diff", "mag_label": "mean |SoT diff|",        "archetype_link": _ARC_SOC, "drivers": _SOC_D},
    "Tennis": {"parquet": "data/domains/tennis/postmortem.parquet",
               "mag_col": "n_breaks", "mag_label": "mean breaks of serve",   "archetype_link": None,     "drivers": _TEN_D},
}


def _slug(label: str) -> str:
    return label.lower().replace(" ", "_")

def _aggregate(df, cfg: Dict) -> List[Dict]:
    """Return ranked driver rows with mechanism, as_of, why, implication."""
    total = int(len(df))
    counts = df["decided_by"].value_counts()
    mag_col = cfg["mag_col"]
    rows: List[Dict] = []
    for label, n in counts.items():
        n = int(n)
        mag = None
        if mag_col in df.columns:
            sub = df.loc[df["decided_by"] == label, mag_col].dropna().abs()
            if len(sub):
                mag = round(float(sub.mean()), 3)
        entry = cfg["drivers"].get(str(label))
        if entry and len(entry) == 4:
            mech, as_of, why, impl = entry
        elif entry and len(entry) == 2:
            mech, as_of, why, impl = entry[0], entry[1], "", ""
        else:
            mech, as_of, why, impl = "Empirical decided-by category.", "as-of priors.", "", ""
        rows.append({"label": str(label), "n": n,
                     "pct": round(100.0 * n / max(total, 1), 1),
                     "magnitude": mag, "mechanism": mech, "as_of": as_of,
                     "why_it_wins": why, "model_implication": impl})
    return rows

def _render_whatwins(sport: str, rows: List[Dict], cfg: Dict, total: int) -> str:
    arch = cfg.get("archetype_link")
    see = [f"[[Mechanisms/_Mechanisms|{sport} Mechanisms]]", f"[[_Index|{sport} Index]]"]
    if arch:
        see.append(arch.replace("../", ""))
    lines = [
        f"---\ntags: [organized, {sport.lower()}, intelligence, what-wins, person-free]\n---",
        f"# {sport} — What Wins & Why (driver taxonomy)\n", _BANNER + "\n",
        f"Ranked decomposition of **what tends to decide {sport} games**, aggregated over "
        f"**{total:,}** per-game post-mortems. Each driver links to its dense note.\n",
        f"| # | Driver | Freq | Share | {cfg['mag_label']} | Mechanism | Motivates (as-of) |",
        "|---|--------|-----:|------:|------:|-----------|-------------------|",
    ]
    for i, r in enumerate(rows, 1):
        mag = "n/a" if r["magnitude"] is None else f"{r['magnitude']:g}"
        lines.append(
            f"| {i} | [[Drivers/{_slug(r['label'])}\\|{r['label']}]] "
            f"| {r['n']:,} | {r['pct']:g}% | {mag} | {r['mechanism']} | {r['as_of']} |")
    lines += [
        "", "## Reading this honestly",
        "- **Descriptive, not predictive.** These are REALIZED games; aggregate scouting knowledge, not a per-game signal.",
        "- **As-of column is the bridge.** Only those leak-free signals may feed a model.",
        "- **Calibration is not edge.** No edge is claimed.",
        "", "## See also", "- " + "\n- ".join(see),
    ]
    return "\n".join(lines) + "\n"

def _render_driver(sport: str, r: Dict, rank: int, total: int,
                   arch_link: Optional[str]) -> str:
    mag = "n/a" if r["magnitude"] is None else f"{r['magnitude']:g}"
    see = [f"[[../_WhatWins|{sport} What Wins & Why]]",
           f"[[../Mechanisms/_Mechanisms|{sport} Mechanisms]]",
           f"[[../_Index|{sport} Index]]"]
    if arch_link:
        see.append(arch_link)
    parts = [
        f"---\ntags: [organized, {sport.lower()}, driver, person-free]\n---",
        f"# {sport} Driver — {r['label']}\n", _BANNER + "\n",
        f"**Rank:** #{rank} · **Frequency:** {r['n']:,} games ({r['pct']:g}% of {total:,})"
        f" · **Magnitude:** {mag}\n",
        "## Mechanism", r["mechanism"], "",
    ]
    if r.get("why_it_wins"):
        parts += ["## Why it wins", r["why_it_wins"], ""]
    parts += ["## Leak-free signal it motivates",
              f"{r['as_of']} The realized post-mortem field is DESCRIPTIVE and must "
              "not be used as a model feature; only the as-of companion may be.", ""]
    if r.get("model_implication"):
        parts += ["## Model implication", r["model_implication"], ""]
    parts += ["## See also", "- " + "\n- ".join(see)]
    return "\n".join(parts) + "\n"

def build_drivers(injected: Optional[Dict] = None,
                  organized_root: Optional[Path] = None,
                  write: bool = True) -> Dict:
    """Build per-sport driver taxonomies. ``injected`` accepts {sport: DataFrame} for tests."""
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    report: Dict[str, Dict] = {}
    for sport, cfg in _SPORTS.items():
        if injected is not None and sport in injected:
            df = injected[sport]
        elif injected is not None:
            continue
        else:
            import pandas as pd  # noqa: PLC0415 — lazy import
            pq = _REPO_ROOT / cfg["parquet"]
            if not pq.exists():
                report[sport] = {"skipped": "missing parquet"}
                continue
            df = pd.read_parquet(pq)
        if "decided_by" not in getattr(df, "columns", []):
            report[sport] = {"skipped": "no decided_by column"}
            continue
        total = int(len(df))
        rows = _aggregate(df, cfg)
        whatwins = _render_whatwins(sport, rows, cfg, total)
        top = rows[:_MAX_DRIVER_NOTES]
        arch_link = cfg.get("archetype_link")
        driver_md = {r["label"]: _render_driver(sport, r, i + 1, total, arch_link)
                     for i, r in enumerate(top)}
        report[sport] = {"n_games": total, "n_drivers": len(rows),
                         "top": [r["label"] for r in top],
                         "rows": rows, "whatwins_md": whatwins, "driver_md": driver_md}
        if write:
            sdir = root / sport
            (sdir / "Drivers").mkdir(parents=True, exist_ok=True)
            (sdir / "_WhatWins.md").write_text(whatwins, encoding="utf-8")
            for label, md in driver_md.items():
                (sdir / "Drivers" / f"{_slug(label)}.md").write_text(md, encoding="utf-8")
    report["_note"] = ("intelligence/calibration only, not a market edge; descriptive "
                       "post-mortems, not a per-game signal; no edge claimed")
    return report

def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_drivers(organized_root=Path(root_arg) if root_arg else None, write=True)
    if "--json" in argv:
        print(json.dumps({k: (v if not isinstance(v, dict) else
                              {kk: vv for kk, vv in v.items() if not kk.endswith("_md")})
                          for k, v in rep.items()}, indent=2, default=str))
        return 0
    for sport, info in rep.items():
        if sport.startswith("_") or "skipped" in info:
            if isinstance(info, dict) and "skipped" in info:
                print(f"  [{sport:<7}] SKIPPED ({info['skipped']})")
            continue
        print(f"  [{sport:<7}] {info['n_games']:,} games -> {info['n_drivers']} drivers; "
              f"top: {', '.join(info['top'])}")
    print(f"NOTE: {rep['_note']}")
    return 0

if __name__ == "__main__":
    sys.exit(_main())
