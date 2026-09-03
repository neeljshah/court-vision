"""S188 deploy tree gate construct tests."""
from __future__ import annotations

import sys

from scripts.platformkit.ops import deploy_tree_gate as gate


def test_tree_list_is_exhaustive_and_control_passes(capsys) -> None:
    assert gate.TREE_IMPORTS == (
        "ops", "kernel", "governance", "data_registry", "improve",
        "frontend", "src", "supervisor.supervisor")

    assert gate.main(["--python", sys.executable]) == 0
    output = capsys.readouterr().out
    assert output == "TREES: 8/8 OK\n"


def test_any_failed_tree_is_named_and_exits_nonzero(monkeypatch, capsys) -> None:
    def _one_failure(modules, python, cwd=None):
        assert tuple(modules) == gate.TREE_IMPORTS
        return {module: ("ModuleNotFoundError: absent" if module == "ops" else None)
                for module in modules}

    monkeypatch.setattr(gate, "check_imports", _one_failure)
    assert gate.main(["--python", sys.executable]) == 1
    output = capsys.readouterr().out
    assert output == (
        "TREES: 7/8 OK\n"
        "FAIL ops -- ModuleNotFoundError: absent\n")
