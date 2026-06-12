"""kernel.testing.golden — Exact-equality golden artifact helpers.

Provides save/load/compare for golden artifacts used in conformance and
migration tests.  Equality is EXACT: ``np.array_equal`` for arrays,
``==`` for JSON-serialisable scalars/structures.  Approximate comparisons
(``np.allclose``) are deliberately absent.

Import rules (R10 compliance)
-----------------------------
This module imports ONLY stdlib and ``numpy``.  No ``domains``, no ``src``,
no heavy third-party libraries.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Union

import numpy as np

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MANIFEST_FILENAME = "MANIFEST.sha256"
_ARRAY_EXT = ".npy"
_JSON_EXT = ".json"


def _golden_path(name: str, golden_dir: pathlib.Path) -> pathlib.Path:
    """Return the stored path for *name*, searching for .npy then .json."""
    for ext in (_ARRAY_EXT, _JSON_EXT):
        p = golden_dir / (name + ext)
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Golden artifact '{name}' not found in {golden_dir} "
        f"(tried {_ARRAY_EXT} and {_JSON_EXT})"
    )


def _sha256(path: pathlib.Path) -> str:
    """Return the hex SHA-256 digest of the file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_array(data: Any) -> bool:
    return isinstance(data, np.ndarray)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_golden(
    name: str,
    data: Union[np.ndarray, Any],
    golden_dir: Union[str, pathlib.Path],
) -> pathlib.Path:
    """Persist *data* as a golden artifact named *name*.

    Arrays are stored via ``np.save`` at full precision; all other
    JSON-serialisable objects (scalars, dicts, lists) are stored as JSON.

    Parameters
    ----------
    name:
        Logical name of the artifact (no extension).
    data:
        The value to persist.  Must be either a ``numpy.ndarray`` or a
        JSON-serialisable object.
    golden_dir:
        Directory in which to write the file (created if absent).

    Returns
    -------
    pathlib.Path
        The path of the file that was written.
    """
    golden_dir = pathlib.Path(golden_dir)
    golden_dir.mkdir(parents=True, exist_ok=True)

    if _is_array(data):
        path = golden_dir / (name + _ARRAY_EXT)
        np.save(path, data, allow_pickle=False)
    else:
        path = golden_dir / (name + _JSON_EXT)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    return path


def load_golden(
    name: str,
    golden_dir: Union[str, pathlib.Path],
) -> Union[np.ndarray, Any]:
    """Restore the golden artifact named *name*.

    Parameters
    ----------
    name:
        Logical name of the artifact (no extension).
    golden_dir:
        Directory that contains the persisted file.

    Returns
    -------
    numpy.ndarray | Any
        The restored value.
    """
    golden_dir = pathlib.Path(golden_dir)
    path = _golden_path(name, golden_dir)

    if path.suffix == _ARRAY_EXT:
        return np.load(path, allow_pickle=False)

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def compare_golden(
    name: str,
    current: Union[np.ndarray, Any],
    golden_dir: Union[str, pathlib.Path],
) -> tuple[bool, str]:
    """Compare *current* against the stored golden for *name*.

    Uses EXACT equality: ``np.array_equal`` for arrays (never
    ``np.allclose``), ``==`` for everything else.

    Parameters
    ----------
    name:
        Logical name of the artifact.
    current:
        The current value to compare.
    golden_dir:
        Directory that contains the stored golden.

    Returns
    -------
    tuple[bool, str]
        ``(True, "ok")`` on exact match, or
        ``(False, <precise diff message>)`` on any mismatch.
    """
    golden_dir = pathlib.Path(golden_dir)

    try:
        stored = load_golden(name, golden_dir)
    except FileNotFoundError as exc:
        return False, str(exc)

    # --- array branch ---
    if _is_array(stored) or _is_array(current):
        if not _is_array(stored):
            return False, (
                f"Golden '{name}': stored is {type(stored).__name__} "
                f"but current is numpy.ndarray"
            )
        if not _is_array(current):
            return False, (
                f"Golden '{name}': stored is numpy.ndarray "
                f"but current is {type(current).__name__}"
            )
        # shape check
        if stored.shape != current.shape:
            return False, (
                f"Golden '{name}': shape mismatch — "
                f"stored {stored.shape} vs current {current.shape}"
            )
        # dtype check
        if stored.dtype != current.dtype:
            return False, (
                f"Golden '{name}': dtype mismatch — "
                f"stored {stored.dtype} vs current {current.dtype}"
            )
        # exact value check
        if not np.array_equal(stored, current):
            diff_mask = stored != current
            n_diff = int(diff_mask.sum())
            first_idx = tuple(int(i) for i in np.argwhere(diff_mask)[0])
            return False, (
                f"Golden '{name}': {n_diff} element(s) differ; "
                f"first mismatch at index {first_idx}: "
                f"stored={stored[first_idx]!r} current={current[first_idx]!r}"
            )
        return True, "ok"

    # --- JSON-able branch ---
    if stored != current:
        return False, (
            f"Golden '{name}': value mismatch — "
            f"stored={stored!r} current={current!r}"
        )
    return True, "ok"


def write_manifest(golden_dir: Union[str, pathlib.Path]) -> pathlib.Path:
    """Write a SHA-256 manifest for every golden file in *golden_dir*.

    The manifest is written to ``MANIFEST.sha256`` inside *golden_dir*.
    Each line has the form ``<hex-digest>  <filename>``.

    Parameters
    ----------
    golden_dir:
        Directory containing golden artifacts.

    Returns
    -------
    pathlib.Path
        Path of the manifest file that was written.
    """
    golden_dir = pathlib.Path(golden_dir)
    manifest_path = golden_dir / _MANIFEST_FILENAME

    entries: list[str] = []
    for path in sorted(golden_dir.iterdir()):
        if path.name == _MANIFEST_FILENAME or path.is_dir():
            continue
        entries.append(f"{_sha256(path)}  {path.name}")

    manifest_path.write_text("\n".join(entries) + ("\n" if entries else ""),
                              encoding="utf-8")
    return manifest_path


def verify_manifest(golden_dir: Union[str, pathlib.Path]) -> tuple[bool, str]:
    """Verify every golden file against the stored SHA-256 manifest.

    Parameters
    ----------
    golden_dir:
        Directory that contains golden artifacts and ``MANIFEST.sha256``.

    Returns
    -------
    tuple[bool, str]
        ``(True, "ok")`` if all digests match, or
        ``(False, <details>)`` listing every changed / missing file.
    """
    golden_dir = pathlib.Path(golden_dir)
    manifest_path = golden_dir / _MANIFEST_FILENAME

    if not manifest_path.exists():
        return False, f"Manifest not found: {manifest_path}"

    expected: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, fname = line.split("  ", 1)
        expected[fname] = digest

    errors: list[str] = []
    for fname, digest in expected.items():
        path = golden_dir / fname
        if not path.exists():
            errors.append(f"missing: {fname}")
            continue
        actual = _sha256(path)
        if actual != digest:
            errors.append(f"digest changed: {fname} (expected {digest[:8]}… got {actual[:8]}…)")

    if errors:
        return False, "; ".join(errors)
    return True, "ok"
