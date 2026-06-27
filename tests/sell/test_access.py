"""tests.sell.test_access -- per-file tests for the sell access layer.

Tests:
  * key issuance and verification (valid key accepted)
  * forged / tampered key denied
  * plan gating -- out-of-plan feature denied, in-plan feature allowed
  * tenant isolation -- tenant A cannot read tenant B's namespace
  * usage meter increments correctly

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/sell/test_access.py -q
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import time

import pytest

# -- authz -------------------------------------------------------------------
from sell.authz import issue_key, verify_key, key_metadata, EDGE_CLAIMED

_SECRET = "test-secret-do-not-use-in-production"


class TestIssueAndVerify:
    def test_valid_key_accepted(self):
        key = issue_key("acme", "pro", _secret=_SECRET)
        result = verify_key(key, _secret=_SECRET)
        assert result is not None
        tenant, plan = result
        assert tenant == "acme"
        assert plan == "pro"

    def test_different_plans(self):
        for plan in ("free", "pro", "enterprise"):
            key = issue_key("t1", plan, _secret=_SECRET)
            r = verify_key(key, _secret=_SECRET)
            assert r is not None
            assert r[1] == plan

    def test_forged_key_denied(self):
        key = issue_key("acme", "pro", _secret=_SECRET)
        # Tamper: flip the last char of the HMAC hex
        parts = key.rsplit(".", 1)
        assert len(parts) == 2
        mac = parts[1]
        bad_char = "0" if mac[-1] != "0" else "1"
        forged = parts[0] + "." + mac[:-1] + bad_char
        assert verify_key(forged, _secret=_SECRET) is None

    def test_wrong_secret_denied(self):
        key = issue_key("acme", "pro", _secret=_SECRET)
        assert verify_key(key, _secret="wrong-secret") is None

    def test_no_secret_denied(self):
        # With no env var and no override, verify_key returns None.
        key = issue_key("acme", "pro", _secret=_SECRET)
        old = os.environ.pop("SELL_API_SECRET", None)
        try:
            assert verify_key(key) is None
        finally:
            if old is not None:
                os.environ["SELL_API_SECRET"] = old

    def test_empty_key_denied(self):
        assert verify_key("", _secret=_SECRET) is None
        assert verify_key(None, _secret=_SECRET) is None  # type: ignore[arg-type]

    def test_garbage_key_denied(self):
        assert verify_key("aaaa.bbbbbbbb", _secret=_SECRET) is None

    def test_edge_claimed_is_false(self):
        assert EDGE_CLAIMED is False
        meta = key_metadata(
            issue_key("t", "free", _secret=_SECRET), _secret=_SECRET
        )
        assert meta is not None
        assert meta.get("edge_claimed") is False

    def test_issue_key_requires_nonempty_tenant(self):
        with pytest.raises(ValueError):
            issue_key("", "free", _secret=_SECRET)

    def test_issue_key_requires_nonempty_plan(self):
        with pytest.raises(ValueError):
            issue_key("acme", "", _secret=_SECRET)

    def test_issue_key_requires_secret(self):
        old = os.environ.pop("SELL_API_SECRET", None)
        try:
            with pytest.raises(ValueError):
                issue_key("acme", "pro")
        finally:
            if old is not None:
                os.environ["SELL_API_SECRET"] = old


# -- entitlements ------------------------------------------------------------
from sell.entitlements import allowed, plan_features, feature_min_plan, PLAN_TIERS


class TestEntitlements:
    def test_free_nba_allowed(self):
        assert allowed("free", "sport_nba") is True

    def test_free_mlb_denied(self):
        assert allowed("free", "sport_mlb") is False

    def test_pro_all_sports_allowed(self):
        for feat in ("sport_nba", "sport_mlb", "sport_soccer", "sport_tennis"):
            assert allowed("pro", feat) is True, feat

    def test_pro_evidence_pack_denied(self):
        assert allowed("pro", "evidence_pack") is False

    def test_enterprise_evidence_pack_allowed(self):
        assert allowed("enterprise", "evidence_pack") is True
        assert allowed("enterprise", "methodology_pdf") is True
        assert allowed("enterprise", "governance_artifacts") is True

    def test_enterprise_includes_pro_features(self):
        for feat in plan_features("pro"):
            assert allowed("enterprise", feat) is True, feat

    def test_unknown_plan_denied(self):
        assert allowed("superduper", "sport_nba") is False

    def test_unknown_feature_denied(self):
        assert allowed("enterprise", "guaranteed_profit") is False
        assert allowed("enterprise", "dollar_edge") is False

    def test_case_insensitive_plan(self):
        assert allowed("FREE", "sport_nba") is True
        assert allowed("Pro", "sport_mlb") is True

    def test_feature_min_plan_ordering(self):
        assert feature_min_plan("sport_nba") == "free"
        assert feature_min_plan("sport_mlb") == "pro"
        assert feature_min_plan("evidence_pack") == "enterprise"

    def test_feature_min_plan_unknown(self):
        assert feature_min_plan("not_a_feature") == ""

    def test_plan_tiers_ordered(self):
        # free < pro < enterprise: each higher tier has >= features
        tiers = PLAN_TIERS
        for i in range(len(tiers) - 1):
            lower = plan_features(tiers[i])
            higher = plan_features(tiers[i + 1])
            assert lower.issubset(higher), (
                "%s features not a subset of %s" % (tiers[i], tiers[i + 1])
            )


# -- tenancy -----------------------------------------------------------------
from sell.tenancy import namespace_for, TenancyError


class TestTenancy:
    def test_basic_path_resolution(self, tmp_path):
        ns = namespace_for("acme", root=tmp_path)
        p = ns.path("data.json")
        assert str(p).startswith(str(tmp_path))
        assert "acme" in str(p)

    def test_tenant_a_cannot_read_tenant_b(self, tmp_path):
        """Tenant A's Namespace cannot resolve into tenant B's root."""
        ns_a = namespace_for("tenant-a", root=tmp_path)
        ns_b = namespace_for("tenant-b", root=tmp_path)
        # Write a file into B's namespace
        ns_b.ensure_dir()
        b_file = ns_b.root / "secret.txt"
        b_file.write_text("b-secret", encoding="ascii")
        # Attempt to resolve tenant B's path via tenant A's namespace
        with pytest.raises(TenancyError):
            ns_a.resolve("../tenant-b/secret.txt")

    def test_path_traversal_denied(self, tmp_path):
        ns = namespace_for("acme", root=tmp_path)
        with pytest.raises(TenancyError):
            ns.resolve("../../etc/passwd")

    def test_absolute_path_injection_denied(self, tmp_path):
        ns = namespace_for("acme", root=tmp_path)
        with pytest.raises(TenancyError):
            ns.resolve("/etc/passwd")

    def test_safe_paths_allowed(self, tmp_path):
        ns = namespace_for("acme", root=tmp_path)
        p = ns.path("subdir/usage.jsonl")
        assert p.name == "usage.jsonl"

    def test_ensure_dir_creates(self, tmp_path):
        ns = namespace_for("newcorp", root=tmp_path)
        d = ns.ensure_dir()
        assert d.exists()

    def test_invalid_tenant_id_rejected(self, tmp_path):
        with pytest.raises(TenancyError):
            namespace_for("../bad", root=tmp_path)
        with pytest.raises(TenancyError):
            namespace_for("", root=tmp_path)
        # Uppercase is auto-normalised to lowercase; the normalised ID is fine.
        ns = namespace_for("UPPER", root=tmp_path)
        assert ns.tenant == "upper"
        # Chars outside [a-z0-9_-] after normalisation are rejected.
        with pytest.raises(TenancyError):
            namespace_for("tenant with spaces", root=tmp_path)
        with pytest.raises(TenancyError):
            namespace_for("tenant@evil.com", root=tmp_path)


# -- usage_meter -------------------------------------------------------------
from sell.usage_meter import record, usage, total_calls, within_quota


class TestUsageMeter:
    def _ns(self, tmp_path: pathlib.Path, tenant: str):
        return namespace_for(tenant, root=tmp_path)

    def test_single_record_increments(self, tmp_path):
        ns = self._ns(tmp_path, "acme")
        record("acme", "/predict/slate", _ns=ns)
        counts = usage("acme", _ns=ns)
        assert counts.get("/predict/slate", 0) == 1

    def test_multiple_records_accumulate(self, tmp_path):
        ns = self._ns(tmp_path, "beta")
        for _ in range(5):
            record("beta", "/predict/slate", _ns=ns)
        record("beta", "/clv/report", _ns=ns)
        counts = usage("beta", _ns=ns)
        assert counts["/predict/slate"] == 5
        assert counts["/clv/report"] == 1

    def test_total_calls(self, tmp_path):
        ns = self._ns(tmp_path, "gamma")
        for _ in range(3):
            record("gamma", "/predict/slate", _ns=ns)
        record("gamma", "/clv/report", _ns=ns)
        assert total_calls("gamma", _ns=ns) == 4

    def test_empty_tenant_returns_zero(self, tmp_path):
        ns = self._ns(tmp_path, "empty-co")
        assert total_calls("empty-co", _ns=ns) == 0
        assert usage("empty-co", _ns=ns) == {}

    def test_within_quota_passes(self, tmp_path):
        ns = self._ns(tmp_path, "delta")
        record("delta", "/predict/slate", _ns=ns)
        assert within_quota("delta", 5, _ns=ns) is True

    def test_within_quota_fails_at_limit(self, tmp_path):
        ns = self._ns(tmp_path, "epsilon")
        for _ in range(3):
            record("epsilon", "/predict/slate", _ns=ns)
        assert within_quota("epsilon", 3, _ns=ns) is False

    def test_zero_quota_always_false(self, tmp_path):
        ns = self._ns(tmp_path, "zeta")
        assert within_quota("zeta", 0, _ns=ns) is False

    def test_record_never_raises_on_bad_tenant(self):
        # record() must not raise even with a weird tenant that can't be
        # resolved to a filesystem path. It swallows the error silently.
        try:
            record("../escape", "/any")
        except Exception as exc:
            pytest.fail("record() raised unexpectedly: %s" % exc)

    def test_tenant_isolation_in_usage(self, tmp_path):
        """Tenant A's usage does not appear in tenant B's usage."""
        ns_a = self._ns(tmp_path, "corp-a")
        ns_b = self._ns(tmp_path, "corp-b")
        record("corp-a", "/predict/slate", _ns=ns_a)
        record("corp-a", "/predict/slate", _ns=ns_a)
        assert total_calls("corp-b", _ns=ns_b) == 0
        assert "/predict/slate" not in usage("corp-b", _ns=ns_b)
