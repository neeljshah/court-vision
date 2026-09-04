"""Archive-only checks for the sealed S285 event-proximity audit."""
import csv
import hashlib
import json
import tracemalloc

import pandas as pd

from scripts.platformkit.eval_gate import s101_aci_coverage as s101
from scripts.platformkit.eval_gate import s285_event_conformal_width as s285


def test_s285_derivation_and_near_event_archive_recompute():
    """Exercise a run, lull, game start, LF seal, and one archived bin."""
    fixture = pd.DataFrame({"game_id": ["a"] * 5 + ["b"], "ts": [1, 2, 3, 4, 5, 1],
                            "score_home": [0, 0, 2, 4, 4, 0], "score_away": [0] * 6})
    assert s285.derive_ticks_since_last_score_change(fixture).tolist() == [0, 1, 0, 0, 1, 0]
    unsorted = fixture.iloc[[2, 0, 5, 4, 1, 3]]
    assert s285.derive_ticks_since_last_score_change(unsorted).tolist() == [0, 0, 0, 1, 1, 0]
    tracemalloc.start()
    prereg = s285.PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = prereg.split(b"SEAL_SHA256:", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.strip().decode("ascii")
    report = json.loads(s285.OUT_JSON.read_text(encoding="ascii"))
    assert report["prereg"]["seal_sha256"] == hashlib.sha256(prefix).hexdigest()
    with s285.PAIR_CSV.open(newline="", encoding="ascii") as handle:
        rows = [row for row in csv.DictReader(handle) if row["nominal"] == "0.9" and row["bin"] == "near_event"]
    p = pd.DataFrame(rows)
    grouped = s101.grouped_coverage(p["p"].astype(float).to_numpy(), p["y"].astype(float).to_numpy(),
                                    p["lo_static"].astype(float).to_numpy(), p["hi_static"].astype(float).to_numpy(), 0.90)
    metric = report["results"]["0.90"]["bins"]["near_event"]
    assert grouped["coverage"] == metric["coverage"]
    assert abs(grouped["mean_interval_width"] / 2.0 - metric["mean_half_width"]) <= 1e-12
    assert tracemalloc.get_traced_memory()[1] < 300 * 1024 * 1024
