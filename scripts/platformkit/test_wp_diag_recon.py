"""Synthetic checks for WP diagnostic outcome-pair reconciliation."""
from scripts.platformkit.wp_diag_recon import reconcile


def test_reconciler_flags_deliberately_mispaired_loader():
    records = [{"game": "G-HIGH", "model_prob": .95, "outcome": 0.0, "side": "home"},
               {"game": "G-OTHER", "model_prob": .40, "outcome": 1.0, "side": "home"}]
    report = reconcile(records, {"good": lambda row: float(row["outcome"]),
                                 "bad": lambda row: 1.0 - float(row["outcome"])})
    assert report["mismatch_counts"] == {"good": 0, "bad": 2}
    assert report["all_agree"] is False
    assert report["games"][0]["game"] == "G-HIGH"
