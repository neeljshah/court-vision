"""G366 fresh-set census, even sample, evaluated-tick audit and eye-check strips.

Sealed definitions: `docs/evidence/tracking/g366_gate_confirmation_2026-09-09/
g366_prereg_2026-09-09.md`. The ledger snapshot, the archived tables and the landed
G358 / G359 modules are the only inputs; nothing under `data/` is written.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "2")

import pandas as pd  # noqa: E402

from scripts.platformkit.tracking.g358_gate_execution import _sha256, load_merged  # noqa: E402
from scripts.platformkit.tracking.g359_held_position import (  # noqa: E402
    _f, _i, _write, collapse_held, latest_ledger_records)
from scripts.platformkit.tracking.production_schema_adapter import (  # noqa: E402
    _frame_size, adapt_production_section)

FRESH_EPOCH = 1788976020          # 2026-09-09T17:47:00Z, the daemon relaunch
MIN_UNIQUE_FRAMES = 150
SECTION_ID = re.compile(r"\A[A-Za-z0-9_-]{11}_s[0-9]+\Z")
SAMPLE_TARGET = 30
STRIP_TARGET = 10
STRIP_MAX_BYTES = 200 * 1024
POOL = "FRESH_POST_RELAUNCH"
LEDGER_COLUMNS = ("sport", "status", "finished_at", "rows", "decoded_frames",
                  "evaluated_frames", "stride", "source_fps", "source_resolution")
CENSUS_COLUMNS = ("section_name", "game_id", "offset_s", "pool", *LEDGER_COLUMNS,
                  "unique_frames", "frame_size_source", "tracking_path", "tracking_sha256",
                  "tracking_bytes", "ball_path", "ball_sha256", "ball_bytes",
                  "eligible", "ineligible_reason", "selected", "select_index")
TICK_COLUMNS = ("section_name", "ledger_decoded_frames", "ledger_evaluated_frames",
                "ledger_stride", "implied_stride", "m0_player_frames", "m1_player_frames",
                "m1_player_rows", "held_rows_dropped", "ratio_vs_evaluated",
                "ratio_vs_decoded_over_stride")


def even_indices(n: int, target: int) -> list[int]:
    """Every k-th index with k = max(n // target, 1); spans the whole range (B7)."""
    k = max(n // target, 1) if n > 0 else 1
    return [i for i in range(n) if i % k == 0]


def even_pick(items: list, count: int) -> list:
    """Exactly `count` items spanning the ordered set, last member always included."""
    if len(items) <= count or count < 2:
        return list(items)
    step = (len(items) - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]


def _frames_and_size(path: Path) -> tuple[int, str]:
    """Distinct `frame` count and the landed adapter's frame-size provenance."""
    wanted = ("frame", "x_position", "y_position", "x_norm", "y_norm")
    present = [c for c in wanted if c in pd.read_csv(path, nrows=0).columns]
    if "frame" not in present:
        return 0, "absent"
    table = pd.read_csv(path, usecols=present)
    frames = int(table["frame"].nunique())
    if not {"x_position", "y_position"}.issubset(present):
        return frames, "absent"
    return frames, _frame_size(table, None)[2]


def _eligibility(name: str, record: dict, sealed_sections: set, sealed_games: set,
                 sections_dir: Path) -> tuple[str, str, str]:
    """Sealed ladder, in order; an empty reason means the snapshot checks passed."""
    if not SECTION_ID.match(name):
        return "not_source_pinnable", "", ""
    game, offset = name.rsplit("_s", 1)
    if int(record.get("finished_at") or 0) < FRESH_EPOCH:
        return "not_fresh", game, offset
    if record.get("status") != "tracked":
        return "status_not_tracked", game, offset
    if name in sealed_sections:
        return "section_in_sealed_set", game, offset
    if game in sealed_games:
        return "game_in_sealed_set", game, offset
    directory = sections_dir / name
    if not ((directory / "tracking_data.csv").exists()
            and (directory / "ball_tracking.csv").exists()):
        return "tables_absent", game, offset
    return "", game, offset


def _file_checks(directory: Path, row: dict[str, str]) -> str:
    """Steps 7-8 of the ladder; fills the measured and pinning cells (A9)."""
    tracking, ball = directory / "tracking_data.csv", directory / "ball_tracking.csv"
    frames, size_source = _frames_and_size(tracking)
    row["unique_frames"], row["frame_size_source"] = _i(frames), size_source
    if frames < MIN_UNIQUE_FRAMES:
        return "unique_frames_below_minimum"
    if "ball_x2d_px" not in pd.read_csv(ball, nrows=0).columns:
        return "ball_px_absent"
    row.update({"tracking_path": str(tracking.resolve()), "tracking_sha256": _sha256(tracking),
                "tracking_bytes": _i(tracking.stat().st_size),
                "ball_path": str(ball.resolve()), "ball_sha256": _sha256(ball),
                "ball_bytes": _i(ball.stat().st_size)})
    return ""


def census(ledger: Path, sections_dir: Path, sealed: Path, out: Path) -> list[dict[str, str]]:
    """One archived row per ledger section, eligible or not, with its reason."""
    sealed_table = pd.read_csv(sealed, dtype=str)
    sealed_sections, sealed_games = set(sealed_table["section_name"]), set(sealed_table["game_id"])
    rows: list[dict[str, str]] = []
    for name, record in sorted(latest_ledger_records(ledger).items()):
        reason, game, offset = _eligibility(name, record, sealed_sections, sealed_games,
                                            sections_dir)
        row = dict.fromkeys(CENSUS_COLUMNS, "")
        row.update({"section_name": name, "game_id": game, "offset_s": offset, "pool": POOL})
        row.update({key: ("" if record.get(key) is None else str(record[key]))
                    for key in LEDGER_COLUMNS})
        if not reason:
            reason = _file_checks(sections_dir / name, row)
        row["eligible"], row["ineligible_reason"] = ("0" if reason else "1"), reason
        rows.append(row)
    _write(out, rows)
    eligible = [row for row in rows if row["eligible"] == "1"]
    print("census n={} eligible={} games={}".format(
        len(rows), len(eligible), len({row["game_id"] for row in eligible})))
    return rows


def sample(sections: Path) -> list[dict[str, str]]:
    """Additive `selected` / `select_index` columns under the sealed every-k-th rule."""
    with sections.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    eligible = sorted((row for row in rows if row["eligible"] == "1"),
                      key=lambda row: (row["game_id"], row["section_name"]))
    chosen = {eligible[index]["section_name"]: order
              for order, index in enumerate(even_indices(len(eligible), SAMPLE_TARGET))}
    for row in rows:
        order = chosen.get(row["section_name"]) if row["eligible"] == "1" else None
        row["selected"] = "1" if order is not None else "0"
        row["select_index"] = _i(order) if order is not None else ""
    _write(sections, rows)
    games = {row["game_id"] for row in rows if row["selected"] == "1"}
    print("sample eligible={} selected={} games={}".format(len(eligible), len(chosen), len(games)))
    return rows


def selected_rows(sections: Path) -> list[dict[str, str]]:
    with sections.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("selected") == "1"]
    if not rows:
        raise ValueError("no selected sections in {}; run `sample` first".format(sections))
    return sorted(rows, key=lambda row: int(row["select_index"]))


def adapted_section(sections_dir: Path, name: str):
    return adapt_production_section(load_merged(sections_dir / name / "tracking_data.csv",
                                                sections_dir / name / "ball_tracking.csv"))


def _player_frames(table: pd.DataFrame) -> int:
    return int(table.loc[table["cls"].eq("player"), "frame"].nunique())


def ticks(sections: Path, sections_dir: Path, ledger: Path, out: Path) -> list[dict[str, str]]:
    """M1 surviving player ticks against the producer's own evaluated-frame count."""
    records = latest_ledger_records(ledger)
    rows: list[dict[str, str]] = []
    for row in selected_rows(sections):
        name = row["section_name"]
        table = adapted_section(sections_dir, name).table
        collapsed, dropped = collapse_held(table)
        record = records.get(name, {})
        evaluated = int(record.get("evaluated_frames") or 0)
        decoded, stride = int(record.get("decoded_frames") or 0), int(record.get("stride") or 0)
        m1_frames = _player_frames(collapsed)
        implied = decoded / evaluated if decoded and evaluated else None
        by_stride = decoded / stride if decoded and stride else None
        rows.append({"section_name": name, "ledger_decoded_frames": _i(decoded),
                     "ledger_evaluated_frames": _i(evaluated), "ledger_stride": _i(stride),
                     "implied_stride": _f(implied) if implied else "",
                     "m0_player_frames": _i(_player_frames(table)),
                     "m1_player_frames": _i(m1_frames),
                     "m1_player_rows": _i(int(collapsed["cls"].eq("player").sum())),
                     "held_rows_dropped": _i(dropped),
                     "ratio_vs_evaluated": _f(m1_frames / evaluated) if evaluated else "",
                     "ratio_vs_decoded_over_stride": _f(m1_frames / by_stride) if by_stride else ""})
    _write(out, [{key: row[key] for key in TICK_COLUMNS} for row in rows])
    ratios = [float(row["ratio_vs_evaluated"]) for row in rows if row["ratio_vs_evaluated"]]
    median = float(pd.Series(ratios).median()) if ratios else 0.0
    print("ticks n={} with_ratio={} median_ratio={}".format(len(rows), len(ratios), _f(median)))
    return rows


def busiest_track(table: pd.DataFrame):
    """The player track with the most rows; ties go to the smallest sorted id."""
    counts = table.loc[table["cls"].eq("player")].groupby("track_id").size()
    if counts.empty:
        raise ValueError("section carries no player rows")
    return sorted(track for track, n in counts.items() if n == counts.max())[0]


def _track_frames(table: pd.DataFrame, track) -> list[int]:
    rows = table.loc[table["cls"].eq("player") & table["track_id"].eq(track), "frame"]
    return sorted(int(value) for value in rows.unique())


def strip_svg(name: str, track, m0: list[int], m1: list[int]) -> str:
    """One strip: the M0 rows of a track over the frame axis, M1 ticks beneath it."""
    lo, hi = min(m0), max(m0)
    span = max(hi - lo, 1)

    def marks(frames: list[int], top: int) -> str:
        return "".join("M{:.1f} {}V{}".format(44 + 920 * (f - lo) / span, top, top + 18)
                       for f in frames)
    label = "{} track {} frames {}-{} M0 n={} M1 n={}".format(name, track, lo, hi, len(m0), len(m1))
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='980' height='110'>"
            "<rect width='980' height='110' fill='#ffffff'/>"
            "<text x='10' y='16' font-family='monospace' font-size='11'>{}</text>"
            "<text x='10' y='42' font-family='monospace' font-size='10'>M0</text>"
            "<text x='10' y='82' font-family='monospace' font-size='10'>M1</text>"
            "<path d='{}' stroke='#222222' stroke-width='1'/>"
            "<path d='{}' stroke='#222222' stroke-width='1'/></svg>").format(
                label, marks(m0, 26), marks(m1, 66))


def strips(sections: Path, sections_dir: Path, out_dir: Path) -> list[str]:
    """Exactly STRIP_TARGET strips, evenly spread over the selected set (B7)."""
    picks = even_pick(selected_rows(sections), STRIP_TARGET)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for row in picks:
        name = row["section_name"]
        table = adapted_section(sections_dir, name).table
        collapsed, _ = collapse_held(table)
        track = busiest_track(table)
        payload = strip_svg(name, track, _track_frames(table, track),
                            _track_frames(collapsed, track)).encode("ascii")
        if len(payload) > STRIP_MAX_BYTES:
            raise ValueError("strip {} is {} bytes, above the sealed bar".format(name, len(payload)))
        (out_dir / (name + ".svg")).write_bytes(payload)
        written.append(name)
    print("strips n={} dir={}".format(len(written), out_dir))
    return written


SUBCOMMANDS = (("census", ("--ledger", "--sections-dir", "--sealed", "--out")),
               ("sample", ("--sections",)),
               ("ticks", ("--sections", "--sections-dir", "--ledger", "--out")),
               ("strips", ("--sections", "--sections-dir", "--out-dir")))


def main() -> None:
    parser = argparse.ArgumentParser(description="G366 fresh set, tick audit, strips")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, options in SUBCOMMANDS:
        child = sub.add_parser(name)
        for option in options:
            child.add_argument(option, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "census":
        census(args.ledger, args.sections_dir, args.sealed, args.out)
    elif args.command == "sample":
        sample(args.sections)
    elif args.command == "ticks":
        ticks(args.sections, args.sections_dir, args.ledger, args.out)
    else:
        strips(args.sections, args.sections_dir, args.out_dir)


if __name__ == "__main__":
    main()
