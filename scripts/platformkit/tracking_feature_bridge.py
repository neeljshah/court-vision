"""Carry per-game CV tracking features into the signal foundry, leak-safe.

Walks ``data/tracking_reports/<sport>/<game_id>.json`` (the QualityReport
written by ``tracking_harness``) beside ``data/tracking/<game_id>/
tracking_data.csv``, asks whichever per-sport feature module exists for that
game's descriptive features, then converts them to AS-OF team-level rolling
means before anything downstream may see them.

Honest scope
------------
* A row appears ONLY for a game that has BOTH a tracking CSV and a matching
  QualityReport.  Everything else is absent, not zero.
* A sport with no importable feature module is SKIPPED and NAMED in the
  output (``frame.attrs["skipped_sports"]``), never silently dropped.
* The raw per-game values never leave :func:`to_asof_team_features`.  Only
  ``shift(1)``-then-roll columns survive, so a game cannot see itself.  That
  is leak safety by construction, not by later inspection.
* These features are DESCRIPTIVE.  Nothing here has been shown to add
  predictive lift; that verdict belongs to the foundry, not this bridge.

Run: ``python -m scripts.platformkit.tracking_feature_bridge``
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Callable, Iterator, Sequence

import pandas as pd

from scripts.platformkit.signal_foundry import REGISTRY, SignalSpec, register
from scripts.platformkit.tracking_features import _game_key

# These two suffixes are the ONLY names this module emits, because they are on
# the leak-contract whitelist in scripts/platformkit/signal_ensemble.py
# (``_extra_numeric._ASOF``).  A raw same-game column would be rejected there,
# and rightly so -- keep it that way.
L5_SUFFIX = "_l5"
ASOF_SUFFIX = "_asof"
L5_WINDOW = 5

TRACKING_FILE = "tracking_data.csv"
KEYS = ("sport", "game_id")
TEAM_KEYS = ("sport", "team", "game_id", "date")
OUTPUT_NAME = "tracking_features_asof.parquet"

# Sport label (the QualityReport ``sport`` field / report directory name) ->
# "module:function".  The callable takes one tracking CSV path and returns a
# single-row frame of per-game features.  Entries whose module does not exist
# yet are intentional: they name the gap instead of hiding it.
FEATURE_MODULES: dict[str, str] = {
    "basketball": "domains.basketball_nba.tracking.screen_features:game_features",
    "wnba": "domains.basketball_wnba.tracking.screen_features:game_features",
    "soccer": "domains.soccer.tracking.game_features:game_features",
    "tennis": "domains.tennis.tracking.game_features:game_features",
    "baseball": "domains.baseball.tracking.game_features:game_features",
    "football": "domains.football.tracking.game_features:game_features",
}


def _load_feature_fn(sport: str) -> Callable[[Path], pd.DataFrame] | None:
    """Import a sport's feature entry point, or return None if it is absent."""
    target = FEATURE_MODULES.get(sport)
    if not target:
        return None
    module_name, _, attribute = target.partition(":")
    try:
        return getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError):
        return None


def _iter_reports(reports_dir: Path) -> Iterator[tuple[str, str, Path]]:
    """Yield ``(sport, game_id, report_path)`` for every readable report."""
    for path in sorted(reports_dir.glob("*/*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(report, dict):
            continue
        sport = str(report.get("sport") or path.parent.name)
        yield sport, path.stem, path


def collect_game_features(reports_dir: str | Path,
                          tracking_root: str | Path) -> pd.DataFrame:
    """Collect one descriptive feature row per (sport, game_id) that has both.

    ``frame.attrs`` carries the honest bookkeeping: ``skipped_sports`` (sport
    -> number of games whose feature module could not be imported),
    ``missing_tracking`` (reported games with no tracking CSV) and
    ``failed_games`` (games whose feature computation raised).
    """
    reports_dir, tracking_root = Path(reports_dir), Path(tracking_root)
    rows: list[dict[str, object]] = []
    skipped: dict[str, int] = {}
    missing: list[str] = []
    failed: list[str] = []
    functions: dict[str, Callable[[Path], pd.DataFrame] | None] = {}

    for sport, game_id, _report_path in _iter_reports(reports_dir):
        csv_path = tracking_root / game_id / TRACKING_FILE
        if not csv_path.is_file():
            missing.append(game_id)
            continue
        if sport not in functions:
            functions[sport] = _load_feature_fn(sport)
        compute = functions[sport]
        if compute is None:
            skipped[sport] = skipped.get(sport, 0) + 1
            continue
        try:
            features = compute(csv_path)
        except (ValueError, KeyError, TypeError, OSError, pd.errors.ParserError):
            failed.append(game_id)
            continue
        if features is None or len(features) == 0:
            failed.append(game_id)
            continue
        row: dict[str, object] = {"sport": sport, "game_id": game_id}
        row.update(features.iloc[0].to_dict())
        rows.append(row)

    if rows:
        frame = pd.DataFrame(rows).drop_duplicates(subset=list(KEYS))
        frame = frame.sort_values(list(KEYS), kind="mergesort").reset_index(drop=True)
    else:
        frame = pd.DataFrame(columns=list(KEYS))
    frame.attrs["skipped_sports"] = dict(sorted(skipped.items()))
    frame.attrs["missing_tracking"] = sorted(missing)
    frame.attrs["failed_games"] = sorted(failed)
    return frame


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return the numeric per-game feature columns of a collected frame."""
    return [name for name in frame.columns
            if name not in KEYS and pd.api.types.is_numeric_dtype(frame[name])]


def _empty_team_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(columns=list(TEAM_KEYS))
    result.attrs.update(frame.attrs)
    return result


def to_asof_team_features(frame: pd.DataFrame,
                          dates: pd.DataFrame) -> pd.DataFrame:
    """Convert per-game features to AS-OF team-level rolling means.

    ``dates`` is the long-form game-to-team map with columns ``game_id``,
    ``date`` and ``team`` -- normally two rows per game.  A per-game tracking
    feature is not attributable to a team on its own, so the caller must
    supply that map; guessing it would be a silent correctness bug.

    For every team the value is ``shift(1)`` first, then rolled: an L5 mean
    (``<feature>_l5``) and an expanding mean (``<feature>_asof``).  The raw
    same-game columns are dropped, so no row can contain its own game.
    """
    dates = pd.DataFrame(dates)
    absent = sorted({"game_id", "date", "team"}.difference(dates.columns))
    if absent:
        raise ValueError("dates is missing columns: %s" % ", ".join(absent))
    names = feature_columns(frame)
    if frame.empty or not names:
        return _empty_team_frame(frame)

    merged = frame.merge(dates[["game_id", "date", "team"]], on="game_id",
                         how="inner", validate="one_to_many")
    if merged.empty:
        return _empty_team_frame(frame)
    merged["date"] = pd.to_datetime(merged["date"], errors="raise")
    merged = merged.sort_values(["sport", "team", "date", "game_id"],
                                kind="mergesort").reset_index(drop=True)

    result = merged[list(TEAM_KEYS)].copy()
    grouped = merged.groupby(["sport", "team"], sort=False)
    for name in names:
        result[name + L5_SUFFIX] = grouped[name].transform(
            lambda values: values.shift(1).rolling(L5_WINDOW, min_periods=1).mean())
        result[name + ASOF_SUFFIX] = grouped[name].transform(
            lambda values: values.shift(1).expanding().mean())
    result.attrs.update(frame.attrs)
    return result


def assert_leak_contract(frame: pd.DataFrame) -> None:
    """Fail loudly if any non-key column is not an as-of/rolling column."""
    offenders = [name for name in frame.columns
                 if name not in TEAM_KEYS
                 and not name.endswith((L5_SUFFIX, ASOF_SUFFIX))]
    if offenders:
        raise ValueError("Non-as-of columns would leak: %s" % ", ".join(offenders))


def asof_columns(frame: pd.DataFrame) -> list[str]:
    """Return the as-of feature columns of a team-level frame."""
    return [name for name in frame.columns
            if name not in TEAM_KEYS and name.endswith((L5_SUFFIX, ASOF_SUFFIX))]


def register_signals(frame: pd.DataFrame,
                     grain: str = "team_game") -> list[SignalSpec]:
    """Register each as-of column as a foundry SignalSpec, once per sport."""
    assert_leak_contract(frame)
    specs: list[SignalSpec] = []
    sports: Sequence[str] = sorted(str(x) for x in frame["sport"].dropna().unique())
    for sport in sports:
        for name in asof_columns(frame):
            key = "%s_%s" % (sport, name)
            if key in REGISTRY:
                specs.append(REGISTRY[key])
                continue
            specs.append(register(SignalSpec(
                key, sport, grain,
                "as-of team rolling mean of a descriptive tracking feature; "
                "unvalidated until the foundry grades it", name)))
    return specs


def game_team_dates(schedule_dir: Path) -> pd.DataFrame:
    """Build the long-form game_id/date/team map from NBA schedule JSON."""
    rows: list[dict[str, str]] = []
    for path in sorted(Path(schedule_dir).glob("schedule_*_v2.json")):
        parts = path.stem.split("_")
        if len(parts) < 2:
            continue
        for game in json.loads(path.read_text(encoding="utf-8")):
            rows.append({"game_id": _game_key(game["game_id"]),
                         "date": str(game["date"]), "team": parts[1]})
    return pd.DataFrame(rows, columns=["game_id", "date", "team"]).drop_duplicates()


def main() -> None:
    """Collect, convert to as-of team features, and write the parquet."""
    root = Path(os.environ.get("NBA_DATA_ROOT", "data"))
    frame = collect_game_features(root / "tracking_reports", root / "tracking")
    for sport, count in frame.attrs["skipped_sports"].items():
        print("SKIPPED sport=%s games=%d reason=no feature module" % (sport, count))
    print("collected rows=%d missing_tracking=%d failed=%d" % (
        len(frame), len(frame.attrs["missing_tracking"]),
        len(frame.attrs["failed_games"])))
    asof = to_asof_team_features(frame, game_team_dates(root / "nba" / "schedule"))
    assert_leak_contract(asof)
    output = root / "ab_reports" / OUTPUT_NAME
    output.parent.mkdir(parents=True, exist_ok=True)
    asof.to_parquet(output, index=False)
    print("Wrote %d as-of team rows to %s" % (len(asof), output))


if __name__ == "__main__":
    main()
