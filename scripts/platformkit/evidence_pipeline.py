"""Regenerate the whole evidence surface from the tracking data on disk.

One command so the published evidence can never drift from the data that
produced it: render missing court-diagram demos, regenerate the evidence
pages and the tracking scoreboard, then write a manifest of every artifact.

Rights safety is a WHITELIST: only court-diagram renders this pipeline knows
how to produce are marked public. Broadcast-derived artifacts (overlays) are
always private, and anything unrecognized is private too.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.platformkit import evidence_page, ledger_report
from scripts.platformkit.demo_render import render_csv

TRACKING_DIR = Path("data/tracking")
REPORTS_DIR = Path("data/tracking_reports")
EVIDENCE_DIR = Path("docs/evidence")
DEMO_DIR = EVIDENCE_DIR / "demos"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
TRACKING_CSV_NAME = "tracking_data.csv"
MEDIA_SUFFIXES = {".mp4", ".gif", ".png", ".jpg", ".jpeg", ".webm", ".mov"}
# Broadcast pixels are never rights-safe. These tokens force private even if
# the artifact otherwise looks like one of our own court-diagram renders.
PRIVATE_TOKENS = ("overlay", "broadcast", "sidebyside", "side_by_side")
DEFAULT_SPORT = "basketball"
DEMO_SECONDS = 15.0


def _mtime(path: Path) -> str:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return stamp.isoformat(timespec="seconds")


def _sport_for(root: Path, game_id: str, csv_path: Path) -> str:
    """Resolve a game's sport from its own report, then the report tree."""
    sibling = csv_path.with_name("quality_report.json")
    try:
        report = json.loads(sibling.read_text(encoding="utf-8"))
        if isinstance(report, dict) and isinstance(report.get("sport"), str):
            return report["sport"].lower()
    except (OSError, json.JSONDecodeError):
        pass
    for path in sorted((root / REPORTS_DIR).glob("*/%s.json" % game_id)):
        return path.parent.name.lower()
    return DEFAULT_SPORT


def discover_games(root: Path) -> list[dict[str, Any]]:
    """Return every game directory that holds a normalized tracking CSV."""
    games: list[dict[str, Any]] = []
    for csv_path in sorted((root / TRACKING_DIR).glob("*/" + TRACKING_CSV_NAME)):
        game_id = csv_path.parent.name
        games.append({
            "game_id": game_id,
            "sport": _sport_for(root, game_id, csv_path),
            "csv": csv_path,
        })
    return games


def _demo_is_current(root: Path, game: dict[str, Any]) -> bool:
    """A demo is current when its GIF exists and is not older than the CSV."""
    gif = root / DEMO_DIR / ("%s_demo.gif" % game["game_id"])
    if not gif.is_file():
        return False
    return gif.stat().st_mtime >= game["csv"].stat().st_mtime


def render_demos(root: Path, games: list[dict[str, Any]],
                 only_new: bool = True) -> dict[str, Any]:
    """Render the court-diagram demo for each game, skipping current ones."""
    rendered: list[str] = []
    skipped: list[str] = []
    failures: list[dict[str, str]] = []
    for game in games:
        game_id = game["game_id"]
        if only_new and _demo_is_current(root, game):
            skipped.append(game_id)
            continue
        stem = root / DEMO_DIR / ("%s_demo" % game_id)
        try:
            render_csv(
                game["csv"],
                game["sport"],
                out_path=stem.with_suffix(".mp4"),
                gif_path=stem.with_suffix(".gif"),
                max_seconds=DEMO_SECONDS,
            )
        except Exception as exc:  # a bad clip must not stop the surface rebuild
            failures.append({"stage": "demo", "game": game_id, "error": str(exc)})
            continue
        rendered.append(game_id)
    return {"rendered": rendered, "skipped": skipped, "failures": failures}


def regenerate_pages(root: Path) -> dict[str, Any]:
    """Rebuild the per-sport evidence pages and the tracking scoreboard."""
    pages: list[Path] = []
    failures: list[dict[str, str]] = []
    try:
        pages = list(evidence_page.generate(root))
    except Exception as exc:
        failures.append({"stage": "pages", "game": "-", "error": str(exc)})
    reports_root = root / REPORTS_DIR
    try:
        reports_root.mkdir(parents=True, exist_ok=True)
        ledger_report.report(reports_root)
    except Exception as exc:
        failures.append({"stage": "scoreboard", "game": "-", "error": str(exc)})
    return {"pages": pages, "failures": failures}


def _classify(path: Path, sports: dict[str, str]) -> dict[str, Any]:
    """Classify one artifact; unknown artifacts stay private by default."""
    name = path.name.lower()
    if any(token in name for token in PRIVATE_TOKENS):
        return {"kind": "broadcast_overlay", "rights_safe": False,
                "game": None, "sport": None}
    if path.suffix.lower() == ".md":
        return {"kind": "evidence_page", "rights_safe": True,
                "game": None, "sport": None}
    if path.name == "scoreboard.json":
        return {"kind": "scoreboard", "rights_safe": True,
                "game": None, "sport": None}
    # ponytail: whitelist -- docs/evidence/demos/<game>_demo.{mp4,gif} is the
    # only path demo_render writes, so it is the only public media shape.
    if (path.parent.name == "demos" and path.stem.endswith("_demo")
            and path.suffix.lower() in {".mp4", ".gif"}):
        game = path.stem[: -len("_demo")]
        return {"kind": "court_diagram_demo", "rights_safe": True,
                "game": game, "sport": sports.get(game)}
    return {"kind": "unclassified", "rights_safe": False,
            "game": None, "sport": None}


def _artifact_paths(root: Path, pages: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in sorted((root / EVIDENCE_DIR).rglob("*")):
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
            found.append(path)
    found.extend(path for path in pages if path.is_file())
    scoreboard = root / REPORTS_DIR / "scoreboard.json"
    if scoreboard.is_file():
        found.append(scoreboard)
    return list(dict.fromkeys(found))


def build_manifest(root: Path, games: list[dict[str, Any]],
                   pages: list[Path]) -> dict[str, Any]:
    """Write docs/evidence/manifest.json describing every evidence artifact."""
    sports = {game["game_id"]: game["sport"] for game in games}
    artifacts: list[dict[str, Any]] = []
    for path in _artifact_paths(root, pages):
        entry = _classify(path, sports)
        entry["rights_safe"] = bool(entry["rights_safe"])
        entry["visibility"] = "public" if entry["rights_safe"] else "private"
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        entry["path"] = relative
        entry["bytes"] = path.stat().st_size
        entry["mtime_utc"] = _mtime(path)
        artifacts.append(entry)
    public = sum(1 for entry in artifacts if entry["rights_safe"])
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_games_with_tracking": len(games),
        "n_artifacts": len(artifacts),
        "n_public": public,
        "n_private": len(artifacts) - public,
        "artifacts": sorted(artifacts, key=lambda entry: entry["path"]),
    }
    out = root / MANIFEST_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    return manifest


def _summary_lines(result: dict[str, Any]) -> list[str]:
    manifest = result["manifest"]
    lines = [
        "EVIDENCE PIPELINE",
        "  games with tracking data : %d" % len(result["games"]),
        "  demos rendered           : %d" % len(result["rendered"]),
        "  demos skipped (current)  : %d" % len(result["skipped"]),
        "  evidence pages written   : %d" % len(result["pages"]),
        "  manifest artifacts       : %d (public %d / private %d)" % (
            manifest["n_artifacts"], manifest["n_public"], manifest["n_private"]),
        "  failures                 : %d" % len(result["failures"]),
    ]
    if result["failures"]:
        lines.append("FAILURES")
        lines.extend("  %s %s: %s" % (item["stage"], item["game"], item["error"])
                     for item in result["failures"])
    return lines


def run_pipeline(root: Path | str = ".", only_new: bool = True,
                 quiet: bool = False) -> dict[str, Any]:
    """Rebuild demos, evidence pages, scoreboard, and manifest under root."""
    root = Path(root)
    games = discover_games(root)
    demos = render_demos(root, games, only_new)
    pages_result = regenerate_pages(root)
    pages = pages_result["pages"]
    manifest = build_manifest(root, games, pages)
    result = {
        "games": [game["game_id"] for game in games],
        "rendered": demos["rendered"],
        "skipped": demos["skipped"],
        "pages": [path.as_posix() for path in pages],
        "manifest": manifest,
        "manifest_path": (root / MANIFEST_PATH).as_posix(),
        "failures": demos["failures"] + pages_result["failures"],
    }
    if not quiet:
        print("\n".join(_summary_lines(result)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate the entire evidence surface from tracking data.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--all", action="store_true",
                        help="Re-render every demo, not just missing/stale ones")
    args = parser.parse_args()
    result = run_pipeline(args.root, only_new=not args.all)
    raise SystemExit(1 if result["failures"] else 0)


if __name__ == "__main__":
    main()
