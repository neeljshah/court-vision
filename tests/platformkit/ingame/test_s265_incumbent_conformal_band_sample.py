"""Archive-only recomputation for S265 attempt 1b."""
import csv
import hashlib
import json
import tracemalloc
from pathlib import Path

from scripts.platformkit.eval_gate import s265_incumbent_conformal_band_sample as s265


REPO = Path(__file__).resolve().parents[3]


def test_s265_archive_recomputes_p4_static_cell_and_prereg_seal():
    """Use only committed S265 archives, never either source store."""
    tracemalloc.start()
    report = json.loads(s265.OUT_JSON.read_text(encoding="ascii"))
    prereg = s265.PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal_line = prereg.split(b"SEAL_SHA256:", 1)
    assert b"\r\n" not in prefix and prefix.endswith(b"\n")
    assert hashlib.sha256(prefix).hexdigest() == seal_line.strip().decode("ascii")
    assert report["prereg"]["seal_sha256"] == hashlib.sha256(prefix).hexdigest()
    assert report["source"]["sample_ticks"] == 79919
    assert report["source"]["sample_games"] == 269
    assert report["rss"]["peak_bytes"] < 600 * 1024 * 1024
    assert report["s101_regression"]["n_cells"] == 24
    assert report["s101_regression"]["passes"]
    assert report["code_identity"]["s265"] == hashlib.sha256(Path(s265.__file__).read_bytes()).hexdigest()

    with s265.PAIR_CSV.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    membership = [row for row in rows if row["record_type"] == "sample_game"]
    assert len(membership) == 269
    assert sum(int(row["n_ticks"]) for row in membership) == 79919
    groups = [row for row in rows if row["record_type"] == "grouped_coverage"
              and row["nominal"] == "0.80" and row["cell"] == "P4"]
    cell = report["static"]["0.80"]["cells"]["P4"]
    assert len(groups) == cell["n_groups"]
    assert sum(int(float(row["covered"])) for row in groups) / len(groups) == cell["coverage"]
    half_width = sum((float(row["mean_hi"]) - float(row["mean_lo"])) / 2.0 for row in groups) / len(groups)
    assert abs(half_width - cell["mean_interval_half_width"]) <= 1e-9
    assert tracemalloc.get_traced_memory()[1] < 200 * 1024 * 1024
