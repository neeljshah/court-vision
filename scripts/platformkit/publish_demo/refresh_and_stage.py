"""refresh_and_stage.py -- run export_snapshot.py against the live P5/boards
services, then git-add + commit webapp/public/demo-data (NO push -- CI's
deploy-demo.yml rebuilds from whatever is committed here).

Usage: python scripts/platformkit/publish_demo/refresh_and_stage.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DATA = REPO_ROOT / "webapp" / "public" / "demo-data"


def main() -> int:
    export_script = Path(__file__).with_name("export_snapshot.py")
    subprocess.run([sys.executable, str(export_script)], check=True, cwd=REPO_ROOT)

    subprocess.run(["git", "add", str(DEMO_DATA)], check=True, cwd=REPO_ROOT)

    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT
    ).returncode
    if status == 0:
        print("no snapshot changes -- nothing to commit")
        return 0

    subprocess.run(
        ["git", "commit", "-m", "chore(demo): refresh snapshot"],
        check=True,
        cwd=REPO_ROOT,
    )
    print("committed refreshed demo snapshot (not pushed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
