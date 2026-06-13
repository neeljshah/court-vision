"""
scripts/platformkit/literal_extract.py

Shared AST-based literal extraction helper.

Extracts literal values from Python source files WITHOUT importing or
executing the target module — safe even when the module depends on
cv2, torch, or other heavy/unavailable packages.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_source(file_path: str | Path) -> str:
    """Read source text, handling CRLF and common encodings."""
    path = Path(file_path)
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            # Normalise Windows line endings so ast.parse is happy
            return text.replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {file_path} with utf-8 / latin-1")


def _parse(file_path: str | Path) -> tuple[ast.Module, str]:
    """Return (parsed AST, source text) for *file_path*."""
    src = _read_source(file_path)
    try:
        tree = ast.parse(src, filename=str(file_path))
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in {file_path}: {exc}") from exc
    return tree, src


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_assignment(
    file_path: str | Path,
    name: str,
    *,
    qualname: str | None = None,
) -> Any:
    """
    Find a module-level (or class-level) assignment ``name = <literal>``
    and return its evaluated value.

    Parameters
    ----------
    file_path:
        Path to the Python source file.
    name:
        The bare variable name on the left-hand side (e.g. ``"VERSION"``).
    qualname:
        If given, restrict the search to assignments inside the class whose
        name matches *qualname* (simple single-level class name only).
        E.g. ``qualname="Config"`` finds ``Config.VERSION = …``.

    Returns
    -------
    The Python value produced by ``ast.literal_eval``.

    Raises
    ------
    ValueError
        If the name is not found, or the RHS is not a literal.
    """
    tree, _ = _parse(file_path)

    def _search_body(stmts: list[ast.stmt]) -> Any:
        for node in stmts:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        return _eval_literal(node.value, name, file_path)
            elif isinstance(node, ast.AnnAssign):
                target = node.target
                if (
                    isinstance(target, ast.Name)
                    and target.id == name
                    and node.value is not None
                ):
                    return _eval_literal(node.value, name, file_path)
        raise ValueError(
            f"Name {name!r} not found as a module-level assignment in {file_path}"
        )

    if qualname is None:
        return _search_body(tree.body)

    # Search inside the named class
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == qualname:
            return _search_body(node.body)

    raise ValueError(
        f"Class {qualname!r} not found in {file_path}"
    )


def extract_dict_value(
    file_path: str | Path,
    dict_name: str,
    key: str,
) -> Any:
    """
    For a module-level dict literal ``dict_name = { … }``, return the value
    associated with *key*.

    Parameters
    ----------
    file_path:
        Path to the Python source file.
    dict_name:
        The variable name of the dict (e.g. ``"CONFIG"``).
    key:
        The string key to look up (e.g. ``"timeout"``).

    Returns
    -------
    The Python value produced by ``ast.literal_eval`` for that key.

    Raises
    ------
    ValueError
        If the dict is not found, is not a literal dict, or the key is absent.
    """
    tree, _ = _parse(file_path)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == dict_name):
                continue
            if not isinstance(node.value, ast.Dict):
                raise ValueError(
                    f"{dict_name!r} in {file_path} is not a dict literal"
                )
            d = node.value
            for k_node, v_node in zip(d.keys, d.values):
                if k_node is None:
                    # **-unpacking — skip
                    continue
                try:
                    k = ast.literal_eval(k_node)
                except ValueError:
                    continue
                if k == key:
                    return _eval_literal(v_node, f"{dict_name}[{key!r}]", file_path)
            raise ValueError(
                f"Key {key!r} not found in dict {dict_name!r} in {file_path}"
            )

    raise ValueError(
        f"Dict {dict_name!r} not found as a module-level assignment in {file_path}"
    )


def extract_line_literal(
    file_path: str | Path,
    lineno: int,
    pattern: str,
) -> float | int:
    """
    Regex-extract a numeric literal from a specific source line.

    Useful for values embedded inside expressions or conditions, e.g.:
    ``if abs(margin) >= 18:``  →  ``extract_line_literal(f, 42, r'>=\\s*(\\d+)')``

    Parameters
    ----------
    file_path:
        Path to the Python source file.
    lineno:
        1-based line number.
    pattern:
        A regex with exactly one capturing group matching the numeric literal.
        The group may contain an optional leading ``-`` for negatives.

    Returns
    -------
    ``int`` if the matched text has no decimal point, otherwise ``float``.

    Raises
    ------
    ValueError
        If *lineno* is out of range, or the pattern does not match.
    """
    src = _read_source(file_path)
    lines = src.splitlines()
    if lineno < 1 or lineno > len(lines):
        raise ValueError(
            f"Line {lineno} out of range (file has {len(lines)} lines): {file_path}"
        )
    line = lines[lineno - 1]
    m = re.search(pattern, line)
    if not m:
        raise ValueError(
            f"Pattern {pattern!r} did not match line {lineno} of {file_path}: {line!r}"
        )
    raw = m.group(1)
    return float(raw) if "." in raw else int(raw)


# ---------------------------------------------------------------------------
# Internal — shared literal evaluator
# ---------------------------------------------------------------------------

def _eval_literal(node: ast.expr, label: str, file_path: str | Path) -> Any:
    """Try ``ast.literal_eval`` on *node*; raise a clear error if it fails."""
    try:
        return ast.literal_eval(node)
    except ValueError as exc:
        raise ValueError(
            f"Value of {label!r} in {file_path} is not a literal "
            f"(got AST node {type(node).__name__}): {exc}"
        ) from exc
