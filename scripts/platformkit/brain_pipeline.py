"""brain_pipeline.py — one-command rebuild of the organized Obsidian brain.

Chains the three brain builders in dependency order (each LOCAL, zero-network,
non-destructive to the SOURCE vault; the generated ``vault/_Organized/`` tree is
wiped+rebuilt):

    organize_all()   -> clean, deduped, person-free 4-sport tree + dense team hubs
    build_digests()  -> per-sport + cross-sport transfer digests
    export_reads()   -> per-sport intelligence reads as browsable memory

After the build it computes self-policing GATES (person_free, graph_clean, edge_clean) and
surfaces them in the summary. ``--strict`` makes the rebuild exit NONZERO if any gate fails.

Honest framing: an intelligence MAP, not a betting edge; markets efficient;
calibration is not edge. No number is emitted here.

CLI: ``python -m scripts.platformkit.brain_pipeline [--json] [--with-models] [--strict]``
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


def compute_gates(organized_root: Path) -> Dict:
    """Self-policing verification gates over the freshly built organized tree.

    person_free : no specific player/team names survive (vault_person_free_lint).
    graph_clean : zero player NODES and zero match NODES (graph_cleanliness).
    Both are computed defensively — a checker failure reports the gate as False, never
    crashes the rebuild. An intelligence MAP; markets efficient; calibration is not edge.
    """
    person_free = graph_clean = False
    try:
        from scripts.platformkit.vault_person_free_lint import lint_vault  # noqa: PLC0415
        person_free = bool(lint_vault(organized_root).get("person_free", False))
    except Exception:  # noqa: BLE001
        person_free = False
    try:
        from scripts.platformkit.graph_cleanliness import scan_vault  # noqa: PLC0415
        rep = scan_vault(organized_root)
        graph_clean = (rep.get("player_nodes", 1) == 0
                       and rep.get("match_nodes", 1) == 0)
    except Exception:  # noqa: BLE001
        graph_clean = False
    return {"person_free": person_free, "graph_clean": graph_clean}


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
    # top-level cross-sport scoreboard (one rating object, all 4 sports)
    try:
        from scripts.platformkit.platform_scoreboard import (  # noqa: PLC0415
            build_scoreboard, write_artifact as sb_write,
        )
        sb = build_scoreboard()
        if sb.get("n_sports", 0) > 0:
            sb_write(sb, organized_root=organized_root)
            models.setdefault("_scoreboard", {})["platform_scoreboard"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # per-sport calibration scoreboard (baseline vs improved ECE/Brier; surfaces the
    # W93/W94 calibration wins as a browsable artifact). Real per-sport providers are
    # heavy (full-corpus WF) -> only on the with_models real-data path. Audit-clean.
    try:
        from scripts.platformkit.calibration_scoreboard import (  # noqa: PLC0415
            build_calibration_scoreboard,
        )
        cal_rows = build_calibration_scoreboard(
            vault_root=organized_root / "_Index", write=True,
        )
        if any("error" not in r for r in cal_rows):
            models.setdefault("_calibration", {})["calibration_scoreboard"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # per-sport "what wins & why" driver taxonomy from the DESCRIPTIVE post-mortems
    # (aggregate knowledge, NOT a per-game signal). Reads real per-sport postmortem
    # parquets -> default-OFF path; missing parquet is skipped honestly. Audit-clean.
    try:
        from scripts.platformkit.brain_drivers import build_drivers  # noqa: PLC0415
        drv = build_drivers(organized_root=organized_root, write=True)
        built = [sp for sp, v in drv.items()
                 if not sp.startswith("_") and isinstance(v, dict) and "skipped" not in v]
        if built:
            models.setdefault("_drivers", {})["what_wins"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # per-sport factor-interaction MECHANISMS notes (cross-cutting "why" intelligence
    # from the DESCRIPTIVE post-mortems; person-free, audit-clean). Default-OFF path.
    try:
        from scripts.platformkit.brain_mechanisms import build_mechanisms  # noqa: PLC0415
        mech = build_mechanisms(organized_root=organized_root, write=True)
        if any(not sp.startswith("_") for sp in mech):
            models.setdefault("_mechanisms", {})["mechanisms"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # data-driven PERSON-FREE archetype clustering (computed from leak-free as-of
    # features: MLB pitcher roles, team styles). Deterministic; person-free; audit-clean.
    try:
        from scripts.platformkit.brain_archetypes import build_archetypes  # noqa: PLC0415
        arch = build_archetypes(vault_organized_dir=organized_root)
        if arch:
            models.setdefault("_archetypes", {})["computed"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # green-cell coverage map (light filesystem walk; accurate after the artifacts above)
    try:
        from scripts.platformkit.brain_coverage import (  # noqa: PLC0415
            build_coverage, write_artifact as cov_write,
        )
        cov = build_coverage(organized_root)
        if cov.get("n_sports", 0) > 0:
            cov_write(cov, organized_root=organized_root)
            models.setdefault("_coverage", {})["coverage_map"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # provenance-tagged VALIDATED leak-free improvements (static historical record;
    # per-sport + index; calibration/accuracy only, NOT a market edge; no edge claimed).
    try:
        from scripts.platformkit.brain_validated import build_validated  # noqa: PLC0415
        val = build_validated(organized_root=organized_root, write=True)
        n_total = val.get("_index", {}).get("n_total", 0)
        if n_total > 0:
            models.setdefault("_validated", {})["validated_improvements"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # cross-section "Related" links (another agent's module). Densifies the graph by
    # wiring concept notes to related concept notes; person-free. Skipped if not present.
    try:
        from scripts.platformkit.brain_crosslinks import build_crosslinks  # noqa: PLC0415
        cl = build_crosslinks(organized_root, write=True)   # mandated signature
        if cl and cl.get("n_linked", 0) > 0:
            models.setdefault("_crosslinks", {})["related_sections"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # PERSON-FREE cross-sport TRANSFER map: drivers/mechanisms -> generic SHAPES,
    # surfacing which model-family/calibration/distribution-shape lesson transfers
    # across sports. Pure filesystem+string ops; complementary to the archetype
    # _Cross_Sport_Digest; intelligence map only, no edge claimed.
    try:
        from scripts.platformkit.brain_transfer import build_transfer  # noqa: PLC0415
        tr = build_transfer(organized_root, write=True)
        if tr.get("n_links", 0) > 0:
            models.setdefault("_transfer", {})["cross_sport"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # per-sport KEY-STATS: which realized box stats most separate WINS from LOSSES
    # (standardized mean difference over the gitignored ESPN box parquets). DESCRIPTIVE
    # realized knowledge, person-free, NOT a leak-free signal; sparse/missing parquet is
    # skipped honestly. Real-data path -> default-OFF (with_models). Audit-clean.
    try:
        from scripts.platformkit.brain_keystats import build_keystats  # noqa: PLC0415
        ks = build_keystats(organized_root, write=True)
        if ks.get("n_sports", 0) > 0:
            models.setdefault("_keystats", {})["key_stats"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # W112 additive stages (form profiles -> stub consolidation+link-repair -> redundancy
    # audit). Kept in brain_extra_stages to hold this orchestrator under the LOC cap.
    try:
        from scripts.platformkit.brain_extra_stages import run_extra_stages  # noqa: PLC0415
        models.update(run_extra_stages(organized_root))
    except Exception:  # noqa: BLE001
        pass
    return models


def run_pipeline(vault_dir: Optional[Path] = None,
                 out_dir: Optional[Path] = None,
                 with_models: bool = False) -> Dict:
    """Run organize -> digest -> export (-> model cards + base rates if with_models).

    Returns a combined report dict with the three stage reports plus a compact
    summary.  Stages run in dependency order; digest/export read the freshly
    written ``_Organized`` tree.
    """
    # Source = live vault, or the legacy archive if its source dirs were moved OUT of
    # the graph (vault_archive_legacy). Output ALWAYS to the live vault/_Organized (the
    # graph) unless explicit source/out is given (hermetic tests keep their tmp paths).
    _live = _REPO_ROOT / "vault"
    _arch = _REPO_ROOT / "_vault_legacy_archive"
    if vault_dir is not None:
        src = Path(vault_dir)
        out = Path(out_dir) if out_dir is not None else src / "_Organized"
    else:
        src = _arch if (not (_live / "Sports").is_dir() and (_arch / "Sports").is_dir()) else _live
        out = Path(out_dir) if out_dir is not None else _live / "_Organized"
    organize = organize_all(vault_dir=src, out_dir=out)
    organized_root = Path(organize["out_dir"])
    digest = build_digests(organized_root=organized_root, write=True)
    export = export_reads(organized_root=organized_root, write=True)
    models = _run_model_stages(organized_root) if with_models else {}
    # Final self-policing gate: no artifact may make an un-caveated betting edge claim.
    from scripts.platformkit.brain_audit import audit_tree  # noqa: PLC0415
    audit = audit_tree(organized_root)
    gates = compute_gates(organized_root)
    # Make _Organized openable as its OWN clean Obsidian vault (graph = only the brain;
    # the full vault/ stays untouched). Seeded after the gates so the .obsidian config
    # never affects the person-free/graph scans. Skipped honestly on any error.
    try:
        from scripts.platformkit.brain_vault import ensure_brain_graph_config  # noqa: PLC0415
        ensure_brain_graph_config(organized_root)
    except Exception:  # noqa: BLE001
        pass

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
        "person_free": gates["person_free"],
        "graph_clean": gates["graph_clean"],
    }
    return {
        "organized_root": str(organized_root),
        "summary": summary,
        "stages": {"organize": organize, "digest": digest, "export": export,
                   "models": models, "audit": audit},
        "note": ("intelligence MAP, not a betting edge; markets efficient; "
                 "calibration is not edge"),
    }


def _gates_pass(summary: Dict) -> bool:
    """True only if ALL three self-policing gates hold (person/graph/edge clean)."""
    return bool(summary.get("person_free") and summary.get("graph_clean")
                and summary.get("edge_clean"))


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    strict = "--strict" in argv
    vault_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = run_pipeline(vault_dir=Path(vault_arg) if vault_arg else None,
                       with_models="--with-models" in argv)
    s = rep["summary"]
    if "--json" in argv:
        print(json.dumps(rep, indent=2, default=str))
        return 0 if (not strict or _gates_pass(s)) else 1
    print(f"organized_root : {rep['organized_root']}")
    print(f"sports         : {', '.join(s['sports'])}")
    print(f"teams / players: {s['teams_total']} / {s['players_total']}")
    print(f"matchup leaks  : {s['matchup_vs_leaks_out']} (inline prose only; 0 matchup files)")
    print(f"digests written: {s['digests_written']}")
    print(f"reads written  : {s['reads_written']}")
    if s.get("model_artifacts"):
        print(f"model artifacts: {s['model_artifacts']}")
    print(f"edge-clean     : {s.get('edge_clean')} (flagged={s.get('edge_flagged')})")
    print(f"person-free    : {s.get('person_free')}   graph-clean: {s.get('graph_clean')}")
    print(f"note           : {rep['note']}")
    if strict and not _gates_pass(s):
        print("STRICT GATE FAIL: person_free / graph_clean / edge_clean not all True.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
