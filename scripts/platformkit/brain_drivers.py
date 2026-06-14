"""brain_drivers.py — per-sport "WHAT WINS & WHY" intelligence from post-mortems.

Turns each sport's per-game POST-MORTEM parquet (a DESCRIPTIVE/REALIZED record of
*why* each game went the way it did) into a DENSE, ORGANIZED, PERSON-FREE driver
taxonomy under ``vault/_Organized/<SPORT>/``:

    _WhatWins.md         -> ranked "what produces wins in <sport> and why" table
                            (empirical frequency + factor magnitude + mechanism +
                             the leak-free as-of signal each driver motivates)
    Drivers/<driver>.md  -> one dense note per top driver (a handful, not per-game)

HONEST + LEAK framing (binding): the post-mortems are DESCRIPTIVE (realized
outcomes), so this is AGGREGATE KNOWLEDGE of *what tends to decide games* — it is
NOT a per-game signal and feeds no model. Intelligence / calibration only; no edge
is claimed; markets are efficient. Every rendered file carries the honest banner.

Heavy pandas import is LAZY (inside ``build_drivers``); tests inject synthetic
post-mortem DataFrames. Missing parquet -> that sport is skipped honestly.
CLI: ``python -m scripts.platformkit.brain_drivers [<organized_root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Intelligence / calibration only, NOT a market edge; no edge claimed.** "
           "Markets are efficient. These post-mortems are DESCRIPTIVE (realized "
           "outcomes): this is AGGREGATE knowledge of *what tends to decide games*, "
           "NOT a per-game signal — it feeds no model and is not bettable.")

_MAX_DRIVER_NOTES = 6  # keep the Drivers/ folder small + dense

# Per-sport config: parquet path (relative), display name, the factor/shape column
# whose mean |value| we report as the driver MAGNITUDE, and a per-driver
# (mechanism, leak-free as-of signal it motivates) lookup. Mechanism is 1-2 dense
# sentences; the as-of note keeps the leak-free companion explicit.
_SPORTS: Dict[str, Dict] = {
    "NBA": {
        "parquet": "data/domains/basketball_nba/postmortem.parquet",
        "mag_col": "margin", "mag_label": "mean |margin| (pts)",
        "drivers": {
            "SHOOTING": ("eFG differential is the dominant Four-Factor swing — the team that "
                         "shoots more efficiently (incl. the 3pt premium) wins most games.",
                         "as-of rolling eFG / shot-quality priors (no realized eFG)."),
            "REBOUNDING": ("Offensive-rebound share converts misses into extra possessions; the "
                           "glass decides games where shooting is close.",
                           "as-of OREB% / lineup size & crash-rate priors."),
            "TURNOVERS": ("A turnover-rate edge denies the opponent shot attempts and fuels "
                          "transition; live-ball giveaways swing close games.",
                          "as-of TOV-rate / ball-handler & pressure priors."),
            "FREE_THROWS": ("A free-throw-rate edge is free points and foul-trouble leverage; "
                            "the smallest of the four factors but real at the margin.",
                            "as-of FT-rate / drive-rate & officiating-environment priors."),
            "BALANCED": ("No single factor dominates (top < 35% of swing): the result is a "
                         "broad, multi-factor outcome rather than one lever.",
                         "as-of full Four-Factor vector (no single dominant prior)."),
        },
    },
    "MLB": {
        "parquet": "data/domains/mlb/postmortem.parquet",
        "mag_col": "margin", "mag_label": "mean |margin| (runs)",
        "drivers": {
            "BIG_INNING": ("One crooked inning (>=50% of a team's runs) decides most games — "
                           "run-scoring clusters; offense is bursty, not linear.",
                           "as-of lineup OBP/SLG & sequencing-variance priors."),
            "BLOWOUT": ("A >=7-run margin: one side's pitching collapsed or its offense ran away "
                        "early; low-information about a close-game edge.",
                        "as-of starter/bullpen quality gap priors."),
            "SP_DUEL": ("Low total (<=4) and tight margin (<=2): starting pitching dominates and "
                        "suppresses scoring on both sides.",
                        "as-of SP form / park-suppression & K-rate priors."),
            "ROUTINE": ("No special structure — runs spread evenly with no big inning, duel, or "
                        "late swing; the base-rate game shape.",
                        "as-of team run-environment priors."),
            "BULLPEN_SWING": ("A late-innings (7-9) run gap >=3 flips the game — relief quality "
                              "and leverage usage decide it after the starters exit.",
                              "as-of bullpen ERA / high-leverage usage priors."),
            "LATE_COMEBACK": ("Winner trailed through 6 then won — late offense overcomes an early "
                              "deficit; high-variance, low predictability.",
                              "as-of late-inning offense & opponent-pen fatigue priors."),
        },
    },
    "Soccer": {
        "parquet": "data/domains/soccer/postmortem.parquet",
        "mag_col": "sot_diff", "mag_label": "mean |SoT diff|",
        "drivers": {
            "ROUTINE": ("Result follows the run of play with no special structure — the "
                        "base-rate match shape and most common outcome.",
                        "as-of team strength / xG-rate priors."),
            "FINISHING_VARIANCE": ("Goals diverge sharply from shots-on-target (xG proxy): "
                                   "finishing luck/quality, not territory, decided it — noisy.",
                                   "as-of xG-vs-goals over/under-performance priors."),
            "TERRITORIAL_CONTROL": ("The side dominating corners+SoT won — sustained territorial "
                                    "pressure converted to a deserved result.",
                                    "as-of possession / chance-creation rate priors."),
            "RED_CARD_SWING": ("A dismissal tilted the match — the man-up side won or drew; "
                               "discipline is a structural, high-impact swing.",
                               "as-of foul/card-propensity & referee-strictness priors."),
            "HT_COLLAPSE": ("A half-time leader failed to win — second-half regression or game "
                            "management let the result slip.",
                            "as-of in-game-state & closing-strength priors."),
            "DOMINANT_BUT_DREW": ("A clear SoT edge yielded only a draw — chances created but "
                                  "not converted; finishing-tail risk realized.",
                                  "as-of chance-quality vs conversion priors."),
            "HT_COMEBACK": ("A side behind at the half won at full time — in-match momentum / "
                            "substitution impact overturned the deficit.",
                            "as-of second-half scoring & bench-impact priors."),
        },
    },
    "Tennis": {
        "parquet": "data/domains/tennis/postmortem.parquet",
        "mag_col": "n_breaks", "mag_label": "mean breaks of serve",
        "drivers": {
            "BLOWOUT": ("Straight sets with >=4 breaks — a clear level gap; serve dominance and "
                        "return pressure produced a one-sided result.",
                        "as-of Elo / surface-rating gap priors."),
            "BP_CONVERSION_EDGE": ("A >=20pt break-point conversion gap decided it — clutch on the "
                                   "biggest points, not raw serve, won the match.",
                                   "as-of historical BP-save/convert rate priors."),
            "BROKE_LATE": ("One tiebreak plus a non-straight result — a single late break or "
                           "tiebreak swung an otherwise even match.",
                           "as-of tiebreak win-rate & late-set stamina priors."),
            "ROUTINE": ("No standout structure — serve-and-hold tennis with the better player "
                        "edging it; the base-rate match shape.",
                        "as-of player-strength / form priors."),
            "THREE_SET_GRIND": ("A full-distance grind — fitness, depth, and adjustment over "
                                "three sets decided a close contest.",
                                "as-of stamina / best-of-3 deciding-set priors."),
            "TIEBREAK_SWING": ("Two-plus tiebreaks — razor margins on serve; a few points in "
                               "breakers, not sustained dominance, decided it.",
                               "as-of tiebreak record & serve-hold priors."),
            "SURFACE_MISMATCH": ("The ranking favorite lost on clay/grass — surface specialization "
                                 "overrode the ranking gap.",
                                 "as-of surface-specific rating priors."),
            "RETIREMENT": ("Match ended in retirement/walkover — outcome is censored by injury, "
                           "carrying little tactical information.",
                           "as-of injury / recent-load flags (treat as noise)."),
            "SERVE_HELD_THROUGHOUT": ("Both players held serve almost throughout (<=1 break) — a "
                                      "serve-dominated, low-break match decided on tiny margins.",
                                      "as-of serve-hold% & ace-rate priors."),
        },
    },
}


def _slug(label: str) -> str:
    return label.lower().replace(" ", "_")


def _aggregate(df, cfg: Dict) -> List[Dict]:
    """Return ranked driver rows: label, n, pct, magnitude, mechanism, as_of."""
    total = int(len(df))
    counts = df["decided_by"].value_counts()
    mag_col = cfg["mag_col"]
    rows: List[Dict] = []
    for label, n in counts.items():
        n = int(n)
        mag = None
        if mag_col in df.columns:
            sub = df.loc[df["decided_by"] == label, mag_col]
            sub = sub.dropna().abs()
            if len(sub):
                mag = round(float(sub.mean()), 3)
        mech, as_of = cfg["drivers"].get(
            str(label), ("Empirical decided-by category from the post-mortems.",
                         "as-of leak-free companion priors."))
        rows.append({"label": str(label), "n": n,
                     "pct": round(100.0 * n / max(total, 1), 1),
                     "magnitude": mag, "mechanism": mech, "as_of": as_of})
    return rows


def _render_whatwins(sport: str, rows: List[Dict], cfg: Dict, total: int) -> str:
    lines = [
        f"---\ntags: [organized, {sport.lower()}, intelligence, what-wins, person-free]\n---",
        f"# {sport} — What Wins & Why (driver taxonomy)\n",
        _BANNER + "\n",
        f"Ranked decomposition of **what tends to decide {sport} games**, aggregated over "
        f"**{total:,}** per-game post-mortems. Each driver shows its empirical frequency, a "
        f"factor magnitude, the mechanism, and the leak-free *as-of* signal it MOTIVATES "
        f"(the realized post-mortem column itself is descriptive and must not be used as a feature).\n",
        f"| # | Driver | Freq | Share | {cfg['mag_label']} | Mechanism | Motivates (leak-free as-of) |",
        "|---|--------|-----:|------:|------:|-----------|------------------------------|",
    ]
    for i, r in enumerate(rows, 1):
        mag = "n/a" if r["magnitude"] is None else f"{r['magnitude']:g}"
        lines.append(
            f"| {i} | [[{_slug(r['label'])}\\|{r['label']}]] | {r['n']:,} | {r['pct']:g}% | "
            f"{mag} | {r['mechanism']} | {r['as_of']} |")
    lines += [
        "",
        "## Reading this honestly",
        "- **Descriptive, not predictive.** Frequencies/magnitudes describe REALIZED games; "
        "they are aggregate scouting knowledge, not a per-game edge.",
        "- **As-of column is the bridge.** Each driver names the leak-free signal a future model "
        "could use; only those (never the realized post-mortem field) may feed a model.",
        "- **Calibration is not edge.** Knowing what decides games improves understanding, not "
        "a market price. No edge is claimed.",
    ]
    return "\n".join(lines) + "\n"


def _render_driver(sport: str, r: Dict, rank: int, total: int) -> str:
    mag = "n/a" if r["magnitude"] is None else f"{r['magnitude']:g}"
    return "\n".join([
        f"---\ntags: [organized, {sport.lower()}, driver, person-free]\n---",
        f"# {sport} Driver — {r['label']}\n",
        _BANNER + "\n",
        f"**Rank:** #{rank} of the {sport} win drivers · **Frequency:** {r['n']:,} games "
        f"({r['pct']:g}% of {total:,}) · **Magnitude:** {mag}\n",
        "## Mechanism",
        r["mechanism"], "",
        "## Leak-free signal it motivates",
        f"{r['as_of']} The realized post-mortem field for this driver is DESCRIPTIVE and must "
        "not be used as a model feature; only the as-of companion may be.",
        "",
        "## Links",
        f"- [[_WhatWins|{sport} What Wins & Why]]",
    ]) + "\n"


def build_drivers(injected: Optional[Dict] = None,
                  organized_root: Optional[Path] = None,
                  write: bool = True) -> Dict:
    """Build per-sport driver taxonomies from the post-mortems.

    Parameters
    ----------
    injected : optional {sport: DataFrame} of synthetic post-mortems (tests).
    organized_root : output root (default vault/_Organized).
    write : write the rendered .md files when True.
    """
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    report: Dict[str, Dict] = {}
    for sport, cfg in _SPORTS.items():
        if injected is not None and sport in injected:
            df = injected[sport]
        elif injected is not None:
            continue  # hermetic: only the injected sports
        else:
            import pandas as pd  # noqa: PLC0415 — heavy import stays lazy
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
        driver_md = {r["label"]: _render_driver(sport, r, i + 1, total)
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
