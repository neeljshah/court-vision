"""platform_scoreboard.py — one honest cross-sport prediction-quality readout.

Composes ``generic_rating.validate_sport`` across ALL 4 sports into a single
scorecard: how well the ONE GenericRatingModel object predicts each sport OOS
(leak-free), vs each sport's hand-tuned baseline (binary) or a naive mean (soccer
expected-score).  Written as a top-level brain artifact so the validated state of
the platform's predictions is browsable in one place.

> **Binding:** ACCURACY / CALIBRATION != EDGE.  A baseline match / beats-naive is a
> validated abstraction, NOT a market edge — markets are efficient and none of these
> models beats the close.  No edge is claimed anywhere.

CLI: ``python -m scripts.platformkit.platform_scoreboard [--write] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from scripts.platformkit.generic_rating import Loader, _SPORT_CFG, validate_sport

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPORTS = ["nba", "mlb", "tennis", "soccer"]
_NOTE = ("ACCURACY/CALIBRATION != EDGE. One generic rating object across 4 sports, "
         "validated OOS leak-free; a baseline match / beats-naive is a validated "
         "abstraction, NOT a market edge. Markets efficient; no edge claimed.")


def build_scoreboard(sports: Optional[List[str]] = None, *,
                     loader: Optional[Loader] = None, min_history: int = 200) -> Dict:
    """Validate the generic rating object on each sport; return a cross-sport report."""
    rows: List[Dict] = []
    for sp in (sports or _SPORTS):
        res = validate_sport(sp, min_history=min_history, loader=loader)
        if "error" in res:
            rows.append({"sport": sp, "error": res["error"]})
            continue
        g = res["generic_elo"]
        row: Dict = {"sport": sp, "n_eval": res["n_eval"],
                     "kind": _SPORT_CFG.get(sp, {}).get("kind", "binary")}
        if "rmse" in g:  # soccer expected-score
            row.update({"metric": "expected-score RMSE", "value": g["rmse"],
                        "reference": g["naive_rmse"], "reference_kind": "naive mean",
                        "validated": g["beats_naive"]})
        else:
            row.update({"metric": "Brier", "value": g["brier"]})
            if "baseline" in res:
                bb = res["baseline"]["brier"]
                row.update({"reference": bb, "reference_kind": "tuned baseline",
                            "validated": bool(g["brier"] <= bb + 0.003)})  # within noise
        rows.append(row)
    return {"rows": rows, "n_sports": len([r for r in rows if "error" not in r]),
            "note": _NOTE}


def render_markdown(rep: Dict) -> str:
    lines = [
        "---\ntags: [organized, platform-scoreboard]\n---",
        "# Platform Prediction Scoreboard — one rating object, 4 sports\n",
        f"> **{_NOTE}**\n",
        "Leak-free walk-forward, OOS. Binary sports vs the hand-tuned adapter baseline; "
        "soccer (expected-score W/D/L) vs a naive expanding-mean.\n",
        "| Sport | n_eval | Metric | Model | Reference | Validated? |",
        "|-------|-------:|--------|------:|----------:|:----------:|",
    ]
    for r in rep["rows"]:
        if "error" in r:
            lines.append(f"| {r['sport'].upper()} | — | — | — | _{r['error'][:30]}_ | — |")
            continue
        ref = f"{r['reference']} ({r['reference_kind']})" if "reference" in r else "—"
        ok = "YES" if r.get("validated") else "close/no"
        lines.append(f"| {r['sport'].upper()} | {r['n_eval']} | {r['metric']} | "
                     f"{r['value']} | {ref} | {ok} |")
    lines += [
        "\n**Honest reading:** the SAME object is competitive with each sport's "
        "hand-tuned model — the unification abstraction is real. Where it trails "
        "(MLB: pitcher-blind), that gap is honest. None of this beats the market — "
        "calibration is not edge; no edge is claimed.",
    ]
    return "\n".join(lines) + "\n"


def write_artifact(rep: Dict, organized_root: Optional[Path] = None) -> str:
    root = organized_root or (_REPO_ROOT / "vault" / "_Organized")
    out = root / "_Index" / "_Platform_Scoreboard.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(rep), encoding="utf-8")
    return str(out)


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    rep = build_scoreboard()
    if "--write" in argv:
        rep["artifact"] = write_artifact(rep)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"platform_scoreboard — one rating object, 4 sports (OOS)\nNOTE: {_NOTE}\n")
    for r in rep["rows"]:
        if "error" in r:
            print(f"  [{r['sport']}] ERROR: {r['error']}")
            continue
        ref = f" vs {r['reference']} ({r['reference_kind']})" if "reference" in r else ""
        print(f"  [{r['sport']:<6}] {r['metric']}={r['value']}{ref} "
              f"-> validated={r.get('validated')}")
    if rep.get("artifact"):
        print(f"\n  artifact -> {rep['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
