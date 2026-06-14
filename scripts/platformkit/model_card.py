"""model_card.py — per-sport browsable MODEL CARD for the organized brain.

Composes the W78 model_ops scorecard (rating_calibrated.run_sport: generic Elo ->
best leak-free calibrator -> OOS metrics vs the adapter baseline) into a markdown
artifact ``vault/_Organized/<SPORT>/_Model_Card.md`` so the model layer becomes
browsable memory in the Obsidian brain alongside the per-sport reads and digests.

Honest throughout: every number is a CALIBRATION / ACCURACY metric, never a market
edge.  ACCURACY/CALIBRATION != EDGE; neither model beats the close.  The card links
to the EB-regularized base-rate artifact when present.

CLI: ``python -m scripts.platformkit.model_card [--sport nba] [--write] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from scripts.platformkit.generic_rating import Loader
from scripts.platformkit.rating_calibrated import run_sport

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORG_DIR = {"nba": "NBA", "mlb": "MLB", "soccer": "Soccer", "tennis": "Tennis"}
_NOTE = ("Every number is a calibration/accuracy metric (Brier/log-loss/ECE), NEVER a "
         "market edge. ACCURACY/CALIBRATION != EDGE; neither model beats the close.")


def parse_card_metrics(sport_key: str, organized_root: Optional[Path] = None) -> Optional[Dict]:
    """Parse calibrated-Elo OOS metrics from a written _Model_Card.md (or None).

    Lets other layers (e.g. sport_read) ground a read in VALIDATED model competence
    without recomputing. Pure read — originates no number.
    """
    import re  # noqa: PLC0415
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    p = root / _ORG_DIR.get(sport_key, sport_key.upper()) / "_Model_Card.md"
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"calibrated Elo \| ([\d.]+) \| ([\d.]+) \| ([\d.]+)", txt)
    if not m:
        return None
    c = re.search(r"chosen calibrator = \*\*(\w+)\*\*", txt)
    return {"brier": float(m.group(1)), "logloss": float(m.group(2)),
            "ece": float(m.group(3)), "calibrator": c.group(1) if c else None}


def _row(tag: str, m: Optional[Dict]) -> Optional[str]:
    """A table row, or None when the metric is absent (None is dropped; '' stays
    as an intentional blank-line separator)."""
    if not m:
        return None
    return f"| {tag} | {m['brier']} | {m['logloss']} | {m['ece']} |"


def _render(rep: Dict) -> str:
    sport = rep["sport"]
    lines = [
        "---\ntags: [organized, model-card]\n---",
        f"# {sport.upper()} — Model Card (model_ops stack)\n",
        f"> **{_NOTE}**\n",
        "Stack: `GenericRatingModel` (leak-free walk-forward Elo) -> `select_calibrator` "
        "(best leak-free walk-forward calibrator by OOS log-loss) -> OOS scorecard.\n",
        f"**Eval:** n_games={rep['n_games']} · n_eval(OOS)={rep['n_eval']} · "
        f"chosen calibrator = **{rep['chosen_calibrator']}**\n",
        "| Forecaster | Brier | LogLoss | ECE |",
        "|------------|------:|--------:|----:|",
        _row("raw generic Elo", rep.get("raw_elo")),
        _row("calibrated Elo", rep.get("calibrated_elo")),
        _row("adapter baseline", rep.get("baseline")),
        "",
        "**Findings (honest):**",
        f"- Calibration improves ECE: **{rep.get('calib_improves_ece')}** · "
        f"log-loss: **{rep.get('calib_improves_logloss')}** "
        "(the OOS selector can never choose a calibrator worse than raw on log-loss).",
    ]
    if "baseline" in rep:
        beats = rep.get("calibrated_beats_baseline_brier")
        lines.append(f"- Calibrated generic Elo {'BEATS' if beats else 'trails'} the "
                     "hand-tuned adapter baseline on Brier "
                     f"({'abstraction competitive' if beats else 'baseline carries extra signal, honest'}).")
    lines += [
        "- **No edge.** A baseline match on calibration metrics is not a market edge.",
        "",
        f"Related: [[Teams]] · `_Team_Base_Rates_EB.md` (EB-regularized base rates) · "
        "`_Read.md` (intelligence read).",
    ]
    return "\n".join(l for l in lines if l is not None) + "\n"


def build_card(sport: str, *, min_history: int = 200, refit_every: int = 25,
               loader: Optional[Loader] = None) -> Dict:
    """Run the model_ops scorecard for *sport* and render a model card.

    Returns {sport, report, markdown} or {sport, error}.
    """
    rep = run_sport(sport, min_history=min_history, refit_every=refit_every, loader=loader)
    if "error" in rep:
        return {"sport": sport, "error": rep["error"]}
    return {"sport": sport, "report": rep, "markdown": _render(rep)}


def write_card(sport: str, card: Dict, organized_root: Optional[Path] = None) -> Optional[str]:
    """Write the model card to <organized_root>/<SPORT>/_Model_Card.md."""
    if "error" in card or sport not in _ORG_DIR:
        return None
    root = organized_root or (_REPO_ROOT / "vault" / "_Organized")
    out = root / _ORG_DIR[sport] / "_Model_Card.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(card["markdown"], encoding="utf-8")
    return str(out)


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    sport = None
    if "--sport" in argv:
        i = argv.index("--sport")
        sport = argv[i + 1] if i + 1 < len(argv) else None
    sports = [sport] if sport else ["nba", "mlb"]
    out: Dict[str, Dict] = {}
    for sp in sports:
        card = build_card(sp)
        if "--write" in argv and "error" not in card:
            card["artifact"] = write_card(sp, card)
        out[sp] = card
    if "--json" in argv:
        print(json.dumps({s: {k: v for k, v in c.items() if k != "markdown"}
                          for s, c in out.items()}, indent=2))
        return 0
    for sp, card in out.items():
        if "error" in card:
            print(f"\n[{sp}] ERROR: {card['error']}")
            continue
        print(card["markdown"])
        if card.get("artifact"):
            print(f"(written -> {card['artifact']})")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
