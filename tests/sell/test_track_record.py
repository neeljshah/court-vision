"""tests.sell.test_track_record -- the signed CLV track record is honest + tamper-evident.

Builds a TrackRecord from a fixture scoreboard (no network, no ledger I/O),
asserts it carries CLV + calibration + counts but NO dollar / ROI / P&L field,
passes the governance honesty linter, signs + verifies round-trip, and proves a
single mutated field FAILS verify. Run ONLY this file (a full pytest run freezes
the box):

    python -m pytest tests/sell/test_track_record.py -q
"""
from __future__ import annotations

import json

from governance import honesty_linter as _linter

from sell import signing as S
from sell.track_record import build_track_record, sign_track_record
from sell.trackrecord_schema import TrackRecord

_SECRET = "unit-test-secret-not-from-env"

# A deterministic fixture in the exact scoreboard.build_scoreboard shape.
_FIXTURE_SCOREBOARD = {
    "as_of": "2026-06-18T00:00:00+00:00",
    "n_settled": 620,
    "mean_clv_pct": 0.73,
    "pct_beat_close": 57.1,
    "n_true_close": 510,
    "n_proxy_close": 110,
    "flat_unit_wins": 300,
    "flat_unit_losses": 320,
    "flat_unit_clv": 0.71,
    "by_sport": {
        "nba": {
            "n": 400, "mean_clv_pct": 0.80, "pct_beat_close": 58.0,
            "n_true_close": 350, "n_proxy_close": 50,
            "flat_unit_wins": 200, "flat_unit_losses": 200,
        },
        "mlb": {
            "n": 220, "mean_clv_pct": 0.61, "pct_beat_close": 55.5,
            "n_true_close": 160, "n_proxy_close": 60,
            "flat_unit_wins": 100, "flat_unit_losses": 120,
        },
    },
    "honest_note": "CLV is the honest yardstick, not a profit claim.",
}

# Keys that would imply a dollar / ROI / P&L claim. NONE may appear on the record.
_FORBIDDEN_KEY_SUBSTRINGS = (
    "roi", "pnl", "p&l", "p_and_l", "profit", "dollar", "$", "edge_pct",
    "edge_dollar", "net_units", "payout", "bankroll", "stake_dollars",
)


def _all_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            _all_keys(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _all_keys(v, out)


# --------------------------------------------------------------------------- #
# build: right fields, no $ keys.                                             #
# --------------------------------------------------------------------------- #
def test_build_has_expected_clv_fields():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    assert isinstance(tr, TrackRecord)
    d = tr.to_dict()
    assert d["n_settled"] == 620
    assert d["mean_clv_pct"] == 0.73
    assert d["pct_beat_close"] == 57.1
    assert d["n_true_close"] == 510
    assert d["n_proxy_close"] == 110
    assert d["edge_claimed"] is False
    # by_sport carries CLV + counts per sport, no flat-unit win/loss money framing.
    assert set(d["by_sport"]) == {"nba", "mlb"}
    nba = d["by_sport"]["nba"]
    assert nba["n"] == 400 and nba["mean_clv_pct"] == 0.80
    assert "flat_unit_wins" not in nba and "flat_unit_losses" not in nba
    # calibration absent -> explicitly unavailable, never fabricated.
    assert d["calibration"]["status"] == "unavailable"
    assert d["calibration"]["brier"] is None
    assert d["calibration"]["ece"] is None


def test_calibration_surfaced_when_supplied():
    tr = build_track_record(
        scoreboard=_FIXTURE_SCOREBOARD,
        calibration={"brier": 0.213, "ece": 0.018},
    )
    cal = tr.to_dict()["calibration"]
    assert cal["status"] == "measured"
    assert cal["brier"] == 0.213 and cal["ece"] == 0.018


def test_no_dollar_roi_or_pnl_key_anywhere():
    d = build_track_record(scoreboard=_FIXTURE_SCOREBOARD).to_dict()
    keys = []
    _all_keys(d, keys)
    for k in keys:
        low = k.lower()
        for bad in _FORBIDDEN_KEY_SUBSTRINGS:
            assert bad not in low, "forbidden key substring %r in key %r" % (bad, k)


def test_edge_claimed_cannot_be_forced_true():
    # from_dict / to_dict must pin edge_claimed False regardless of input.
    tr = TrackRecord.from_dict({"generated_at": "x", "edge_claimed": True})
    assert tr.edge_claimed is False
    assert tr.to_dict()["edge_claimed"] is False


# --------------------------------------------------------------------------- #
# honesty linter: the signed artifact is clean.                              #
# --------------------------------------------------------------------------- #
def test_signed_record_passes_honesty_linter():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    signed = sign_track_record(tr, secret=_SECRET)
    res = _linter.lint_obj(signed)
    assert res["clean"], res["violations"]


def test_sign_track_record_raises_on_dishonest_payload(monkeypatch):
    # If a poisoned key somehow reaches signing, the honesty gate must block it.
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    import sell.track_record as M

    def _poison(payload, secret=None):
        out = dict(payload)
        out["$edge"] = 1.23  # forbidden key
        return out

    monkeypatch.setattr(M, "_sign", _poison)
    try:
        M.sign_track_record(tr, secret=_SECRET)
        raised = False
    except AssertionError:
        raised = True
    assert raised, "honesty linter must block a $edge key from shipping"


# --------------------------------------------------------------------------- #
# sign + verify round-trip; tamper fails.                                     #
# --------------------------------------------------------------------------- #
def test_sign_verify_round_trip():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    signed = sign_track_record(tr, secret=_SECRET)
    assert S.is_signed(signed)
    assert signed["signature"]["algo"] == "HMAC-SHA256"
    assert S.verify(signed, secret=_SECRET) is True


def test_mutated_field_fails_verify():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    signed = sign_track_record(tr, secret=_SECRET)
    # Round-trip through JSON (as the artifact would be persisted) then mutate.
    record = json.loads(json.dumps(signed))
    assert S.verify(record, secret=_SECRET) is True
    record["n_settled"] = record["n_settled"] + 1  # single mutated field
    assert S.verify(record, secret=_SECRET) is False


def test_mutated_nested_field_fails_verify():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    signed = sign_track_record(tr, secret=_SECRET)
    record = json.loads(json.dumps(signed))
    record["by_sport"]["nba"]["mean_clv_pct"] = 9.99  # nested tamper
    assert S.verify(record, secret=_SECRET) is False


def test_wrong_secret_fails_verify():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    signed = sign_track_record(tr, secret=_SECRET)
    assert S.verify(signed, secret="a-different-secret") is False


def test_no_secret_yields_unsigned_record():
    tr = build_track_record(scoreboard=_FIXTURE_SCOREBOARD)
    # Explicit empty secret -> cannot sign -> marked unsigned, verify False.
    signed = sign_track_record(tr, secret="")
    assert S.is_signed(signed) is False
    assert signed["signature"]["signed"] is False
    assert signed["signature"]["value"] is None
    assert S.verify(signed, secret=_SECRET) is False
