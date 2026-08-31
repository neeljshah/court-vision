"""Generate honest, deterministic multi-sport tracking evidence pages."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any


MARKER = "<!-- GENERATED: scripts/platformkit/evidence_page.py -->"
METRICS = ("coverage_pct", "det_per_frame", "median_track_len", "ball_valid_pct",
           "jump_p95", "oob_pct")
MODEL_NAMES = ("wp_oos", "nfl_game_model", "teacher_student")


def _ascii(value: Any) -> str:
    """Return a Markdown-safe ASCII representation of a report value."""
    return str(value).encode("ascii", "backslashreplace").decode("ascii").replace("|", "\\|")


def _number(value: Any) -> str:
    return f"{value:.4g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else _ascii(value)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _ledger_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not path.exists():
        return labels
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        key = row.get("report") or row.get("report_path") or row.get("path")
        label = row.get("game") or row.get("game_id") or row.get("game_name")
        if key and label:
            labels[Path(str(key)).stem] = _ascii(label)
    return labels


def _reports(root: Path) -> dict[str, list[dict[str, Any]]]:
    labels = _ledger_labels(root / "data" / "tracking_reports" / "ledger.jsonl")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((root / "data" / "tracking_reports").glob("**/*.json")):
        row = _read_json(path)
        if not row or not isinstance(row.get("sport"), str):
            continue
        if not all(key in row for key in ("n_frames", "passed", "failures")):
            continue
        row = dict(row)
        row["game"] = labels.get(path.stem, path.stem)
        row["_path"] = path
        grouped.setdefault(row["sport"], []).append(row)
    return grouped


def _median(rows: list[dict[str, Any]], key: str) -> str:
    values = [row[key] for row in rows if isinstance(row.get(key), (int, float))]
    return _number(statistics.median(values)) if values else "n/a"


def _demo(root: Path, game: str) -> str:
    path = root / "docs" / "evidence" / "demos" / f"{game}_demo.gif"
    return f"[GIF](../demos/{game}_demo.gif)" if path.exists() else "-"


def _sport_page(root: Path, sport: str, rows: list[dict[str, Any]]) -> str:
    lines = [MARKER, "", f"# { _ascii(sport) } tracking evidence", "",
             "| Game | Frames | Pass | Coverage | Det/frame | Track median | Ball valid | Jump p95 | OOB | Demo |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        lines.append("| {game} | {frames} | {passed} | {coverage} | {det} | {track} | {ball} | {jump} | {oob} | {demo} |".format(
            game=_ascii(row["game"]), frames=_number(row.get("n_frames", "n/a")),
            passed="PASS" if row.get("passed") else "FAIL", coverage=_number(row.get("coverage_pct", "n/a")),
            det=_number(row.get("det_per_frame", "n/a")), track=_number(row.get("median_track_len", "n/a")),
            ball=_number(row.get("ball_valid_pct", "n/a")), jump=_number(row.get("jump_p95", "n/a")),
            oob=_number(row.get("oob_pct", "n/a")), demo=_demo(root, str(row["game"]))))
    return "\n".join(lines) + "\n"


def _flatten(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        return [item for key in sorted(value) for item in _flatten(value[key], f"{prefix}{key}." )]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return [(prefix.rstrip("."), _number(value))]
    return []


def _models(root: Path) -> list[str]:
    files = list((root / "data" / "ab_reports").glob("*.json"))
    chosen: list[Path] = []
    for name in MODEL_NAMES:
        matches = [path for path in files if name in path.stem.lower()]
        if matches:
            chosen.append(max(matches, key=lambda path: (path.stat().st_mtime, path.name)))
    chosen.extend(path for path in files if ("calib" in path.stem.lower()
                   or "model" in path.stem.lower()) and path not in chosen)
    lines = ["## Models", "", "Walk-forward/calibration reports are recorded below when present.", ""]
    for path in sorted(chosen, key=lambda item: item.name):
        report = _read_json(path)
        if report:
            lines += [f"### {_ascii(path.stem)}", "", "| Metric | Value |", "| --- | ---: |"]
            lines += [f"| {_ascii(key)} | {_ascii(value)} |" for key, value in _flatten(report)]
            lines.append("")
    lines += ["No betting edge or ROI is claimed; these are calibration and model-evaluation records only."]
    return lines


def _write_generated(path: Path, content: str) -> None:
    if path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER):
        raise ValueError(f"refusing to overwrite non-generated file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="ascii")


def generate(root: Path | str = ".") -> list[Path]:
    """Regenerate marked evidence pages and return their paths."""
    root = Path(root)
    grouped = _reports(root)
    output = root / "docs" / "evidence" / "multisport"
    pages: list[Path] = []
    lines = [MARKER, "", "# Multi-sport evidence", "", "| Sport | Games | Pass rate | Coverage median | Det/frame median | Track median | Ball valid median | Jump p95 median | OOB median |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for sport in sorted(grouped):
        rows = grouped[sport]
        passed = sum(bool(row.get("passed")) for row in rows) / len(rows)
        lines.append(f"| [{_ascii(sport)}]({_ascii(sport)}.md) | {len(rows)} | {passed:.0%} | " + " | ".join(_median(rows, key) for key in METRICS) + " |")
        page = output / f"{sport}.md"
        _write_generated(page, _sport_page(root, sport, rows))
        pages.append(page)
    lines += ["", "## Honest limitations", ""]
    failures = [(sport, row["game"], failure) for sport, rows in grouped.items() for row in rows for failure in row.get("failures", [])]
    lines += [f"- {_ascii(sport)}/{_ascii(game)}: {_ascii(failure)}" for sport, game, failure in failures] or ["- No failing metrics were reported."]
    lines += [""] + _models(root) + [""]
    readme = output / "README.md"
    _write_generated(readme, "\n".join(lines))
    return [readme] + pages


if __name__ == "__main__":
    generate()
