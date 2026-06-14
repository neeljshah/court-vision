"""brain_pipeline.py — one-command rebuild of the organized Obsidian brain.

Chains the three brain builders in dependency order (each LOCAL, zero-network,
non-destructive to the SOURCE vault; the generated ``vault/_Organized/`` tree is
wiped+rebuilt):

    organize_all()   -> clean, deduped, person-free 4-sport tree + dense team hubs
    build_digests()  -> per-sport + cross-sport transfer digests
    export_reads()   -> per-sport intelligence reads as browsable memory

Honest framing: an intelligence MAP, not a betting edge; markets efficient;
calibration is not edge. No number is emitted here.

CLI: ``python -m scripts.platformkit.brain_pipeline [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.vault_organize_multi import organize_all  # noqa: E402
from scripts.platformkit.brain_digest import build_digests  # noqa: E402
from scripts.platformkit.brain_export import export_reads  # noqa: E402


def _run_model_stages(organized_root: Path) -> Dict:
    """Optional real-data stages: write per-sport model cards + EB base rates.

    These read the REAL per-sport corpora (their own loaders), so they only make
    sense on the live vault — hence default-OFF (``with_models``) to keep the
    hermetic fixture pipeline test clean. Errors per sport are skipped honestly.
    """
    from scripts.platformkit.model_card import build_card, write_card  # noqa: PLC0415
    from scripts.platformkit.eb_base_rates import (  # noqa: PLC0415
        build_for_sport, write_artifact,
    )
    models: Dict[str, Dict] = {}
    for sp in ("nba", "mlb", "tennis"):
        card = build_card(sp)
        if "error" not in card and write_card(sp, card, organized_root=organized_root):
            models.setdefault(sp, {})["model_card"] = "written"
        rep = build_for_sport(sp)
        if "error" not in rep and write_artifact(sp, rep, organized_root=organized_root):
            models.setdefault(sp, {})["base_rates"] = "written"
    return models


def run_pipeline(vault_dir: Optional[Path] = None,
                 out_dir: Optional[Path] = None,
                 with_models: bool = False) -> Dict:
    """Run organize -> digest -> export (-> model cards + base rates if with_models).

    Returns a combined report dict with the three stage reports plus a compact
    summary.  Stages run in dependency order; digest/export read the freshly
    written ``_Organized`` tree.
    """
    organize = organize_all(vault_dir=vault_dir, out_dir=out_dir)
    organized_root = Path(organize["out_dir"])
    digest = build_digests(organized_root=organized_root, write=True)
    export = export_reads(organized_root=organized_root, write=True)
    models = _run_model_stages(organized_root) if with_models else {}
    # Final self-policing gate: no artifact may make an un-caveated betting edge claim.
    from scripts.platformkit.brain_audit import audit_tree  # noqa: PLC0415
    audit = audit_tree(organized_root)

    per_sport = organize.get("per_sport", {})
    summary = {
        "sports": sorted(per_sport.keys()),
        "teams_total": sum(s.get("n_teams", 0) for s in per_sport.values()),
        "players_total": sum(s.get("n_players", 0) for s in per_sport.values()),
        "matchup_vs_leaks_out": organize.get("after", {}).get("matchup_vs_leaks"),
        "digests_written": digest.get("n_written"),
        "reads_written": export.get("n_written"),
        "model_artifacts": {sp: sorted(v) for sp, v in models.items()},
        "edge_clean": audit.get("clean"),
        "edge_flagged": audit.get("n_flagged"),
    }
    return {
        "organized_root": str(organized_root),
        "summary": summary,
        "stages": {"organize": organize, "digest": digest, "export": export,
                   "models": models, "audit": audit},
        "note": ("intelligence MAP, not a betting edge; markets efficient; "
                 "calibration is not edge"),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    vault_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = run_pipeline(vault_dir=Path(vault_arg) if vault_arg else None,
                       with_models="--with-models" in argv)
    if "--json" in argv:
        print(json.dumps(rep, indent=2, default=str))
        return 0
    s = rep["summary"]
    print(f"organized_root : {rep['organized_root']}")
    print(f"sports         : {', '.join(s['sports'])}")
    print(f"teams / players: {s['teams_total']} / {s['players_total']}")
    print(f"matchup leaks  : {s['matchup_vs_leaks_out']} (inline prose only; 0 matchup files)")
    print(f"digests written: {s['digests_written']}")
    print(f"reads written  : {s['reads_written']}")
    if s.get("model_artifacts"):
        print(f"model artifacts: {s['model_artifacts']}")
    print(f"edge-clean     : {s.get('edge_clean')} (flagged={s.get('edge_flagged')})")
    print(f"note           : {rep['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
