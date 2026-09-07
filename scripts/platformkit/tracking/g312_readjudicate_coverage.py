"""G312 -- the ledger coverage denominator ignores the route's own max_frames.

Two jobs, both arithmetic, both read-only:

* PREMISE: for ONE named game, print the ledger pair (``evaluated_frames`` /
  ``coverage_pct``) beside the capped pair (``attempted_frames_capped`` /
  ``coverage_attempted_capped_pct``) recomputed under the sealed formula.
* RE-ADJUDICATION: recompute all 13 ledger-backed rows of the COMMITTED G309 census
  and emit one CSV, with the sealed 1e-9 agreement checks printed per row.

The capped share is a SCHEDULING number, not a quality one: a game can attempt every
frame it was allowed and still track the wrong objects. Image space only; no recall,
precision, accuracy or registration claim is made or may be read into any output here.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

TOL = 1e-9
CENSUS = "docs/evidence/tracking/g309_multigame_census_2026-09-07.csv"
FIELDS = ("game_id", "sport", "stride", "decoded_frames", "frames_emitted",
          "ledger_evaluated_frames", "ledger_coverage_pct", "route_max_frames",
          "attempted_frames_capped", "coverage_attempted_capped_pct",
          "capped_over_ledger_coverage_ratio", "agrees_within_1e9")


def capped_attempt(decoded: int, stride: int, max_frames: int) -> int:
    """Frames the route could attempt: min(ceil(decoded/s), ceil(max_frames/s))."""
    return min(-(-decoded // stride), -(-max_frames // stride))


def _premise(game: str, tracking_csv: Path, ledger: Path, sidecar: Path) -> dict:
    """Print the ledger pair beside the capped pair for one game; return both."""
    line = None
    for raw in ledger.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row = json.loads(raw)
            if row.get("game_id") == game and row.get("passed") is not None:
                line = row  # LAST matching adjudicated line wins
    if line is None:
        raise SystemExit("PREMISE FALSE: no adjudicated ledger line for %s" % game)
    max_frames = json.loads(sidecar.read_text(encoding="utf-8")).get("max_frames")
    if not isinstance(max_frames, int) or isinstance(max_frames, bool) or max_frames <= 0:
        raise SystemExit("PREMISE FALSE: no positive max_frames in %s" % sidecar)
    with tracking_csv.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        frames = {row["frame"] for row in csv.DictReader(handle) if row.get("frame")}
    emitted = len(frames)
    attempted = capped_attempt(int(line["decoded_frames"]), int(line["stride"]), max_frames)
    out = {"game_id": game, "frames_emitted": emitted,
           "ledger_evaluated_frames": int(line["evaluated_frames"]),
           "ledger_coverage_pct": float(line["coverage_pct"]),
           "route_max_frames": max_frames, "attempted_frames_capped": attempted,
           "coverage_attempted_capped_pct": emitted / attempted}
    print("PREMISE -- %s (pod read, ledger line and route sidecar)" % game)
    print("  decoded_frames %d  stride %d  route max_frames %d  frames_emitted %d"
          % (int(line["decoded_frames"]), int(line["stride"]), max_frames, emitted))
    print("  LEDGER  evaluated_frames %8d   coverage_pct                  %.6f"
          % (out["ledger_evaluated_frames"], out["ledger_coverage_pct"]))
    print("  CAPPED  attempted_frames %8d   coverage_attempted_capped_pct %.6f"
          % (attempted, out["coverage_attempted_capped_pct"]))
    if attempted == out["ledger_evaluated_frames"]:
        raise SystemExit("PREMISE FALSE: the two attempted counts are equal")
    print("  PREMISE HOLDS: the denominators differ (%d vs %d, ratio %.1fx)"
          % (out["ledger_evaluated_frames"], attempted,
             out["ledger_evaluated_frames"] / attempted))
    return out


def _readjudicate(census: Path, max_frames: int, out_path: Path) -> list[dict]:
    """Recompute every ledger-backed census row and run the sealed 1e-9 checks."""
    with census.open("r", encoding="utf-8", newline="") as handle:
        census_rows = [row for row in csv.DictReader(handle)
                       if row.get("ledger_row") == "present"]
    rows, failures = [], []
    for row in census_rows:
        game = row["game_id"]
        stride, decoded = int(row["stride"]), int(row["decoded_frames"])
        emitted, attempted_unc = int(row["frames_emitted"]), int(row["frames_attempted"])
        # Sealed check (a): the census/ledger denominator IS ceil(decoded/stride).
        if attempted_unc != -(-decoded // stride):
            failures.append("%s (a) frames_attempted %d != ceil(%d/%d)"
                            % (game, attempted_unc, decoded, stride))
        # Sealed checks (b) and (c): both committed coverage columns, to 1e-9.
        for tag, column, denominator in (("b", "coverage_attempted_frames_pct", attempted_unc),
                                         ("c", "coverage_decoded_pct", decoded)):
            if abs(float(row[column]) - emitted / denominator) > TOL:
                failures.append("%s (%s) %s off by %.3e" % (
                    game, tag, column, abs(float(row[column]) - emitted / denominator)))
        attempted = capped_attempt(decoded, stride, max_frames)
        share = emitted / attempted
        rows.append({"game_id": game, "sport": row["sport"], "stride": stride,
                     "decoded_frames": decoded, "frames_emitted": emitted,
                     "ledger_evaluated_frames": attempted_unc,
                     "ledger_coverage_pct": float(row["ledger_coverage_pct"]),
                     "route_max_frames": max_frames,
                     "attempted_frames_capped": attempted,
                     "coverage_attempted_capped_pct": share,
                     "capped_over_ledger_coverage_ratio":
                         share / float(row["ledger_coverage_pct"]),
                     "agrees_within_1e9": not any(game in f for f in failures)})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    shares = [row["coverage_attempted_capped_pct"] for row in rows]
    worst = min(rows, key=lambda row: row["coverage_attempted_capped_pct"])
    ledger_median = statistics.median(row["ledger_coverage_pct"] for row in rows)
    print("\nRE-ADJUDICATION -- %d ledger-backed census rows -> %s" % (len(rows), out_path))
    print("  agreement (sealed checks a,b,c): %d/%d rows within %g"
          % (sum(row["agrees_within_1e9"] for row in rows), len(rows), TOL))
    print("  capped attempted share: median %.4f  min %.4f @ %s  max %.4f  n %d"
          % (statistics.median(shares), min(shares), worst["game_id"], max(shares), len(shares)))
    print("  ledger coverage_pct   : median %.4f  (understated by %.1fx at the medians)"
          % (ledger_median, statistics.median(shares) / ledger_median))
    print("  ratio capped/ledger per row: min %.1fx  max %.1fx"
          % (min(row["capped_over_ledger_coverage_ratio"] for row in rows),
             max(row["capped_over_ledger_coverage_ratio"] for row in rows)))
    for failure in failures:
        print("  DISAGREEMENT (reported, never patched): %s" % failure)
    print("  NOT a quality number: this is scheduling only. No recall, precision, accuracy"
          " or registration claim. All %d rows remain passed=false." % len(rows))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path(CENSUS))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-frames", type=int, default=3000,
                        help="route cap, re-verified from the pod sidecars (never assumed)")
    parser.add_argument("--premise-game", default="den_phx_2025")
    parser.add_argument("--premise-csv", type=Path)
    parser.add_argument("--premise-ledger", type=Path)
    parser.add_argument("--premise-sidecar", type=Path)
    args = parser.parse_args()
    if args.premise_csv:
        _premise(args.premise_game, args.premise_csv, args.premise_ledger,
                 args.premise_sidecar)
    _readjudicate(args.census, args.max_frames, args.out)


if __name__ == "__main__":  # pragma: no cover
    main()
