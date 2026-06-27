"""tests.platformkit.improve.test_ingame_prop_ratchet -- in-game prop ratchet contract.

Asserts:
  (a) bucket_for: frac_elapsed -> early/mid/late by boundary; out-of-range / non-numeric -> None.
  (b) load_settled_ingame_props: keeps ONLY ingame=True + market_type=prop + status=settled
      rows; drops pregame, non-prop, open, push (outcome undecided), and bad-frac rows;
      stamps frac + bucket; chronological.
  (c) improve_all_ingame on a THIN synthetic ledger -> every bucket INSUFFICIENT_DATA
      (never a fabricated SHIP); meta written; gate read-surface shape correct.
  (d) HONESTY: no $ / roi / pnl key anywhere in the meta or verdict recs; note present.

Per-file test only. ASCII; stdlib deps. Uses a tmp ledger (never the real one).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import ingame_prop_ratchet as R


def _row(**kw):
    base = {
        "sport": "mlb", "market_type": "prop", "ingame": True, "status": "settled",
        "frac_elapsed": 0.2, "model_prob": 0.6, "outcome": "win", "market_prob": 0.55,
        "bet_id": "b%s" % kw.get("bet_id", "0"), "ts": kw.get("ts", "2026-06-26T01:00:00+00:00"),
        "market": "prop|P|Hits|0.5|over",
    }
    base.update(kw)
    return base


def _write_ledger(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_bucket_for_boundaries():
    assert R.bucket_for(0.0) == "early"
    assert R.bucket_for(0.33) == "early"
    assert R.bucket_for(0.34) == "mid"
    assert R.bucket_for(0.66) == "mid"
    assert R.bucket_for(0.67) == "late"
    assert R.bucket_for(0.99) == "late"
    assert R.bucket_for(1.5) is None
    assert R.bucket_for(-0.1) is None
    assert R.bucket_for("x") is None
    assert R.bucket_for(None) is None


def test_loader_filters_to_ingame_settled_props(tmp_path):
    led = tmp_path / "clv.jsonl"
    rows = [
        _row(bet_id="ig1", frac_elapsed=0.2, ts="2026-06-26T01:00:00+00:00"),     # keep (early)
        _row(bet_id="ig2", frac_elapsed=0.5, ts="2026-06-26T02:00:00+00:00"),     # keep (mid)
        _row(bet_id="pre", ingame=False),                                          # drop: pregame
        _row(bet_id="ml", market_type="moneyline"),                                # drop: not prop
        _row(bet_id="open", status="open"),                                        # drop: not settled
        _row(bet_id="push", outcome="push"),                                       # drop: undecided
        _row(bet_id="badfrac", frac_elapsed=2.0),                                  # drop: bad frac
    ]
    _write_ledger(led, rows)
    out = R.load_settled_ingame_props("mlb", clv_path=led)
    assert [r["market"] for r in out] and len(out) == 2
    buckets = sorted(r["bucket"] for r in out)
    assert buckets == ["early", "mid"]
    # chronological + frac stamped
    assert out[0]["ts"] <= out[1]["ts"]
    assert all("frac" in r and "bucket" in r for r in out)


def test_thin_ledger_is_insufficient_never_fabricated(tmp_path):
    led = tmp_path / "clv.jsonl"
    # 5 early-bucket ingame props -> well under MIN_RECAL_GAMES -> INSUFFICIENT_DATA
    _write_ledger(led, [_row(bet_id="t%d" % i, frac_elapsed=0.2,
                             ts="2026-06-26T0%d:00:00+00:00" % i) for i in range(5)])
    meta_path = tmp_path / "ingame_prop_meta.json"
    led_imp = tmp_path / "improve.jsonl"
    res = R.improve_all_ingame(clv_path=led, ledger_path=led_imp, meta_path=meta_path)
    verdicts = {g["verdict"] for g in res["meta"]["groups"]}
    assert verdicts == {"INSUFFICIENT_DATA"}
    assert meta_path.exists()
    disk = json.loads(meta_path.read_text(encoding="utf-8"))
    assert disk["suppress_verdicts"] == ["REJECT"]
    assert {g["bucket"] for g in disk["groups"]} == {"early", "mid", "late"}


def test_honesty_no_dollar_keys(tmp_path):
    led = tmp_path / "clv.jsonl"
    _write_ledger(led, [_row(bet_id="h%d" % i) for i in range(3)])
    res = R.improve_all_ingame(clv_path=led, ledger_path=tmp_path / "imp.jsonl",
                               meta_path=tmp_path / "m.json")
    blob = json.dumps(res).lower()
    for banned in ("roi", "pnl", "profit", "bankroll", "$"):
        assert banned not in blob, "honesty: %r leaked into ratchet output" % banned
    assert "calibration" in res["note"].lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
