"""Archive-only S294 seal and grouped-cell reproduction."""
import csv
import gzip
import hashlib
import json

from scripts.platformkit.eval_gate import s276_incumbent_conformal_band_full_attempt2 as s294


def test_s294_prereg_seal_and_archived_p1_cell_recompute():
    """Normalize the extracted prereg file and recompute one archived grouped cell."""
    data = s294.PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"SEAL_SHA256:", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.strip().decode("ascii")
    report = json.loads(s294.OUT_JSON.read_text(encoding="ascii"))
    with gzip.open(s294.PAIR_CSV, "rt", newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    pairs = [row for row in rows if row["record_type"] == "paired_loss"]
    assert len(pairs) == 465249
    assert len({row["state_key"] for row in pairs}) == len(pairs)
    assert len({row["game"] for row in pairs}) == 1593
    grouped = [row for row in rows if row["record_type"] == "grouped_coverage"
               and row["nominal"] == "0.90" and row["cell"] == "P1"]
    expected = report["static"]["0.90"]["cells"]["P1"]
    assert len(grouped) == expected["n_groups"]
    coverage = sum(int(float(row["covered"])) for row in grouped) / len(grouped)
    half_width = sum((float(row["mean_hi"]) - float(row["mean_lo"])) / 2.0 for row in grouped) / len(grouped)
    assert abs(coverage - float(expected["coverage"])) <= 1e-9
    assert abs(half_width - float(expected["mean_interval_half_width"])) <= 1e-9
    assert report["prereg"]["seal_sha256"] == s294.prereg_seal()
    assert report["design"]["n_groups"] == 6
    assert [row["block_id"] for row in report["design"]["blocks"]] == list(range(6))
