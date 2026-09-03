"""S137 -- the re-quote helper must reproduce published CIs from the archives alone."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s137_rebaseline as s137

# the two rows whose published CI is stored inside its own artifact and whose
# archive is a plain per-unit differential: S86 (a d column) and S82 (a paired
# probability pair).  One of each shape, so both helper paths are covered.
TWO = ("S86", "S82")


def _archives_present(rows) -> bool:
    for name in rows:
        spec = s137._A2[name]
        if not (s137._CACHE / spec["csv"]).exists():
            return False
        if spec["json"] and not (s137._CACHE / spec["json"]).exists():
            return False
    return True


@pytest.mark.skipif(not _archives_present(TWO),
                    reason="local-only archives under data/cache/eval_gate are absent")
def test_requote_helper_reproduces_two_published_cis_to_1e_9():
    out = s137.a2(TWO)
    for name in TWO:
        entry = out[name]
        assert entry["reproduced"], (name, entry["max_abs_delta"])
        assert entry["max_abs_delta"] < 1e-9, (name, entry["max_abs_delta"])


def test_a_cluster_id_containing_a_hash_is_not_truncated(tmp_path):
    """The S116 archive keys clusters as `mlb:TICKER#1`; a `comment="#"` read
    silently blanks every later column and leaves the loss all-NaN."""
    csv = tmp_path / "series.csv"
    pd.DataFrame({"cluster": ["a#1", "a#1", "b#2", "b#2"],
                  "d": [0.1, -0.1, 0.2, 0.0]}).to_csv(csv, index=False)
    quote = s137.archive_quote("series.csv", "cluster", d_col="d", cache=tmp_path)
    assert quote["n"] == 4 and quote["n_games"] == 2
    assert quote["mean_loss_differential"] == pytest.approx(0.05)


def test_reproduces_reports_a_mismatch_rather_than_replacing_it():
    quote = {"dm_ci95": [0.0, 1.0]}
    assert s137.reproduces(quote, [0.0, 1.0])["reproduced"] is True
    bad = s137.reproduces(quote, [0.0, 1.001])
    assert bad["reproduced"] is False and bad["max_abs_delta"] == pytest.approx(0.001)
