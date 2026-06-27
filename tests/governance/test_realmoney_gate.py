"""tests.governance.test_realmoney_gate -- the signed, default-DENY authorization gate.

Asserts the hard default-DENY behaviour of the real-money MODE authorization gate
and its HMAC token scheme: cold/empty -> DENY; eligible-but-no-human -> DENY;
eligible+human but no/invalid token -> DENY; eligible+human+valid token ->
authorized True; a TAMPERED token -> DENY; and that the gate NEVER authorizes a
bet. Run ONLY this file (a full pytest run freezes the box):

    python -m pytest tests/governance/test_realmoney_gate.py -q
"""
from __future__ import annotations

from governance import realmoney_gate as G

_SECRET = "test-secret-not-a-real-key"


def _eligible() -> dict:
    """A synthetic M4-eligibility result that PASSES the bar (no real ledger)."""
    return {
        "eligible": True,
        "reasons": [],
        "metrics": {"n": 600, "clv_mean": 0.5, "clv_lb95": 0.1,
                    "pct_beat_close": 0.58, "true_close_frac": 0.95},
        "gate_version": "realmoney_gate.v1",
        "authorizes_bet": False,
    }


def _ineligible() -> dict:
    return {
        "eligible": False,
        "reasons": ["insufficient settled N: have 0, need >= 500"],
        "metrics": {"n": 0, "clv_mean": None, "clv_lb95": None,
                    "pct_beat_close": None, "true_close_frac": None},
        "gate_version": "realmoney_gate.v1",
        "authorizes_bet": False,
    }


def _valid_token(elig: dict, secret: str = _SECRET) -> str:
    """Sign a token bound to the eligibility snapshot the gate will compute."""
    snap = G._snapshot(elig)
    return G.sign_token(snap, secret)


# --------------------------------------------------------------------------- #
# DEFAULT-DENY ladder                                                          #
# --------------------------------------------------------------------------- #
def test_cold_empty_denies():
    # No eligibility, no human, no token, no secret -> DENY.
    res = G.authorize(eligibility=_ineligible(), human_approved=False,
                      token=None, secret=None)
    assert res["authorized"] is False
    assert res["authorizes_bet"] is False
    assert res["reasons"]  # explained


def test_eligible_but_no_human_denies():
    elig = _eligible()
    res = G.authorize(eligibility=elig, human_approved=False,
                      token=_valid_token(elig), secret=_SECRET)
    assert res["authorized"] is False
    assert any("human" in r.lower() for r in res["reasons"])


def test_eligible_human_but_no_token_denies():
    elig = _eligible()
    res = G.authorize(eligibility=elig, human_approved=True,
                      token=None, secret=_SECRET)
    assert res["authorized"] is False
    assert res["token_valid"] is False


def test_eligible_human_but_invalid_token_denies():
    elig = _eligible()
    res = G.authorize(eligibility=elig, human_approved=True,
                      token="garbage.notavalidmac", secret=_SECRET)
    assert res["authorized"] is False
    assert res["token_valid"] is False


def test_eligible_human_valid_token_authorizes():
    elig = _eligible()
    res = G.authorize(eligibility=elig, human_approved=True,
                      token=_valid_token(elig), secret=_SECRET)
    assert res["authorized"] is True
    assert res["token_valid"] is True
    # Even when authorized, it NEVER authorizes a bet.
    assert res["authorizes_bet"] is False


def test_no_secret_denies_even_with_human_and_token():
    elig = _eligible()
    tok = _valid_token(elig)
    res = G.authorize(eligibility=elig, human_approved=True,
                      token=tok, secret=None)
    assert res["authorized"] is False
    assert any(G.SECRET_ENV in r for r in res["reasons"])


# --------------------------------------------------------------------------- #
# Token scheme: tamper / stale / wrong-secret rejection                        #
# --------------------------------------------------------------------------- #
def test_tampered_token_denies():
    elig = _eligible()
    tok = _valid_token(elig)
    # Flip a character in the signature portion -> HMAC mismatch.
    body, mac = tok.split(".", 1)
    bad_char = "0" if mac[-1] != "0" else "1"
    tampered = body + "." + mac[:-1] + bad_char
    res = G.authorize(eligibility=elig, human_approved=True,
                      token=tampered, secret=_SECRET)
    assert res["authorized"] is False
    assert res["token_valid"] is False


def test_tampered_body_denies():
    elig = _eligible()
    tok = _valid_token(elig)
    body, mac = tok.split(".", 1)
    tampered = body[:-1] + ("A" if body[-1] != "A" else "B") + "." + mac
    assert G.verify_token(tampered, _SECRET) is None


def test_token_bound_to_snapshot_rejects_stale():
    # A token signed over the ELIGIBLE snapshot must not authorize a DIFFERENT
    # (e.g. now-ineligible) snapshot -- stale authorizations cannot leak.
    tok = _valid_token(_eligible())
    res = G.authorize(eligibility=_ineligible(), human_approved=True,
                      token=tok, secret=_SECRET)
    assert res["authorized"] is False
    assert res["token_valid"] is False


def test_wrong_secret_denies():
    elig = _eligible()
    tok = _valid_token(elig, secret="some-other-secret")
    res = G.authorize(eligibility=elig, human_approved=True,
                      token=tok, secret=_SECRET)
    assert res["authorized"] is False


def test_sign_requires_secret():
    import pytest
    with pytest.raises(ValueError):
        G.sign_token({"x": 1}, "")


def test_secret_from_env(monkeypatch):
    elig = _eligible()
    monkeypatch.setenv(G.SECRET_ENV, _SECRET)
    res = G.authorize(eligibility=elig, human_approved=True,
                      token=_valid_token(elig))
    assert res["authorized"] is True


def test_sign_verify_roundtrip():
    payload = {"eligible": True, "n": 600}
    tok = G.sign_token(payload, _SECRET)
    assert G.verify_token(tok, _SECRET) == payload
    assert G.verify_token(tok, "wrong") is None
    assert G.verify_token(None, _SECRET) is None
    assert G.verify_token(tok, None) is None
