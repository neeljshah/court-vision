"""
brain_graph_display.py -- apply the Obsidian DISPLAY tweaks for the brain graph.

MUST be run with Obsidian CLOSED: Obsidian owns vault/.obsidian/graph.json while
running and reverts external edits on close. This script REFUSES to run if an
Obsidian process is detected (unless --force), and clears the read-only bit
Obsidian leaves on graph.json.

Changes (all idempotent):
  - graph.json: lineSizeMultiplier=1.2, textFadeMultiplier=0,
                add a colorGroup for path:"_System" if absent.
  - %APPDATA%/obsidian/obsidian.json: drop the junk registered-vault entry whose
                path ends in "\\.obsidian" (a stray sub-folder vault, not a real one).

    python scripts/platformkit/brain_graph_display.py vault [--force]
"""
from __future__ import annotations
import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

LINE_SIZE = 1.2
TEXT_FADE = 0
SYS_QUERY = 'path:"_System"'
SYS_COLOR = {"a": 1, "rgb": 4286945}


def _obsidian_running() -> bool:
    try:
        out = subprocess.run(["tasklist.exe"], capture_output=True, text=True,
                             timeout=15).stdout.lower()
        return "obsidian.exe" in out
    except Exception:  # noqa: BLE001 -- if we cannot check, be conservative below
        return False


def _apply_graph(vault: Path) -> dict:
    gp = vault / ".obsidian" / "graph.json"
    if not gp.exists():
        return {"graph_json": "missing"}
    gp.chmod(stat.S_IWRITE | stat.S_IREAD)  # clear read-only Obsidian leaves behind
    g = json.loads(gp.read_text(encoding="utf-8"))
    g["lineSizeMultiplier"] = LINE_SIZE
    g["textFadeMultiplier"] = TEXT_FADE
    cgs = g.setdefault("colorGroups", [])
    added = False
    if not any(c.get("query") == SYS_QUERY for c in cgs):
        cgs.insert(0, {"query": SYS_QUERY, "color": dict(SYS_COLOR)})
        added = True
    gp.write_text(json.dumps(g, indent=2), encoding="utf-8")
    return {"graph_json": "written", "line_size": LINE_SIZE,
            "text_fade": TEXT_FADE, "system_group_added": added}


def _apply_obsidian_json() -> dict:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return {"obsidian_json": "no APPDATA"}
    oj = Path(appdata) / "obsidian" / "obsidian.json"
    if not oj.exists():
        return {"obsidian_json": "missing"}
    o = json.loads(oj.read_text(encoding="utf-8"))
    vaults = o.get("vaults", {})
    before = len(vaults)
    drop = [k for k, v in vaults.items()
            if str(v.get("path", "")).replace("/", "\\").rstrip("\\").endswith("\\.obsidian")]
    for k in drop:
        del vaults[k]
    oj.write_text(json.dumps(o, indent=2), encoding="utf-8")
    return {"obsidian_json": "written", "vaults_before": before,
            "vaults_after": len(vaults), "dropped": drop}


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Obsidian display tweaks (run with Obsidian CLOSED).")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--force", action="store_true",
                    help="apply even if an Obsidian process is detected (will be reverted on close)")
    a = ap.parse_args()
    if _obsidian_running() and not a.force:
        print("REFUSING: Obsidian is running -- close it first (edits would be reverted). "
              "Re-run with --force only if you understand the revert risk.")
        return 1
    rep = {**_apply_graph(Path(a.vault)), **_apply_obsidian_json()}
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
