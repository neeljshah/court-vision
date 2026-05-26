"""Fetch historical NBA line data from free public GitHub repos.

Sources:
  1. reisneriv/NBA_Player_Props - DK/FD/MGM/BetRivers PLAYER PROP lines
     + actual outcomes, 2024 NBA playoffs (~35 daily xlsx snapshots).
  2. FinnedAI/sportsbookreview-scraper - 10Y NBA GAME-LEVEL odds
     (ML / spread / total, no player props), 2011-2021.
  3. benashkar/nba_gambling - DK/FD/MGM PLAYER PROP closing-line
     archive, ~48 daily snapshots covering Jan 28 - May 8 2026
     (2025-26 NBA regular season + 2026 playoffs).
  4. lilswad/NbaBetExplorer - NBA GAME-LEVEL closing odds, decimal
     format, 2022-23 / 2023-24 / 2024-25 / 2025-26 seasons.

Outputs to local subdirectories. No auth required. Safe to re-run
(skips files already on disk).
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "nba-ai-system/research"}


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def download(url: str, dest: Path) -> int:
    if dest.exists() and dest.stat().st_size > 0:
        return dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = http_get(url)
    dest.write_bytes(data)
    return len(data)


def fetch_reisneriv():
    """List repo via GitHub API, grab every .xlsx that looks like a prop snapshot."""
    api = "https://api.github.com/repos/reisneriv/NBA_Player_Props/contents"
    listing = json.loads(http_get(api).decode())
    out_dir = HERE / "reisneriv_2024_playoffs"
    n_ok = n_skip = 0
    for entry in listing:
        if entry["type"] != "file":
            continue
        name = entry["name"]
        if not name.lower().endswith(".xlsx"):
            continue
        url = entry["download_url"]
        dest = out_dir / name
        try:
            size = download(url, dest)
            print(f"  [ok] {name} ({size} bytes)")
            n_ok += 1
        except Exception as e:
            print(f"  [fail] {name}: {e}")
            n_skip += 1
        time.sleep(0.2)
    return n_ok, n_skip


def fetch_sbr_archive():
    """Game-level odds (ML/spread/total), 2011-2021. Single JSON file."""
    url = "https://github.com/FinnedAI/sportsbookreview-scraper/raw/main/data/nba_archive_10Y.json"
    dest = HERE / "sbr_archive_2011_2021" / "nba_archive_10Y.json"
    size = download(url, dest)
    print(f"  [ok] nba_archive_10Y.json ({size} bytes)")
    return 1, 0


def _list_tree(repo: str, branch: str) -> list:
    """Return flat list of (path, size) blobs in a repo at branch HEAD."""
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    blob = json.loads(http_get(url).decode())
    out = []
    for f in blob.get("tree", []):
        if f.get("type") != "blob":
            continue
        out.append((f.get("path", ""), int(f.get("size", 0))))
    return out


def fetch_benashkar():
    """DK/FD/MGM player props, 2025-26 season + 2026 playoffs (~40 MB)."""
    repo = "benashkar/nba_gambling"
    branch = "master"
    out_dir = HERE / "benashkar_nba_gambling"
    tree = _list_tree(repo, branch)
    targets = [
        (p, s) for p, s in tree
        if p.startswith("data/output/")
        and (p.endswith(".csv"))
        and s > 50_000
    ]
    n_ok = n_fail = 0
    for path, size in targets:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        dest = out_dir / path.replace("/", "__")
        try:
            actual = download(url, dest)
            print(f"  [ok] {path} ({actual} bytes)")
            n_ok += 1
        except Exception as e:
            print(f"  [fail] {path}: {e}")
            n_fail += 1
        time.sleep(0.3)
    return n_ok, n_fail


def fetch_lilswad():
    """NBA game-level closing odds 2022-2026 (decimal format)."""
    repo = "lilswad/NbaBetExplorer"
    branch = "main"
    out_dir = HERE / "lilswad_NbaBetExplorer"
    files = [
        "nba_2022-2023.csv",
        "nba_2023-2024.csv",
        "nba_2024-2025.csv",
        "nba_2025-2026.csv",
        "nba_all_seasons.csv",
    ]
    n_ok = n_fail = 0
    for f in files:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{f}"
        dest = out_dir / f
        try:
            size = download(url, dest)
            print(f"  [ok] {f} ({size} bytes)")
            n_ok += 1
        except Exception as e:
            print(f"  [fail] {f}: {e}")
            n_fail += 1
        time.sleep(0.3)
    return n_ok, n_fail


def main():
    print("== reisneriv/NBA_Player_Props (DK/FD/MGM/BetRivers player props, 2024 playoffs) ==")
    ok, fail = fetch_reisneriv()
    print(f"  -> {ok} ok, {fail} fail\n")

    print("== FinnedAI/sportsbookreview-scraper (game-level ML/spread/total 2011-2021) ==")
    ok2, fail2 = fetch_sbr_archive()
    print(f"  -> {ok2} ok, {fail2} fail\n")

    print("== benashkar/nba_gambling (DK/FD/MGM player props, 2025-26 + 2026 playoffs) ==")
    ok3, fail3 = fetch_benashkar()
    print(f"  -> {ok3} ok, {fail3} fail\n")

    print("== lilswad/NbaBetExplorer (NBA game-level closing odds, 2022-2026) ==")
    ok4, fail4 = fetch_lilswad()
    print(f"  -> {ok4} ok, {fail4} fail\n")


if __name__ == "__main__":
    sys.exit(main())
