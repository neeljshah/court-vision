"""G367 paired noise sweep with labelled and modulo recovery columns."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g365_refine_b as rb
from scripts.platformkit.tracking import g365_sweep as sw
from scripts.platformkit.tracking import g365_sweep_b as sb
from scripts.platformkit.tracking import g367_symmetry as sym
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS

SIGMAS, NOISY_DRAWS, PREFIX = (0.0, 0.25, 0.5, 1.0), 30, "G367"
HEADER = ("geometry,sigma_px,draw,seed,baseline_labelled_gap_px,baseline_modulo_gap_px,"
          "baseline_element,candidate_b_labelled_gap_px,candidate_b_modulo_gap_px,"
          "candidate_b_element,n_supports,n_kept,rounds_run,n_fev,status")


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER.split(","))
        writer.writeheader()
        writer.writerows(rows)


def _one(truth: np.ndarray, name: str, sigma: float, draw: int) -> dict:
    seed = sw.seed_of(name, sigma, draw, prefix=PREFIX)
    starts, ends = sw.draw_lines(truth, sigma, seed)
    baseline = sw.corner_solve(starts, ends)
    row = {"geometry": name, "sigma_px": "%.2f" % sigma, "draw": draw, "seed": seed}
    if baseline is None:
        return {**row, **{key: "inf" for key in HEADER.split(",")[4:10]},
                "n_supports": 0, "n_kept": 0, "rounds_run": 0, "n_fev": 0, "status": "no_corner_solve"}
    chunks = [sw.supports_along(starts[index], ends[index]) for index in sw.FIT_LINES]
    supports = np.concatenate(chunks, axis=0)
    lengths = np.concatenate([np.full(len(chunk), float(np.linalg.norm(ends[index] - starts[index])))
                              for index, chunk in zip(sw.FIT_LINES, chunks)])
    candidate, stats = rb.refine_b(baseline, supports, lengths)
    first = sym.recovery_modulo_symmetry(truth, baseline, TEMPLATE_POINTS)
    second = sym.recovery_modulo_symmetry(truth, candidate, TEMPLATE_POINTS)
    return {**row, "baseline_labelled_gap_px": "%.6f" % first["labelled_gap_px"],
            "baseline_modulo_gap_px": "%.6f" % first["modulo_gap_px"],
            "baseline_element": first["attaining_element"],
            "candidate_b_labelled_gap_px": "%.6f" % second["labelled_gap_px"],
            "candidate_b_modulo_gap_px": "%.6f" % second["modulo_gap_px"],
            "candidate_b_element": second["attaining_element"], "n_supports": stats["n_supports"],
            "n_kept": stats["n_kept"], "rounds_run": stats["rounds_run"],
            "n_fev": stats["n_fev"], "status": stats["status"]}


def _summary(rows: list[dict]) -> dict:
    result = {}
    for name, _quad in sw.GEOMETRIES:
        for sigma in SIGMAS:
            subset = [row for row in rows if row["geometry"] == name and float(row["sigma_px"]) == sigma]
            key = "%s|%.2f" % (name, sigma)
            result[key] = {"draws": len(subset),
                           "baseline_labelled_median_px": float(np.median([float(r["baseline_labelled_gap_px"]) for r in subset])),
                           "baseline_modulo_median_px": float(np.median([float(r["baseline_modulo_gap_px"]) for r in subset])),
                           "candidate_b_labelled_median_px": float(np.median([float(r["candidate_b_labelled_gap_px"]) for r in subset])),
                           "candidate_b_modulo_median_px": float(np.median([float(r["candidate_b_modulo_gap_px"]) for r in subset]))}
    return result


def sweep(out: Path) -> int:
    """Run the sealed exact control plus paired noisy draws, after the premise exists."""
    if not (out / "g367_premise.json").exists():
        print("ABSENT %s: run premise first" % (out / "g367_premise.json").as_posix())
        return 2
    rows = []
    for name, quad in sw.GEOMETRIES:
        truth = sw.geometry_matrix(quad)
        for sigma in SIGMAS:
            draws = 1 if sigma == 0.0 else NOISY_DRAWS
            rows.extend(_one(truth, name, sigma, draw) for draw in range(draws))
    _write(out / "sweep.csv", rows)
    path = out / "summary.json"
    payload = json.loads(path.read_text(encoding="ascii")) if path.exists() else {}
    payload["sweep"] = {"sigmas_px": list(SIGMAS), "noisy_draws": NOISY_DRAWS,
                        "seed_prefix": PREFIX, "median_px": _summary(rows)}
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("SWEEP rows=%d" % len(rows))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("sweep",))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])
    return sweep(Path(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
