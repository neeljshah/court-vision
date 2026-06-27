"""tests.governance.test_policy -- governance.policy is the single source of truth.

Asserts the banned numbers / tokens are present AND matchable, the provenance
enum is complete and correctly partitioned, and the re-exported real-money
thresholds match the vetted pm_trading.realmoney_gate (no drift). Run ONLY this
file (a full pytest run freezes the box):

    python -m pytest tests/governance/test_policy.py -q
"""
from __future__ import annotations

from governance import policy as P
from scripts.platformkit.pm_trading import realmoney_gate as rmg


# --------------------------------------------------------------------------- #
# BANNED NUMBERS: present + tolerant matching                                  #
# --------------------------------------------------------------------------- #
EXPECTED_BANNED_TOKENS = {"18.38", "0.119", "54", "78.11", "8.94", "54.57"}


def test_banned_numbers_present():
    assert set(P.BANNED_NUMBER_TOKENS) == EXPECTED_BANNED_TOKENS
    # Each banned number carries a token, a float value, a reason and a regex.
    for b in P.BANNED_NUMBERS:
        assert b.token and b.reason
        assert isinstance(b.value, float)
        assert float(b.token) == b.value


def test_banned_numbers_match_in_text():
    # Tolerant matching: with or without sign / percent / surrounding text.
    assert P.find_banned_numbers("pregame ROI was +18.38% last run") == ["18.38"]
    assert P.find_banned_numbers("win prob 0.119 at endQ3") == ["0.119"]
    assert "78.11" in P.find_banned_numbers("hit 78.11 accuracy")
    assert "8.94" in P.find_banned_numbers("inflated to 8.94 units")
    assert "54.57" in P.find_banned_numbers("the 54.57 figure")


def test_banned_number_not_embedded_in_longer_number():
    # Must not fire on an unrelated longer number that merely contains the digits.
    assert P.find_banned_numbers("game id 218.384 is fine") == []
    assert P.find_banned_numbers("value 0.1190001 differs") == []
    assert P.find_banned_numbers("3.054 is unrelated") == []


def test_bare_54_requires_percent_or_sign_context():
    # "54" is context-gated: a STANDALONE 54 (e.g. an ISO ':54' second, a count)
    # must NOT raise a false honesty violation. The retracted figure is "+54%" /
    # "54%", so only those (with +/- or %) are banned.
    assert P.find_banned_numbers("generated_at 2026-06-18T22:01:54+00:00") == []
    assert P.find_banned_numbers("page 54 of the report") == []
    assert P.find_banned_numbers("there are 54 games") == []
    # In percent / signed context it IS still detected.
    assert "54" in P.find_banned_numbers("in-play hit +54% last run")
    assert "54" in P.find_banned_numbers("a 54% accuracy figure")
    assert "54" in P.find_banned_numbers("delta of -54 units")


def test_retraction_context_whitelists_numbers():
    retracted = ("The +18.38% pregame ROI is a documented measurement artifact; "
                 "see JOB_EVIDENCE_PACKET. Do not claim it.")
    assert P.is_retraction_context(retracted)
    assert P.find_banned_numbers(retracted) == []
    # But ignoring retraction context, the number is still detectable.
    assert P.find_banned_numbers(retracted, respect_retraction=False) == ["18.38"]


# --------------------------------------------------------------------------- #
# BANNED TOKENS: present + matchable, never whitelisted by retraction           #
# --------------------------------------------------------------------------- #
def test_banned_tokens_present():
    low = set(P.BANNED_TOKENS_LOWER)
    for must in ("$edge", "dollar-edge", "guaranteed", "roi edge"):
        assert must in low
    assert len(P.BANNED_TOKENS) == len(P.BANNED_TOKENS_LOWER)


def test_banned_tokens_match_case_insensitive():
    assert "$edge" in P.find_banned_tokens('{"$edge": 12.0}')
    assert "guaranteed" in P.find_banned_tokens("GUARANTEED winner tonight")
    assert "roi edge" in P.find_banned_tokens("our ROI Edge is real")
    assert P.find_banned_tokens("probability and EV only") == []


def test_banned_tokens_not_whitelisted_by_retraction():
    # A $edge field is wrong even inside an otherwise-retraction-framed note.
    text = "Retracted: we removed the $edge field. (artifact)"
    assert P.is_retraction_context(text)
    assert "$edge" in P.find_banned_tokens(text)


# --------------------------------------------------------------------------- #
# PROVENANCE enum: complete + correctly partitioned                            #
# --------------------------------------------------------------------------- #
def test_provenance_enum_complete():
    names = {m.name for m in P.Provenance}
    assert names == {
        "REAL_MODEL", "CAPTURED_MARKET", "DERIVED",
        "FILLED", "UNAVAILABLE", "UNKNOWN",
    }


def test_provenance_partition():
    # FILLED / UNKNOWN must be flagged, never presentable as real.
    assert P.Provenance.FILLED in P.FLAGGED_PROVENANCE
    assert P.Provenance.UNKNOWN in P.FLAGGED_PROVENANCE
    assert P.provenance_must_be_flagged(P.Provenance.FILLED)
    assert P.provenance_must_be_flagged(P.Provenance.UNKNOWN)
    # REAL_MODEL / CAPTURED_MARKET / DERIVED are presentable, not flagged.
    for ok in (P.Provenance.REAL_MODEL, P.Provenance.CAPTURED_MARKET,
               P.Provenance.DERIVED):
        assert ok in P.PRESENTABLE_PROVENANCE
        assert not P.provenance_must_be_flagged(ok)
    # The two partitions are disjoint and cover the flag-relevant members.
    assert P.PRESENTABLE_PROVENANCE.isdisjoint(P.FLAGGED_PROVENANCE)


# --------------------------------------------------------------------------- #
# THRESHOLDS: re-exported, match realmoney_gate (no drift)                      #
# --------------------------------------------------------------------------- #
def test_thresholds_match_realmoney_gate():
    assert P.MIN_SETTLED_N == rmg.MIN_SETTLED_N
    assert P.CLV_BOOTSTRAP_LB_MIN == rmg.CLV_BOOTSTRAP_LB_MIN
    assert P.MIN_PCT_BEAT_CLOSE == rmg.MIN_PCT_BEAT_CLOSE
    assert P.MIN_TRUE_CLOSE_FRAC == rmg.MIN_TRUE_CLOSE_FRAC
    assert P.REALMONEY_GATE_VERSION == rmg.GATE_VERSION


def test_threshold_dict_consistent():
    assert P.REALMONEY_THRESHOLDS == {
        "min_settled_n": P.MIN_SETTLED_N,
        "clv_bootstrap_lb_min": P.CLV_BOOTSTRAP_LB_MIN,
        "min_pct_beat_close": P.MIN_PCT_BEAT_CLOSE,
        "min_true_close_frac": P.MIN_TRUE_CLOSE_FRAC,
    }


def test_default_realmoney_ineligible():
    # Governance default-DENY: the stack is ineligible for real money by default.
    assert P.DEFAULT_REALMONEY_ELIGIBLE is False
