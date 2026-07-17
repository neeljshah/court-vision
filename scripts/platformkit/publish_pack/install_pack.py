"""install_pack.py -- consumer-side one-command installer for the CourtVision
data-pack. Works on a FRESH clone (no data/ yet).

  python scripts/platformkit/publish_pack/install_pack.py            # install latest
  python scripts/platformkit/publish_pack/install_pack.py --update   # re-download latest

It downloads the latest GitHub release asset (public API, stdlib only -- no
pip deps needed to bootstrap), unpacks into data/ WITHOUT clobbering any file
you already have (first install refuses on conflict; --update overwrites a
prior pack), verifies pack_info.json, then prints: python env setup, the
.mcp.json / Claude Desktop config snippet, and a 3-question smoke test.

Descriptive-intelligence snapshot only: no betting data, no live updates.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GH_REPO = "neeljshah/court-vision"
API_LATEST = f"https://api.github.com/repos/{GH_REPO}/releases/latest"
MARKER = REPO_ROOT / "data" / "cache" / "publish_pack" / "pack_info.json"
REQUIRED_INFO_KEYS = ("version_date", "file_count", "family_count", "edge_claimed")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "courtvision-install"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 -- fixed public host
        return r.read()


def latest_asset_url() -> tuple[str, str]:
    """Return (download_url, asset_name) for the newest .zip release asset."""
    rel = json.loads(_get(API_LATEST))
    for asset in rel.get("assets", []):
        if asset.get("name", "").endswith(".zip"):
            return asset["browser_download_url"], asset["name"]
    raise RuntimeError(f"no .zip asset on latest release of {GH_REPO}")


def _conflicts(zf: zipfile.ZipFile, root: Path) -> list[str]:
    """Existing files a first-install would overwrite (differing content)."""
    out: list[str] = []
    for m in zf.namelist():
        if m == "pack_info.json":
            continue
        dest = root / m
        if dest.is_file() and dest.stat().st_size != zf.getinfo(m).file_size:
            out.append(m)
    return out


def install(root: Path, zip_bytes: bytes, is_update: bool) -> dict:
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    try:
        info = json.loads(zf.read("pack_info.json"))
    except KeyError as e:
        raise RuntimeError("pack has no pack_info.json -- refusing") from e
    missing = [k for k in REQUIRED_INFO_KEYS if k not in info]
    if missing:
        raise RuntimeError(f"pack_info.json missing keys {missing} -- refusing")
    if info.get("edge_claimed") is not False:
        raise RuntimeError("pack_info.edge_claimed is not False -- refusing")

    prior = MARKER.is_file()
    if not (is_update or prior):
        conflicts = _conflicts(zf, root)
        if conflicts:
            raise RuntimeError(
                "refusing to overwrite existing non-pack files (run with --update "
                "to replace a prior pack):\n  " + "\n  ".join(conflicts[:20]))

    for m in zf.namelist():
        if m == "pack_info.json":
            continue
        dest = root / m
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(m))
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


def print_next_steps(root: Path, info: dict) -> None:
    root_fwd = root.as_posix()
    print("\n" + "=" * 60)
    print(f"Installed CourtVision data-pack {info['version_date']} -- "
          f"{info['file_count']} files, {info['family_count']} claim families.")
    print(info.get("honest_note", ""))
    print("=" * 60)

    print("\n1) Python env (from the repo root):")
    print("     python -m venv .venv")
    print("     # Windows:  .venv\\Scripts\\activate")
    print("     # mac/linux: source .venv/bin/activate")
    print("     pip install -r requirements.txt")

    print("\n2a) Claude Code -- the repo .mcp.json already declares the server:")
    print(json.dumps({"mcpServers": {"courtvision": {
        "command": "python",
        "args": ["-m", "scripts.platformkit.mcp_server.server"],
        "env": {"PYTHONPATH": "."}}}}, indent=2))
    print("    Open this repo in Claude Code and approve 'courtvision' when prompted.")

    print("\n2b) Claude Desktop -- Settings > Developer > Edit Config, then add:")
    print(json.dumps({"mcpServers": {"courtvision": {
        "command": "python",
        "args": ["-m", "scripts.platformkit.mcp_server.server"],
        "cwd": root_fwd}}}, indent=2))
    print("    Restart Claude Desktop; the CourtVision tools appear in the picker.")

    print("\n3) Smoke test (ask Claude these once connected):")
    print("     - \"Use system_health to show the snapshot date.\"")
    print("     - \"Scouting report for Nikola Jokic (nba).\"")
    print("     - \"What's the claim survival rate?\"  (analytics_receipts)")
    print("   Expect real numbers with a source_artifact + as_of, or an honest")
    print("   no_data. Betting/live questions return no_data BY DESIGN.\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="re-download latest")
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()

    try:
        url, name = latest_asset_url()
        print(f"downloading {name} ...")
        zip_bytes = _get(url)
        info = install(root, zip_bytes, is_update=args.update)
    except Exception as exc:  # noqa: BLE001 -- one clean error line for the consumer
        print(f"install failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print_next_steps(root, info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
