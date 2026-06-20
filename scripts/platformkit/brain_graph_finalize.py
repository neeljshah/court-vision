"""
brain_graph_finalize.py -- THE single entrypoint that makes the Obsidian brain
one fully-navigable, enriched, coherent graph. Run this LAST, after any brain
rebuild (brain_pipeline) and any human edits.

Passes, in dependency order (each idempotent; re-run = byte-identical):

  1. brain_folder_indexes  -- complete + recursive + enriched folder/sport indexes
                              (the structural backbone: every note linked from its
                              folder index, every folder from its sport index).
  2. brain_system_map      -- the Platform->...->Intelligence funnel notes.
  3. brain_crosslinks      -- within-sport "## Related" concept links.
  4. brain_enrich          -- enrich the master _Index + cross-sport hubs and link
                              every top-level area (the last reachability gap).
  5. brain_fix_relative_links -- normalize any ../ or .md links to vault-relative.
  6. brain_reachability    -- ASSERT reachable == total from _Index (fail-closed).

Honest framing: an intelligence MAP, not a betting edge; calibration is not edge.

    python scripts/platformkit/brain_graph_finalize.py vault [--no-assert]

Exit code is nonzero if the graph is not 100% reachable (unless --no-assert).
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain_folder_indexes import build_folder_indexes  # noqa: E402
from brain_system_map import build_system_map  # noqa: E402
from brain_crosslinks import build_crosslinks  # noqa: E402
from brain_enrich import enrich_all  # noqa: E402
from brain_fix_relative_links import normalize_vault  # noqa: E402
from brain_reachability import analyze  # noqa: E402


def finalize(vault_root, write: bool = True, do_assert: bool = True) -> dict:
    vault = Path(vault_root)
    rep: dict = {}
    rep["folder_indexes"] = build_folder_indexes(vault, write=write)
    rep["system_map"] = build_system_map(vault, write=write)
    try:
        rep["crosslinks"] = build_crosslinks(vault / "_Organized", write=write)
    except Exception as e:  # noqa: BLE001  -- crosslinks is best-effort enrichment
        rep["crosslinks"] = {"error": str(e)}
    rep["enrich"] = enrich_all(vault, write=write)
    rep["fix_links"] = normalize_vault(vault, write=write)
    reach = analyze(vault, list_unreached=True)
    rep["reachability"] = {k: v for k, v in reach.items()
                           if k != "unreachable_notes"}
    rep["fully_reachable"] = (reach["unreachable"] == 0)
    if not rep["fully_reachable"]:
        rep["reachability"]["sample_unreachable"] = reach["unreachable_notes"][:20]
    return rep


def _print(rep: dict) -> None:
    r = rep["reachability"]
    print("== brain_graph_finalize ==")
    print(f"folder indexes : {rep['folder_indexes'].get('indexes')} "
          f"({rep['folder_indexes'].get('written')} written)")
    print(f"system map     : {rep['system_map'].get('notes')} notes")
    cl = rep.get("crosslinks", {})
    print(f"crosslinks     : {cl.get('n_linked', cl.get('error'))}")
    print(f"enrich         : master={rep['enrich']['master_changed']} "
          f"hubs={rep['enrich']['hubs_changed']}")
    print(f"links fixed    : {rep['fix_links'].get('links_fixed')}")
    print(f"reachable      : {r['reachable']} / {r['in_scope']}  "
          f"(unreachable={r['unreachable']}, components={r['components']})")
    if r.get("sample_unreachable"):
        print("unreachable    :", ", ".join(r["sample_unreachable"]))
    print(f"FULLY REACHABLE: {rep['fully_reachable']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Finalize the brain graph (run last).")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--no-assert", action="store_true",
                    help="report but do not exit nonzero on partial reachability")
    a = ap.parse_args()
    rep = finalize(a.vault, write=True, do_assert=not a.no_assert)
    _print(rep)
    if not a.no_assert and not rep["fully_reachable"]:
        print("ASSERT FAILED: brain graph is not 100% reachable from _Index.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
