"""tests.sell.test_evidence -- the reproducibility / evidence pack is honest + stable.

Proves the buyer's due-diligence contract: reproduce_all() returns the gate / proof
verdicts UNCHANGED (governance ok, eval-gate leak-free, the in-game proof surfaced
honestly with vs_close UNPROVEN, the signed track record verifying), the pack
manifest hashes are STABLE / reproducible, and the assembled pack contains NO $-edge
key (governance honesty linter). Run ONLY this file (a full pytest run freezes the
box):

    python -m pytest tests/sell/test_evidence.py -q
"""
from __future__ import annotations

import json

from governance import honesty_linter as _linter

from sell import pack_manifest as M
from sell import reproduce as R
from sell.evidence_pack import (MANIFEST_NAME, REPRODUCE_NAME,
                                TRACK_RECORD_NAME, assemble_pack, build_pack)

_SECRET = "unit-test-secret-not-from-env"

# Substrings that would imply a dollar / ROI / P&L claim. NONE may appear in the
# pack (mirrors the track-record test's forbidden-key list).
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
# reproduce_all: real verdicts, honest, never upgraded.                       #
# --------------------------------------------------------------------------- #
def test_reproduce_all_governance_ok():
    """Governance preflight runs and surfaces a 0/1 verdict; on this clean stack ok."""
    res = R.reproduce_all(secret=_SECRET)
    gov = res["governance"]
    assert gov["exit_code"] in (0, 1)
    assert gov["verdict"] in ("GOVERNANCE_OK", "GOVERNANCE_BLOCKED")
    # The clean local stack should pass the honesty/correctness preflight.
    assert gov["ok"] is True
    assert gov["verdict"] == "GOVERNANCE_OK"


def test_reproduce_all_eval_gate_leak_free():
    """The leak-free golden walk-forward runs and surfaces honest per-corpus verdicts."""
    res = R.reproduce_all(secret=_SECRET)
    eg = res["eval_gate"]
    assert eg["exit_code"] in (0, 1)
    assert eg["corpora"], "eval gate must surface corpus rows"
    labels = {c["verdict"] for c in eg["corpora"]}
    allowed = {"BEATS_CLOSE", "MATCHES_CLOSE", "BEHIND",
               "CORPUS_ABSENT (skip)", "LEAK"}
    # Every label is an HONEST gate label -- not upgraded to a $ claim.
    assert labels <= allowed, labels
    # The golden anchor must not regress / leak on this committed fixture.
    assert eg["exit_code"] == 0


def test_reproduce_all_ingame_vs_close_unproven():
    """The in-game proof verdict is surfaced honestly: vs_close stays UNPROVEN."""
    res = R.reproduce_all(secret=_SECRET)
    ig = res["ingame_proof"]
    assert ig["available"] is True
    # The honest in-game verdict is calibration, not a market edge.
    assert ig["verdict"] == "CALIBRATION_GAIN_VS_BASERATE"
    assert "UNPROVEN" in str(ig["vs_close"])
    # No verdict upgrade: vs_close is never turned into a beat/edge.
    assert "edge" not in str(ig["vs_close"]).lower() or "not a market edge" in \
        str(ig["vs_close"]).lower()


def test_reproduce_all_track_record_verifies(tmp_path):
    """A freshly built+signed track record verifies through reproduce_all."""
    # Write a signed artifact this test controls, then point reproduce at it.
    written = build_pack(tmp_path, secret=_SECRET,
                         track_record_path=tmp_path / TRACK_RECORD_NAME)
    tr_path = written[TRACK_RECORD_NAME]
    res = R.reproduce_all(secret=_SECRET, track_record_path=tr_path)
    tr = res["track_record"]
    assert tr["available"] is True
    assert tr["signed"] is True
    assert tr["verified"] is True
    assert tr["verdict"] == "SIGNATURE_VERIFIED"
    assert tr["edge_claimed"] is False


def test_reproduce_all_no_secret_is_unsigned_not_upgraded(tmp_path):
    """No secret -> track record is honestly UNSIGNED, never silently verified."""
    written = build_pack(tmp_path, secret=None,
                         track_record_path=tmp_path / TRACK_RECORD_NAME)
    res = R.reproduce_all(secret=None,
                          track_record_path=written[TRACK_RECORD_NAME])
    tr = res["track_record"]
    assert tr["signed"] is False
    assert tr["verified"] is False
    assert "UNSIGNED" in tr["verdict"]


def test_reproduce_edge_claimed_pinned_false():
    """The reproduce verdict block pins edge_claimed False -- no $ claim."""
    res = R.reproduce_all(secret=_SECRET)
    assert res["edge_claimed"] is False
    assert res["command"] == "python -m sell.evidence_pack"


# --------------------------------------------------------------------------- #
# manifest: stable + reproducible hashes; tamper-evident.                     #
# --------------------------------------------------------------------------- #
def test_manifest_hashes_are_stable():
    """The same objects hash to the same digests + roll-up every time."""
    objs = {"a.json": {"k": 1, "z": [3, 2, 1]}, "b.json": {"x": "y"}}
    m1 = M.manifest_for_objects(objs)
    m2 = M.manifest_for_objects(dict(reversed(list(objs.items()))))
    # Order-independent: insertion order must not change the manifest.
    assert m1 == m2
    assert m1["manifest_sha256"] == m2["manifest_sha256"]
    # Digests are reproducible content hashes.
    again = M.manifest_for_objects(objs)
    assert again["manifest_sha256"] == m1["manifest_sha256"]


def test_manifest_detects_tamper():
    """Mutating one packed object changes its digest and the roll-up."""
    objs = {"a.json": {"k": 1}, "b.json": {"x": "y"}}
    m = M.manifest_for_objects(objs)
    ok, mism = M.verify_manifest(m, objs)
    assert ok and not mism
    tampered = {"a.json": {"k": 2}, "b.json": {"x": "y"}}
    ok2, mism2 = M.verify_manifest(m, tampered)
    assert ok2 is False
    assert "a.json" in mism2


def test_pack_manifest_matches_written_files(tmp_path):
    """The manifest digests match the canonical bytes actually written to disk."""
    pack = assemble_pack(secret=_SECRET,
                         track_record_path=tmp_path / TRACK_RECORD_NAME)
    manifest = pack[MANIFEST_NAME]
    by_name = {e["name"]: e for e in manifest["artifacts"]}
    # Manifest covers the three content artifacts (not itself).
    assert set(by_name) == {TRACK_RECORD_NAME, REPRODUCE_NAME,
                            "methodology.json"}
    for name, entry in by_name.items():
        recomputed = M.hash_bytes(M.canonical_bytes(pack[name]))
        assert entry["sha256"] == recomputed


# --------------------------------------------------------------------------- #
# honesty: no $ keys anywhere in the assembled pack.                          #
# --------------------------------------------------------------------------- #
def test_pack_has_no_dollar_keys():
    """No ROI / P&L / $-edge key appears anywhere in the assembled pack."""
    pack = assemble_pack(secret=_SECRET)
    keys = []
    _all_keys(pack, keys)
    for k in keys:
        low = k.lower()
        for bad in _FORBIDDEN_KEY_SUBSTRINGS:
            assert bad not in low, "forbidden key substring %r in key %r" % (bad, k)


def test_pack_passes_honesty_linter():
    """The whole assembled pack passes the governance honesty linter (no raise)."""
    pack = assemble_pack(secret=_SECRET)
    res = _linter.lint_obj(pack)
    assert res["clean"] is True, res["violations"]
    # assemble_pack also asserts internally; an explicit re-check here.
    _linter.assert_clean(pack)


def test_pack_is_round_trippable_json():
    """Every pack artifact serialises to JSON (the on-disk form)."""
    pack = assemble_pack(secret=_SECRET)
    for name, obj in pack.items():
        s = json.dumps(obj, sort_keys=True, default=str)
        assert json.loads(s) is not None or s == "null"
