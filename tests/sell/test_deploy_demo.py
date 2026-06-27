"""tests/sell/test_deploy_demo.py -- M12 deploy bundle + demo seed tests.

Covers:
  1. boot_sell.ps1 -DryRun: Procfile/compose parse + service list present in
     output (without starting any process).
  2. demo_seed: deterministic, idempotent, no $ keys (honesty linter).
  3. Procfile.sell / docker-compose.sell.yml: parse + service names present.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/sell/test_deploy_demo.py -q

INVARIANTS: per-file only; no full-suite invocation; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo(rel: str) -> Path:
    return _REPO / rel


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="ascii"))


# ---------------------------------------------------------------------------
# 1. Procfile.sell -- parse + service names
# ---------------------------------------------------------------------------

class TestProcfileSell:
    """Procfile.sell declares exactly the expected service names."""

    EXPECTED_SERVICES = {"sell_api", "auto_api", "paper_loop"}
    PROCFILE = _repo("deploy/Procfile.sell")

    def test_procfile_exists(self) -> None:
        assert self.PROCFILE.exists(), "deploy/Procfile.sell not found"

    def test_service_names_present(self) -> None:
        text = self.PROCFILE.read_text(encoding="ascii")
        found = set()
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                m = re.match(r"^(\w+)\s*:", line)
                if m:
                    found.add(m.group(1))
        missing = self.EXPECTED_SERVICES - found
        assert not missing, "Procfile.sell missing services: %s" % sorted(missing)

    def test_no_dollar_edge_in_procfile(self) -> None:
        from governance.honesty_linter import lint_text
        text = self.PROCFILE.read_text(encoding="ascii")
        result = lint_text(text)
        assert result["clean"], "Procfile.sell fails honesty lint: %s" % result["violations"]


# ---------------------------------------------------------------------------
# 2. docker-compose.sell.yml -- parse + service names
# ---------------------------------------------------------------------------

class TestDockerComposeSell:
    """docker-compose.sell.yml declares the expected services."""

    COMPOSE = _repo("deploy/docker-compose.sell.yml")
    EXPECTED_SERVICES = {"sell_api", "auto_api", "paper_loop"}

    def test_compose_exists(self) -> None:
        assert self.COMPOSE.exists(), "deploy/docker-compose.sell.yml not found"

    def test_service_names_in_compose(self) -> None:
        """Service names appear in the YAML (no YAML dep: scan for keys)."""
        text = self.COMPOSE.read_text(encoding="ascii")
        for svc in self.EXPECTED_SERVICES:
            assert svc in text, "compose missing service: %s" % svc

    def test_edge_claimed_label_present(self) -> None:
        text = self.COMPOSE.read_text(encoding="ascii")
        assert "edge_claimed" in text.lower(), "compose should label edge_claimed=false"

    def test_human_gated_comment_present(self) -> None:
        text = self.COMPOSE.read_text(encoding="ascii")
        assert "HUMAN" in text, "compose must document human-gated public deploy"

    def test_no_banned_tokens_in_compose(self) -> None:
        from governance.honesty_linter import lint_text
        text = self.COMPOSE.read_text(encoding="ascii")
        result = lint_text(text)
        assert result["clean"], "docker-compose.sell.yml fails honesty lint: %s" % result["violations"]


# ---------------------------------------------------------------------------
# 3. boot_sell.ps1 -- DryRun prints process graph (parse the script text)
# ---------------------------------------------------------------------------

class TestBootSellScript:
    """boot_sell.ps1 contains the expected process graph markers."""

    SCRIPT = _repo("deploy/boot_sell.ps1")
    REQUIRED_MARKERS = [
        "sell_api",
        "auto_api",
        "DryRun",
        "HUMAN",
        "edge_claimed",
    ]

    def test_script_exists(self) -> None:
        assert self.SCRIPT.exists(), "deploy/boot_sell.ps1 not found"

    def test_required_markers_in_script(self) -> None:
        text = self.SCRIPT.read_text(encoding="ascii")
        for marker in self.REQUIRED_MARKERS:
            assert marker in text, "boot_sell.ps1 missing marker: %r" % marker

    def test_no_dollar_edge_in_script(self) -> None:
        from governance.honesty_linter import lint_text
        text = self.SCRIPT.read_text(encoding="ascii")
        result = lint_text(text)
        assert result["clean"], "boot_sell.ps1 fails honesty lint: %s" % result["violations"]


# ---------------------------------------------------------------------------
# 4. demo_seed -- deterministic, idempotent, no $ keys
# ---------------------------------------------------------------------------

class TestDemoSeed:
    """sell.demo_seed produces correct, honest, idempotent output."""

    def test_seed_runs_and_writes_files(self, tmp_path: Path) -> None:
        from sell.demo_seed import seed
        written = seed(tmp_path)
        assert "snapshot" in written
        assert "track_record" in written
        assert written["snapshot"].exists()
        assert written["track_record"].exists()

    def test_seed_is_idempotent(self, tmp_path: Path) -> None:
        from sell.demo_seed import seed
        written1 = seed(tmp_path)
        written2 = seed(tmp_path)
        snap1 = written1["snapshot"].read_text(encoding="ascii")
        snap2 = written2["snapshot"].read_text(encoding="ascii")
        assert snap1 == snap2, "demo_seed is not idempotent: snapshot differs"
        tr1 = written1["track_record"].read_text(encoding="ascii")
        tr2 = written2["track_record"].read_text(encoding="ascii")
        assert tr1 == tr2, "demo_seed is not idempotent: track_record differs"

    def test_snapshot_no_dollar_keys(self, tmp_path: Path) -> None:
        from sell.demo_seed import seed
        from governance.honesty_linter import lint_obj
        written = seed(tmp_path)
        obj = _load_json(written["snapshot"])
        result = lint_obj(obj)
        assert result["clean"], "snapshot.json fails honesty lint: %s" % result["violations"]

    def test_track_record_no_dollar_keys(self, tmp_path: Path) -> None:
        from sell.demo_seed import seed
        from governance.honesty_linter import lint_obj
        written = seed(tmp_path)
        obj = _load_json(written["track_record"])
        result = lint_obj(obj)
        assert result["clean"], "track_record.json fails honesty lint: %s" % result["violations"]

    def test_edge_claimed_is_false(self, tmp_path: Path) -> None:
        from sell.demo_seed import seed
        written = seed(tmp_path)
        obj = _load_json(written["track_record"])
        assert obj.get("edge_claimed") is False, (
            "track_record.json must have edge_claimed=false"
        )

    def test_no_dollar_sign_in_any_key(self, tmp_path: Path) -> None:
        """No JSON key in any seeded file contains a literal dollar sign."""
        from sell.demo_seed import seed

        def _check_keys(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full = "%s.%s" % (path, k) if path else k
                    assert "$" not in k, "dollar-sign key found: %r" % full
                    _check_keys(v, full)
            elif isinstance(obj, (list, tuple)):
                for i, v in enumerate(obj):
                    _check_keys(v, "%s[%d]" % (path, i))

        written = seed(tmp_path)
        for name, p in written.items():
            if p.suffix == ".json":
                _check_keys(_load_json(p), name)

    def test_no_network_call(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """demo_seed must not make any network calls."""
        import socket

        def _no_network(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("demo_seed must not access the network")

        monkeypatch.setattr(socket, "getaddrinfo", _no_network)
        from sell.demo_seed import seed
        seed(tmp_path)  # must not raise

    def test_calibration_status_is_demo(self, tmp_path: Path) -> None:
        """Calibration block must carry status='demo_seed', not a real number."""
        from sell.demo_seed import seed
        written = seed(tmp_path)
        obj = _load_json(written["track_record"])
        cal = obj.get("calibration", {})
        assert cal.get("status") == "demo_seed", (
            "calibration.status should be 'demo_seed'; got %r" % cal.get("status")
        )
