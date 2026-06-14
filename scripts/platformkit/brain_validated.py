"""brain_validated.py — provenance-tagged VALIDATED LEAK-FREE improvements per sport.

Renders, per sport, vault/_Organized/<SPORT>/_Validated_Improvements.md + a top-level
_Index/_Validated_Improvements.md listing the VALIDATED leak-free model improvements
as a table.

DATA IS STATIC + PROVENANCE-TAGGED: these are historical validated results, each tagged
with its wave + commit + module path.  Artifacts say 'validated at the cited commit --
re-verify via the module CLI', NOT presented as a live re-derivation.

KEY FRAMING: distribution-shape/structure fixes won; mean-shift priors got absorbed.
Calibration/accuracy improvement only, NOT a market edge; no edge claimed.

Tested-but-absorbed nulls are also recorded honestly (absorbed by the rating/engine;
recorded not shipped).

CLI: ``python -m scripts.platformkit.brain_validated [<organized_root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = (
    "> **Calibration / accuracy metric improvement only, NOT a market edge; "
    "no edge claimed.**  Markets are efficient; calibration is not edge.  "
    "All results are validated at the cited commit -- re-verify via the module CLI.  "
    "Distribution-shape/structure fixes won; mean-shift priors got absorbed."
)

# ---------------------------------------------------------------------------
# STATIC PROVENANCE-TAGGED VALIDATED ENTRIES
# Each entry: sport, name, metric_delta, module, wave, commit
# ---------------------------------------------------------------------------
_ENTRIES: List[Dict] = [
    {
        "sport": "Soccer",
        "name": "finishing-regression prior",
        "metric_delta": (
            "O/U-2.5 Brier 0.2633→0.2615, 1X2 Brier 0.2309→0.2295 "
            "(both ECE also improve)"
        ),
        "module": "domains/soccer/finishing_prior.py",
        "wave": "W99",
        "commit": "facda0f4",
    },
    {
        "sport": "MLB",
        "name": "negbinom over-dispersed run engine",
        "metric_delta": (
            "O/U Brier improves -0.014..-0.022 all thresholds; "
            "Poisson tail over-confidence fixed"
        ),
        "module": "domains/mlb/negbinom_engine.py",
        "wave": "W101",
        "commit": "6124d86b",
    },
    {
        "sport": "MLB",
        "name": "SP-form -> Elo log-odds offset",
        "metric_delta": "ECE 0.0121→0.0092",
        "module": "domains/mlb/sp_elo_offset.py",
        "wave": "W99",
        "commit": "2c06de12",
    },
    {
        "sport": "NBA",
        "name": "multi-feature WF win-prob",
        "metric_delta": "ECE 0.0293→0.0176 (full corpus)",
        "module": "scripts/platformkit/nba_winprob_model.py",
        "wave": "W93",
        "commit": "a83c0e2a",
    },
    {
        "sport": "Tennis",
        "name": "Platt logit recalibration",
        "metric_delta": "Brier 0.2222→0.2197, ECE 0.0484→0.0187",
        "module": "domains/tennis/elo_tune.py",
        "wave": "W93",
        "commit": "7a6e5181",
    },
    {
        "sport": "Tennis",
        "name": "as-of hold% prior (games/sets substrate)",
        "metric_delta": "hold MAE 39% better than flat-0.62 baseline",
        "module": "domains/tennis/asof_hold.py",
        "wave": "W99",
        "commit": "f32d0c78",
    },
]

# Tested-but-absorbed nulls (honest record; not shipped as standalone improvements)
_ABSORBED: List[str] = [
    "NBA opp-adj rating + quarter-variance priors",
    "Soccer discipline signal + per-team HFA offset",
    "MLB park factor folded into the run engine",
    "NBA availability/load signal",
]
_ABSORBED_NOTE = (
    "absorbed by the rating/engine; recorded not shipped — "
    "structurally redundant or indistinguishable from base model noise"
)

_SPORTS_ORDER = ["NBA", "MLB", "Soccer", "Tennis"]


def _entries_for(sport: str) -> List[Dict]:
    return [e for e in _ENTRIES if e["sport"] == sport]


def _render_sport(sport: str) -> str:
    rows = _entries_for(sport)
    lines = [
        f"---\ntags: [organized, {sport.lower()}, validated, calibration, person-free]\n---",
        f"# {sport} — Validated Leak-Free Improvements\n",
        _BANNER + "\n",
        (
            f"Leak-free, walk-forward validated calibration/accuracy improvements "
            f"for **{sport}**.  Each entry is PROVENANCE-TAGGED (wave + commit + "
            f"module); re-run the module CLI to reproduce.  "
            f"No edge claimed; calibration is not edge.\n"
        ),
    ]
    if rows:
        lines += [
            "## Validated improvements\n",
            "| # | Improvement | Metric delta | Module | Wave | Commit |",
            "|---|-------------|-------------|--------|------|--------|",
        ]
        for i, e in enumerate(rows, 1):
            lines.append(
                f"| {i} | {e['name']} | {e['metric_delta']} "
                f"| `{e['module']}` | {e['wave']} | `{e['commit']}` |"
            )
        lines.append("")
    else:
        lines += ["## Validated improvements\n", "_None recorded for this sport yet._\n"]

    lines += [
        "## Tested but ABSORBED (nulls, not shipped)\n",
        (
            "_Improvements trialled but absorbed into the base rating/engine "
            "without a standalone ship.  Recorded for completeness._\n"
        ),
    ]
    absorbed = [a for a in _ABSORBED if sport.lower() in a.lower()]
    if absorbed:
        for a in absorbed:
            lines.append(f"- {a} — {_ABSORBED_NOTE}")
        lines.append("")
    else:
        lines.append("_None recorded for this sport._\n")

    lines += [
        "## Reading this honestly",
        "- **Calibration is not edge.**  Lower Brier/ECE = better calibrated "
        "probabilities, not a market price model.  No edge is claimed.",
        "- **Validate at the cited commit.**  Each entry shows the wave + commit "
        "where the result was originally confirmed; run the module CLI to reproduce.",
        "- **Distribution-shape fixes won; mean-shift priors absorbed.**  "
        "Structure/shape changes (NegBinom tail, Platt scaling, hold% substrate) "
        "improved OOS metrics; additive mean offsets were absorbed by the base model.",
        "- **No edge claimed** across all entries.  Markets are efficient.",
    ]
    return "\n".join(lines) + "\n"


def _render_index() -> str:
    all_sports_covered = sorted({e["sport"] for e in _ENTRIES})
    lines = [
        "---\ntags: [index, validated, calibration, person-free]\n---",
        "# Cross-Sport Validated Leak-Free Improvements\n",
        _BANNER + "\n",
        (
            "Top-level index of all PROVENANCE-TAGGED validated leak-free "
            "calibration/accuracy improvements across the platform.  "
            "Distribution-shape/structure fixes won; mean-shift priors got absorbed.  "
            "No edge claimed; calibration is not edge.\n"
        ),
        f"Sports covered: {', '.join(all_sports_covered)}  "
        f"| Total validated entries: {len(_ENTRIES)}\n",
        "## All validated improvements\n",
        "| Sport | Improvement | Metric delta | Module | Wave | Commit |",
        "|-------|-------------|-------------|--------|------|--------|",
    ]
    for e in _ENTRIES:
        lines.append(
            f"| {e['sport']} | {e['name']} | {e['metric_delta']} "
            f"| `{e['module']}` | {e['wave']} | `{e['commit']}` |"
        )
    lines += [
        "",
        "## Tested but ABSORBED (nulls, not shipped — all sports)\n",
        (
            "_Improvements trialled but absorbed into the base rating/engine "
            "without a standalone ship: " + "; ".join(_ABSORBED) + ".  "
            + _ABSORBED_NOTE.capitalize() + "._\n"
        ),
        "## Key framing",
        "- Calibration is not edge.  No edge is claimed across any entry.",
        "- Validated at the cited commit -- re-verify via the module CLI.",
        "- Distribution-shape/structure fixes won; mean-shift priors got absorbed.",
        "- Markets are efficient; no edge claimed.",
    ]
    return "\n".join(lines) + "\n"


def build_validated(
    organized_root: Optional[Path] = None,
    write: bool = True,
) -> Dict:
    """Render per-sport + index validated-improvements artifacts.

    Parameters
    ----------
    organized_root : Path to vault/_Organized (default auto-detected).
    write          : write .md files when True (default True).

    Returns a report dict with per-sport status + the rendered text.
    """
    root = (
        Path(organized_root)
        if organized_root is not None
        else (_REPO_ROOT / "vault" / "_Organized")
    )
    report: Dict = {}

    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        report[sport] = {
            "n_entries": len(_entries_for(sport)),
            "md": md,
        }
        if write:
            sport_dir = root / sport
            sport_dir.mkdir(parents=True, exist_ok=True)
            (sport_dir / "_Validated_Improvements.md").write_text(md, encoding="utf-8")

    idx_md = _render_index()
    report["_index"] = {"n_total": len(_ENTRIES), "md": idx_md}
    if write:
        idx_dir = root / "_Index"
        idx_dir.mkdir(parents=True, exist_ok=True)
        (idx_dir / "_Validated_Improvements.md").write_text(idx_md, encoding="utf-8")

    report["_note"] = (
        "calibration/accuracy only, NOT a market edge; no edge claimed; "
        "distribution-shape/structure fixes won; mean-shift priors got absorbed"
    )
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_validated(
        organized_root=Path(root_arg) if root_arg else None,
        write=True,
    )
    if "--json" in argv:
        safe = {k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items()
                                                        if kk != "md"})
                for k, v in rep.items()}
        print(json.dumps(safe, indent=2, default=str))
        return 0
    for sport in _SPORTS_ORDER:
        info = rep.get(sport, {})
        print(f"  [{sport:<7}] {info.get('n_entries', 0)} validated entries written")
    idx = rep.get("_index", {})
    print(f"  [Index  ] {idx.get('n_total', 0)} total entries -> _Index/_Validated_Improvements.md")
    print(f"  NOTE: {rep['_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
