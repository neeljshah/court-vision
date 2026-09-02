"""answers.tracking_resolver -- fail-closed readout of the multi-sport tracking
QualityReport tree (``data/tracking_reports/**``).

Answers six question shapes, all descriptive, none predictive:
  scoreboard   -- per-sport games scored / pass rate / metric medians
  game_report  -- one game's QualityReport verbatim
  worst_metric -- the median metric furthest under its threshold + repair rule
  bar_progress -- games on file vs the 10-game evidence bar
  changed      -- diff the two most recent ledger rows for one game_id
  provenance   -- which footage produced a game's tracking

The scoreboard math is NOT re-derived here: ``tracking_brain.scorecard`` is
imported and wrapped, so this resolver and ``tracking_brain.next_actions`` can
never disagree.  Thresholds come from ``tracking_harness.SPORTS``.

HONESTY (carried in every envelope as ``caveat``): these are SELF-CONSISTENCY
health checks, never accuracy.  No labeled ground truth is involved, so no
accuracy claim and no edge claim can be read off any number here
(see .claude/rules/no-edge-claims.md).

Absent sport dir / zero reports / missing ledger -> ``no_data`` with the
reason.  Nothing is ever filled in from memory.

Run: python -m scripts.platformkit.answers.tracking_resolver "worst metric for tennis"
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking_brain import REPORTS_DIR, RULES, scorecard
from scripts.platformkit.tracking_harness import SPORTS

CATEGORY = "tracking_quality"
# tracking_brain.next_actions raises a priority-1 action below this count.
GAME_BAR = 10

CAVEAT = (
    "SELF-CONSISTENCY health check, not accuracy: coverage/ball_valid/jump_max/oob "
    "are internal plausibility metrics scored against the versioned per-sport "
    "thresholds in scripts/platformkit/tracking_harness.py (SPORTS). No labeled "
    "ground truth is involved -- these numbers support no accuracy claim and no "
    "edge claim (.claude/rules/no-edge-claims.md)."
)

# Colloquial sport names -> the report-tree directory names (SPORTS keys).
_ALIASES = {"nba": "basketball", "mlb": "baseball", "bball": "basketball",
            "hoops": "basketball", "futbol": "soccer", "nfl": "football"}
_PROV_REL = "data/tracking_reports/provenance.jsonl"
_LEDGER_REL = "data/tracking_reports/ledger.jsonl"


def normalize_sport(name: str | None) -> str | None:
    """Colloquial or canonical sport name -> a SPORTS key, else None."""
    key = (name or "").strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in SPORTS else None


def sport_in_query(query: str) -> str | None:
    """Longest-token-first scan so 'wnba' is not swallowed by 'nba'."""
    low = (query or "").lower()
    for token in sorted(set(SPORTS) | set(_ALIASES), key=len, reverse=True):
        if token in low:
            return normalize_sport(token)
    return None


def _envelope(status: str, sport: str | None, artifact: str, **extra: Any) -> dict:
    return {"status": status, "category": CATEGORY, "sport": sport or "all",
            "source_artifact": artifact, "caveat": CAVEAT, **extra}


def _as_of(paths: list[Path]) -> str | None:
    stamps = [p.stat().st_mtime for p in paths if p.exists()]
    if not stamps:
        return None
    return datetime.fromtimestamp(max(stamps), timezone.utc).isoformat(timespec="seconds")


def _report_paths(reports_dir: Path, sport: str | None = None) -> list[Path]:
    pattern = f"{sport}/*.json" if sport else "*/*.json"
    return sorted(Path(reports_dir).glob(pattern))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _row_game(row: dict) -> str | None:
    for key in ("game_id", "game", "game_name"):
        if isinstance(row.get(key), str):
            return row[key]
    ref = row.get("report_path") or row.get("path")
    return Path(str(ref)).stem if isinstance(ref, str) else None


# ---------------------------------------------------------------------------
# Question shapes
# ---------------------------------------------------------------------------
def scoreboard(sport: str, reports_dir: Path = REPORTS_DIR) -> dict:
    """Per-sport card: games scored, pass rate, metric medians, worst metric."""
    key = normalize_sport(sport)
    art = "data/tracking_reports/{0}/*.json".format(key or sport)
    if key is None:
        return _envelope("no_data", sport, art,
                         note="unknown sport '{0}' -- tracked sports: {1}".format(sport, sorted(SPORTS)))
    paths = _report_paths(reports_dir, key)
    if not paths:
        return _envelope("no_data", key, art,
                         note="no QualityReport on file for '{0}' -- run the footage queue".format(key))
    card = scorecard(key, Path(reports_dir))
    if not card["games_scored"]:
        return _envelope("no_data", key, art,
                         note="report files present but none parsed as a QualityReport")
    scoped = {"coordinate_profile": card.get("coordinate_profile", "court_feet")}
    if "coordinate_profiles" in card:
        scoped["coordinate_profiles"] = card["coordinate_profiles"]
    return _envelope("ok", key, art, as_of=_as_of(paths), thresholds=dict(SPORTS[key]),
                     games_scored=card["games_scored"], pass_rate=card["pass_rate"],
                     metric_medians=card["metric_medians"], worst_metric=card["worst_metric"],
                     trend=card["trend"], games=[p.stem for p in paths], **scoped)


def worst_metric(sport: str, reports_dir: Path = REPORTS_DIR) -> dict:
    """The median metric furthest under its threshold, plus its repair rule."""
    card = scoreboard(sport, reports_dir)
    if card["status"] != "ok":
        return card
    metric = card["worst_metric"]
    if metric is None:
        return {**card, "status": "no_data",
                "note": "no numeric metric present in any report for this sport"}
    return {**card, "worst_metric_median": card["metric_medians"][metric],
            "repair_rule": RULES[metric],
            "note": "worst median metric for {0} is {1} (thresholds: "
                    "tracking_harness.SPORTS)".format(card["sport"], metric)}


def bar_progress(sport: str, reports_dir: Path = REPORTS_DIR, bar: int = GAME_BAR) -> dict:
    """Games on file for a sport against the 10-game evidence bar."""
    card = scoreboard(sport, reports_dir)
    if card["status"] != "ok":
        return card
    scored = card["games_scored"]
    return {**card, "bar": bar, "games_needed": max(0, bar - scored), "bar_met": scored >= bar,
            "note": "{0} of {1} games scored for {2}".format(scored, bar, card["sport"])}


def game_report(game_id: str, sport: str | None = None,
                reports_dir: Path = REPORTS_DIR) -> dict:
    """One game's QualityReport, quoted verbatim."""
    key = normalize_sport(sport) if sport else None
    if sport and key is None:
        return _envelope("no_data", sport, "data/tracking_reports/*/*.json",
                         note="unknown sport '{0}' -- tracked sports: {1}".format(sport, sorted(SPORTS)))
    matches = [p for p in _report_paths(reports_dir, key) if p.stem == game_id]
    art = "data/tracking_reports/{0}/{1}.json".format(key or "<sport>", game_id)
    if not matches:
        return _envelope("no_data", key, art,
                         note="no QualityReport on file for game_id '{0}'".format(game_id))
    if len(matches) > 1:
        return _envelope("ambiguous", key, art, candidates=[p.parent.name for p in matches],
                         note="game_id '{0}' exists under several sports -- pass sport=".format(game_id))
    path = matches[0]
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _envelope("no_data", key, art, note="report unreadable: {0}".format(exc))
    found = row.get("sport") if isinstance(row.get("sport"), str) else path.parent.name
    return _envelope("ok", found, "data/tracking_reports/{0}/{1}".format(path.parent.name, path.name),
                     as_of=_as_of([path]), game_id=game_id, report=row,
                     thresholds=dict(SPORTS.get(path.parent.name, {})))


def changed(game_id: str, reports_dir: Path = REPORTS_DIR) -> dict:
    """Diff the two most recent ledger rows for one game_id -- what moved after
    the last adapter change.  A single scored run cannot show a delta, so this
    fails closed rather than guessing."""
    rows = [r for r in _read_jsonl(Path(reports_dir) / "ledger.jsonl")
            if _row_game(r) == game_id and isinstance(r.get("report"), dict)]
    rows.sort(key=lambda r: str(r.get("ts") or ""))
    if len(rows) < 2:
        return _envelope("no_data", None, _LEDGER_REL, game_id=game_id, runs_found=len(rows),
                         note="need 2 scored runs for '{0}' to show a delta; {1} found in "
                              "{2}".format(game_id, len(rows), _LEDGER_REL))
    before, after = rows[-2]["report"], rows[-1]["report"]
    deltas = {}
    for k in sorted(set(before) & set(after)):
        b, a = before[k], after[k]
        if isinstance(b, bool) or isinstance(a, bool):
            continue
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            deltas[k] = {"before": b, "after": a, "delta": round(a - b, 4)}
    fail_b = set(before.get("failures") or [])
    fail_a = set(after.get("failures") or [])
    return _envelope("ok", after.get("sport") or before.get("sport"), _LEDGER_REL,
                     as_of=rows[-1].get("ts"), game_id=game_id,
                     ts_before=rows[-2].get("ts"), ts_after=rows[-1].get("ts"),
                     adapter_version_before=rows[-2].get("adapter_version"),
                     adapter_version_after=rows[-1].get("adapter_version"),
                     passed_before=bool(before.get("passed")), passed_after=bool(after.get("passed")),
                     metric_deltas=deltas, failures_resolved=sorted(fail_b - fail_a),
                     failures_new=sorted(fail_a - fail_b))


def provenance(game_id: str, reports_dir: Path = REPORTS_DIR) -> dict:
    """Which footage produced this tracking run (latest capture for game_id).
    Absolute video paths are reduced to a basename so envelopes stay clone-portable."""
    rows = [r for r in _read_jsonl(Path(reports_dir) / "provenance.jsonl")
            if r.get("game_id") == game_id]
    if not rows:
        return _envelope("no_data", None, _PROV_REL, game_id=game_id,
                         note="no provenance row for game_id '{0}' in {1}".format(game_id, _PROV_REL))
    rows.sort(key=lambda r: str(r.get("capture_ts") or ""))
    row = rows[-1]
    return _envelope("ok", row.get("sport"), _PROV_REL, as_of=row.get("capture_ts"),
                     game_id=game_id, captures_on_file=len(rows),
                     source_url=row.get("source_url"),
                     video_name=Path(str(row.get("video_path") or "")).name,
                     sha256=row.get("sha256"), size_bytes=row.get("size_bytes"),
                     resolution=row.get("resolution"), fps=row.get("fps"),
                     adapter_module=row.get("adapter_module"),
                     adapter_version=row.get("adapter_version"),
                     thresholds_snapshot=row.get("thresholds_snapshot"))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def _game_in_query(query: str, reports_dir: Path) -> str | None:
    """Match a game_id only against ids that exist on disk -- no NER, no guessing."""
    low = (query or "").lower()
    stems = {p.stem for p in _report_paths(reports_dir)}
    stems |= {r["game_id"] for r in _read_jsonl(Path(reports_dir) / "provenance.jsonl")
              if isinstance(r.get("game_id"), str)}
    hits = [s for s in stems if s and s.lower() in low]
    return max(hits, key=len) if hits else None


_PROV_TOKENS = ("provenance", "footage", "which video", "what video", "source video")
_DELTA_TOKENS = ("changed", "change after", "adapter fix", "since the fix", "regress", "improve after")
_BAR_TOKENS = ("how many games", "bar", "enough games", "toward the")


def resolve(query: str = "", sport: str | None = None, game_id: str | None = None,
            reports_dir: Path = REPORTS_DIR) -> dict:
    """Registry entrypoint: route one tracking question to a question shape."""
    low = (query or "").lower()
    game = game_id or _game_in_query(query, reports_dir)
    if any(t in low for t in _PROV_TOKENS):
        return provenance(game, reports_dir) if game else _envelope(
            "no_data", sport, _PROV_REL, note="name a game_id -- provenance is per-game")
    if any(t in low for t in _DELTA_TOKENS):
        return changed(game, reports_dir) if game else _envelope(
            "no_data", sport, _LEDGER_REL, note="name a game_id -- run-to-run deltas are per-game")
    found_sport = normalize_sport(sport) or sport_in_query(query)
    if found_sport and "worst" in low:
        return worst_metric(found_sport, reports_dir)
    if found_sport and any(t in low for t in _BAR_TOKENS):
        return bar_progress(found_sport, reports_dir)
    # A named game wins over the sport token it usually contains ("tennis_03"),
    # so a per-game lookup is not swallowed by the per-sport scoreboard.
    if game:
        return game_report(game, None, reports_dir)
    if found_sport:
        return scoreboard(found_sport, reports_dir)
    return _envelope("no_data", sport, "data/tracking_reports/*/*.json",
                     note="name a sport {0} or a game_id -- tracking reports are "
                          "per-sport".format(sorted(SPORTS)))


if __name__ == "__main__":
    print(json.dumps(resolve(" ".join(sys.argv[1:])), indent=2, default=str))
