"""Focused tests for the static exception-handler census."""

from __future__ import annotations

import ast

from scripts.platformkit.tracking.silent_handler_census import (
    _body_kind,
    _exc_name,
    _is_silent,
    census,
)


def _handler(src: str) -> ast.ExceptHandler:
    tree = ast.parse(src)
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))


def test_pass_body_is_silent_and_logged_body_is_not() -> None:
    swallow = _handler("try:\n    f()\nexcept Exception:\n    pass\n")
    talks = _handler("try:\n    f()\nexcept Exception:\n    print('boom')\n")
    assert _body_kind(swallow) == "pass"
    assert _is_silent(_body_kind(swallow)) is True
    assert _body_kind(talks) == "logged"
    assert _is_silent(_body_kind(talks)) is False


def test_reraise_is_not_silent() -> None:
    node = _handler("try:\n    f()\nexcept ValueError:\n    raise RuntimeError('x')\n")
    assert _body_kind(node) == "reraise"
    assert _is_silent(_body_kind(node)) is False


def test_bare_except_is_named_BARE() -> None:
    assert _exc_name(_handler("try:\n    f()\nexcept:\n    pass\n")) == "BARE"
    assert _exc_name(_handler("try:\n    f()\nexcept KeyError:\n    pass\n")) == "KeyError"


def test_census_reports_function_and_skips_absent_files(tmp_path) -> None:
    mod = tmp_path / "pkg"
    mod.mkdir()
    (mod / "m.py").write_text(
        "def outer():\n    try:\n        g()\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    rows = census(tmp_path, ["pkg/m.py", "pkg/does_not_exist.py"])
    assert len(rows) == 1
    assert rows[0]["function"] == "outer"
    assert rows[0]["silent"] is True
    assert rows[0]["catches"] == "Exception"
