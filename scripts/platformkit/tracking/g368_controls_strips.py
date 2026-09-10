"""G368 -- synthetic controls (K1, K2) and the 10 evenly spaced eye-check strips.

Split out of g368_tick_motion.py to keep both files under the 300-line rail.
Sealed definitions: prereg sections 7 and 10. Imports of the core happen inside
the functions so the two modules can refer to each other without a cycle.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

STRIP_N = 10
STRIPS_MAX_BYTES = 200 * 1024
PLANT_LEN = 30
PLANT_START = 10
N_TICKS = 60
N_TRACKS = 5
STRIDE = 6
BALL_COLS = ["frame", "timestamp", "ball_x2d", "ball_y2d", "detected", "live",
             "ball_inferred", "ball_x2d_px", "ball_y2d_px"]


def _row(tick: int, track: int, x: int, y: int, confidence: str) -> dict:
    """One synthetic player row carrying exactly the columns the real table carries."""
    return {"frame": tick * STRIDE, "player_id": track, "x_position": x, "y_position": y,
            "confidence": confidence, "bbox_x1": x - 20, "bbox_y1": y - 40,
            "bbox_x2": x + 20, "bbox_y2": y + 40}


def synthetic(plant: bool) -> pd.DataFrame:
    """K1 (plant=False): every track moves every tick. K2 (plant=True): one 30-tick coast."""
    rows = []
    for tick in range(N_TICKS):
        for track in range(N_TRACKS):
            x, y = 100 + 7 * tick + 13 * track, 200 + 11 * tick + 5 * track
            confidence = "1.0"
            if plant and track == 3 and PLANT_START <= tick < PLANT_START + PLANT_LEN:
                held = tick - PLANT_START
                x, y = 100 + 7 * PLANT_START + 13 * track, 200 + 11 * PLANT_START + 5 * track
                if held:  # the first planted row is the real detection that starts the run
                    confidence = str(round(max(0.0, 1.0 - min(held, 15) / 15), 3))
            rows.append(_row(tick, track, x, y, confidence))
    return pd.DataFrame(rows)


def synthetic_ball(plant: bool) -> pd.DataFrame:
    """The K2 companion ball table: a 30-tick carry-over flagged by the real G320 flag."""
    rows = []
    for tick in range(N_TICKS):
        x, y = 500 + 9 * tick, 300 + 3 * tick
        inferred = 0
        if plant and PLANT_START <= tick < PLANT_START + PLANT_LEN:
            x, y = 500 + 9 * PLANT_START, 300 + 3 * PLANT_START
            inferred = int(tick > PLANT_START)
        rows.append({"frame": tick * STRIDE, "timestamp": round(tick * 0.1, 3),
                     "ball_x2d": x, "ball_y2d": y, "detected": 1, "live": 1,
                     "ball_inferred": inferred, "ball_x2d_px": x // 5, "ball_y2d_px": y // 5})
    return pd.DataFrame(rows, columns=BALL_COLS)


def ball_carry_share(ball: pd.DataFrame) -> tuple[int, float]:
    """Held ball steps attributed to P7 (unified_pipeline.py:1977) by `ball_inferred`."""
    held = (ball["ball_x2d"].astype(str).eq(ball["ball_x2d"].astype(str).shift(1))
            & ball["ball_y2d"].astype(str).eq(ball["ball_y2d"].astype(str).shift(1)))
    steps = int(held.sum())
    flagged = int((held & ball["ball_inferred"].astype(str).eq("1")).sum())
    return steps, (flagged / steps if steps else 0.0)


def ledger_records(path: Path) -> dict:
    """Latest ledger record per section -- the landed G359 reader, reused as-is."""
    from scripts.platformkit.tracking.g359_held_position import latest_ledger_records
    return latest_ledger_records(path) if path.exists() else {}


def sidecar_evaluated(section_dir: Path) -> str:
    """The section's own evaluated_frame_count.json count; blank when absent."""
    path = section_dir / "evaluated_frame_count.json"
    if not path.exists():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("evaluated_frames", ""))
    except (ValueError, OSError):
        return ""


def write_table(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def cmd_controls(args) -> None:
    """K1 and K2 with the exact required values; a FAIL stops the row before scoring."""
    from scripts.platformkit.tracking import g368_tick_motion as core
    scratch = Path(args.scratch)
    checks = []
    k1 = core.load(write_table(synthetic(False), scratch / "k1" / "tracking_data.csv"))
    k1_census = core.census(k1)
    checks.append(("K1_MOTION_SHARE", core._f(1.0), core._f(core.motion_of(k1)["motion_share"])))
    checks.append(("K1_HELD_RUNS", core._i(0), k1_census["held_runs_n"]))
    checks.append(("K1_HELD_STEPS", core._i(0), k1_census["held_steps_n"]))

    k2 = core.load(write_table(synthetic(True), scratch / "k2" / "tracking_data.csv"))
    k2_census = core.census(k2)
    steps = core.classify(k2)
    steps = steps.loc[steps.ne("")]
    coast = int((steps == "COAST_LOST").sum())
    checks.append(("K2_HELD_RUNS", core._i(1), k2_census["held_runs_n"]))
    checks.append(("K2_RUN_LEN_MAX", core._i(PLANT_LEN), k2_census["run_len_max"]))
    checks.append(("K2_HELD_STEPS", core._i(PLANT_LEN - 1), k2_census["held_steps_n"]))
    checks.append(("K2_COAST_LOST_SHARE", core._f(1.0),
                   core._f(coast / len(steps) if len(steps) else 0.0)))
    checks.append(("K2_UNATTRIBUTED", core._i(0), core._i(int((steps == "UNATTRIBUTED").sum()))))

    ball = synthetic_ball(True)
    write_table(ball, scratch / "k2" / "ball_tracking.csv")
    ball_steps, ball_share = ball_carry_share(ball)
    checks.append(("K2_BALL_HELD_STEPS", core._i(PLANT_LEN - 1), core._i(ball_steps)))
    checks.append(("K2_BALL_P7_SHARE", core._f(1.0), core._f(ball_share)))

    rows = [{"control": name, "required": required, "observed": observed,
             "verdict": "PASS" if required == observed else "FAIL"}
            for name, required, observed in checks]
    core.write(Path(args.out), rows, False)
    failed = [row["control"] for row in rows if row["verdict"] == "FAIL"]
    print("CONTROLS n={} failed={}".format(len(rows), ",".join(failed) or "none"))
    if failed:
        raise SystemExit("a failing control stops the row before any corpus is scored")


def pick_sections(names: list[str]) -> list[str]:
    """Ten evenly spaced indices over the ordered set -- never a head slice (A3)."""
    ordered = sorted(names)
    if len(ordered) <= STRIP_N:
        return ordered
    return [ordered[len(ordered) * index // STRIP_N] for index in range(STRIP_N)]


def pick_track(table: pd.DataFrame) -> str:
    """The track with the most rows; ties break to the smallest player_id string."""
    counts = table["player_id"].value_counts()
    best = counts.max()
    return sorted(str(name) for name, value in counts.items() if value == best)[0]


def _polyline(values: list[float], ranks: list[int], top: int, width: int, height: int) -> str:
    span = max(ranks) or 1
    low, high = min(values), max(values)
    scale = (high - low) or 1.0
    points = " ".join(
        "{:.1f},{:.1f}".format(rank * width / span, top + height - (value - low) * height / scale)
        for rank, value in zip(ranks, values))
    return '<polyline fill="none" stroke="#1a1a1a" stroke-width="1" points="{}"/>'.format(points)


def strip_svg(table: pd.DataFrame, track: str, section: str) -> str:
    """One track's x and y against the evaluated tick, with held runs shaded behind."""
    from scripts.platformkit.tracking import g368_tick_motion as core
    one = table.loc[table["player_id"].astype(str) == track]
    ranks = [int(value) for value in one["_rank"].tolist()]
    held = core.held_flag(one).tolist()
    width, height = 620, 70
    bands = "".join(
        '<rect x="{:.1f}" y="0" width="{:.1f}" height="170" fill="#d8d8d8"/>'.format(
            ranks[index - 1] * width / (max(ranks) or 1),
            max((ranks[index] - ranks[index - 1]) * width / (max(ranks) or 1), 1.0))
        for index in range(1, len(ranks)) if held[index])
    body = "".join(
        _polyline([float(value) for value in one[column].tolist()], ranks, top, width, height)
        for column, top in (("x_position", 10), ("y_position", 95)))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="180" '
            'viewBox="0 0 {} 180">{}{}<text x="4" y="176" font-size="9">{} track {} '
            'x top y bottom held shaded</text></svg>\n').format(
                width, width, bands, body, section, track)


def cmd_strips(args) -> None:
    """Ten evenly spaced strips over the corpus, plus a manifest; refuses over 200 KB."""
    from scripts.platformkit.tracking import g368_tick_motion as core
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(args.tracking_root)
    names = [name for name, _digest in core.section_rows(Path(args.sections))]
    manifest = []
    for section in pick_sections(names):
        path = root / section / "tracking_data.csv"
        if not path.exists():
            print("ABSENT-SECTION {}".format(section))
            continue
        table = core.load(path)
        track = pick_track(table)
        target = out / "{}.svg".format(section)
        target.write_text(strip_svg(table, track, section), encoding="ascii")
        manifest.append({"section_name": section, "corpus": args.corpus, "track_id": track,
                         "svg": target.name, "bytes": target.stat().st_size})
    if not manifest:
        raise SystemExit("no strip section resolved under {}".format(root))
    with (out / "manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)
    total = sum(path.stat().st_size for path in out.iterdir())
    print("STRIPS n={} total_bytes={} cap={}".format(len(manifest), total, STRIPS_MAX_BYTES))
    if total > STRIPS_MAX_BYTES:
        raise SystemExit("strips exceed the sealed 200 KB cap; observed {}".format(total))


def cmd_summary(args) -> None:
    """Aggregate the landed CSVs into summary.json; quantiles are nearest-rank."""
    from scripts.platformkit.tracking import g368_tick_motion as core
    evidence = Path(args.evidence)
    out = {"prereg": "g368_prereg_2026-09-09.md",
           "bars": {"premise_motion_min": core.PREMISE_MOTION_MIN,
                    "attribution": core.ATTRIBUTION_BAR,
                    "proposal_trigger": core.PROPOSAL_TRIGGER}}
    for stem, fields in (("motion", ["motion_share"]),
                         ("consequence", ["coast_row_share", "motion_share_no_coast"]),
                         ("held_runs", ["tick_share_in_runs_ge2", "tick_share_in_runs_ge30"])):
        path = evidence / "{}.csv".format(stem)
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        for corpus in sorted(set(frame["corpus"])):
            block = frame.loc[frame["corpus"] == corpus]
            for field in fields:
                values = [float(value) for value in block.get(field, []) if value != ""]
                out.setdefault(corpus, {})[field] = {
                    "n": len(values), "p10": core.nearest(values, 0.10),
                    "p50": core.nearest(values, 0.50), "p90": core.nearest(values, 0.90)}
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("SUMMARY {}".format(args.out))
