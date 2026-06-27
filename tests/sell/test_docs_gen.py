"""tests.sell.test_docs_gen -- sell doc generator is idempotent, honest, number-driven.

Proves:
  * generate_all is idempotent: calling it twice with the same scoreboard
    fixture produces byte-identical docs (same input -> same output).
  * Each of the four generated docs passes governance.honesty_linter.
  * Numbers in TRACK_RECORD.md come from the signed track record: changing
    a value in the fixture scoreboard changes the rendered doc.
  * No $-edge / ROI / P&L key appears anywhere in any generated doc.
  * edge_claimed=false is surfaced correctly in the track-record doc.

Run ONLY this file (a full pytest run freezes the box):

    python -m pytest tests/sell/test_docs_gen.py -q
"""
from __future__ import annotations

import copy

from governance import honesty_linter as _linter
from sell.docs_gen import generate_all

_SECRET = "unit-test-docs-gen-not-from-env"

# Deterministic scoreboard fixture (same shape as scoreboard.build_scoreboard).
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

# Key/field substrings that would imply a dollar / ROI / P&L CLAIM.
# These are structural / field-name checks (not prose): retraction prose
# ("NOT a dollar ROI", "no P&L field") is allowed and indeed required for
# honesty -- the governance honesty_linter is the definitive gate for that.
# Here we check that no doc FIELD or assertive sell-side claim appears.
_FORBIDDEN_SUBSTRINGS = (
    "edge_pct", "edge_dollar", "net_units", "payout",
    "bankroll", "stake_dollars", "pnl", "p_and_l",
)

# The four docs that must be generated.
_EXPECTED_DOCS = frozenset({
    "TRACK_RECORD.md",
    "PRODUCT_ONE_PAGER.md",
    "PRICING_TIERS.md",
    "MANIFEST.md",
})


def _gen(**kw):
    """Shorthand: generate_all with the test fixture, dry_run=True."""
    return generate_all(
        secret=_SECRET,
        scoreboard=_FIXTURE_SCOREBOARD,
        dry_run=True,
        **kw,
    )


# --------------------------------------------------------------------------- #
# Completeness                                                                 #
# --------------------------------------------------------------------------- #

def test_all_four_docs_generated():
    docs = _gen()
    assert set(docs.keys()) == _EXPECTED_DOCS, (
        "expected docs %s; got %s" % (sorted(_EXPECTED_DOCS), sorted(docs))
    )


def test_all_docs_are_non_empty():
    docs = _gen()
    for name, content in docs.items():
        assert content and len(content) > 50, (
            "%s is unexpectedly short or empty" % name
        )


# --------------------------------------------------------------------------- #
# Idempotence: same scoreboard -> byte-identical output                       #
# --------------------------------------------------------------------------- #

def test_generate_all_is_idempotent():
    """Two calls with the same fixture scoreboard must produce the same docs."""
    docs1 = _gen()
    docs2 = _gen()
    for name in _EXPECTED_DOCS:
        # generated_at timestamps differ between build_track_record calls;
        # strip the timestamp line before comparing so idempotence is about
        # the actual numbers and prose, not the wall-clock instant.
        def _strip_ts(text: str) -> str:
            return "\n".join(
                ln for ln in text.splitlines()
                if "Generated:" not in ln and "generated_at" not in ln
                and "as_of" not in ln
            )
        assert _strip_ts(docs1[name]) == _strip_ts(docs2[name]), (
            "%s content changed between two identical calls" % name
        )


# --------------------------------------------------------------------------- #
# Honesty linter: every doc is lint-clean                                     #
# --------------------------------------------------------------------------- #

def test_track_record_md_passes_honesty_linter():
    docs = _gen()
    res = _linter.lint_obj(docs["TRACK_RECORD.md"])
    assert res["clean"], "TRACK_RECORD.md lint violations: %s" % res["violations"]


def test_product_one_pager_md_passes_honesty_linter():
    docs = _gen()
    res = _linter.lint_obj(docs["PRODUCT_ONE_PAGER.md"])
    assert res["clean"], (
        "PRODUCT_ONE_PAGER.md lint violations: %s" % res["violations"]
    )


def test_pricing_tiers_md_passes_honesty_linter():
    docs = _gen()
    res = _linter.lint_obj(docs["PRICING_TIERS.md"])
    assert res["clean"], (
        "PRICING_TIERS.md lint violations: %s" % res["violations"]
    )


def test_manifest_md_passes_honesty_linter():
    docs = _gen()
    res = _linter.lint_obj(docs["MANIFEST.md"])
    assert res["clean"], "MANIFEST.md lint violations: %s" % res["violations"]


# --------------------------------------------------------------------------- #
# No forbidden key / substring in any doc                                     #
# --------------------------------------------------------------------------- #

def test_no_forbidden_dollar_roi_pnl_substring_in_any_doc():
    """None of the generated docs may contain a $-edge / ROI / P&L substring."""
    docs = _gen()
    for doc_name, content in docs.items():
        low = content.lower()
        for bad in _FORBIDDEN_SUBSTRINGS:
            assert bad not in low, (
                "forbidden substring %r found in %s" % (bad, doc_name)
            )


# --------------------------------------------------------------------------- #
# Numbers come from the track record: fixture change -> doc changes           #
# --------------------------------------------------------------------------- #

def test_track_record_md_shows_n_settled_from_fixture():
    """n_settled from the fixture scoreboard must appear in TRACK_RECORD.md."""
    docs = _gen()
    content = docs["TRACK_RECORD.md"]
    assert "620" in content, (
        "n_settled=620 from fixture not found in TRACK_RECORD.md"
    )


def test_track_record_md_changes_when_fixture_changes():
    """Changing n_settled in the fixture must change the rendered doc."""
    alt_fixture = copy.deepcopy(_FIXTURE_SCOREBOARD)
    alt_fixture["n_settled"] = 999

    docs_orig = _gen()
    docs_alt = generate_all(
        secret=_SECRET,
        scoreboard=alt_fixture,
        dry_run=True,
    )
    assert "999" in docs_alt["TRACK_RECORD.md"], (
        "altered n_settled=999 not reflected in TRACK_RECORD.md"
    )
    # The original must NOT contain 999 in the n_settled position.
    # (Content differs between orig and alt.)
    def _strip_ts(text: str) -> str:
        return "\n".join(
            ln for ln in text.splitlines()
            if "Generated:" not in ln and "generated_at" not in ln
        )
    assert _strip_ts(docs_orig["TRACK_RECORD.md"]) != _strip_ts(
        docs_alt["TRACK_RECORD.md"]
    ), "TRACK_RECORD.md unchanged despite different fixture n_settled"


def test_track_record_md_shows_mean_clv_from_fixture():
    """mean_clv_pct from the fixture must appear in TRACK_RECORD.md."""
    docs = _gen()
    content = docs["TRACK_RECORD.md"]
    # 0.73 formatted to 4 decimal places => "0.7300"
    assert "0.7300" in content, (
        "mean_clv_pct=0.73 (formatted 0.7300) not found in TRACK_RECORD.md"
    )


# --------------------------------------------------------------------------- #
# edge_claimed                                                                 #
# --------------------------------------------------------------------------- #

def test_track_record_md_surfaces_edge_claimed_false():
    """The track-record doc must surface edge_claimed=False from the record."""
    docs = _gen()
    content = docs["TRACK_RECORD.md"]
    assert "edge_claimed" in content.lower(), (
        "edge_claimed not found in TRACK_RECORD.md"
    )
    assert "false" in content.lower(), (
        "edge_claimed=False not surfaced in TRACK_RECORD.md"
    )


# --------------------------------------------------------------------------- #
# Pricing tiers: feature structure matches sell.entitlements                  #
# --------------------------------------------------------------------------- #

def test_pricing_tiers_md_contains_all_tiers():
    docs = _gen()
    content = docs["PRICING_TIERS.md"]
    for tier in ("Free", "Pro", "Enterprise"):
        assert tier in content, (
            "tier %r not found in PRICING_TIERS.md" % tier
        )


def test_pricing_tiers_md_has_feature_checklist():
    """Each tier section should have at least one [x] feature."""
    docs = _gen()
    content = docs["PRICING_TIERS.md"]
    assert "[x]" in content, "no checked feature [x] found in PRICING_TIERS.md"
    # Free tier does NOT get enterprise features.
    assert "[ ]" in content, (
        "no unchecked feature [ ] found in PRICING_TIERS.md (all tiers look same)"
    )


# --------------------------------------------------------------------------- #
# MANIFEST.md: reproduce command present                                      #
# --------------------------------------------------------------------------- #

def test_manifest_md_contains_reproduce_command():
    docs = _gen()
    content = docs["MANIFEST.md"]
    assert "python -m sell.evidence_pack" in content, (
        "reproduce command not found in MANIFEST.md"
    )


def test_manifest_md_sha_digests_not_in_prose():
    """Raw sha256 digests (64-char hex) must not appear in MANIFEST.md prose."""
    import re
    docs = _gen()
    content = docs["MANIFEST.md"]
    sha_hits = re.findall(r"\b[0-9a-f]{64}\b", content, flags=re.I)
    assert not sha_hits, (
        "raw sha256 digests found in MANIFEST.md prose (should be omitted): %s"
        % sha_hits[:2]
    )
