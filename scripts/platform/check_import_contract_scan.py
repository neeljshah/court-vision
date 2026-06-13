"""check_import_contract_scan.py — AST-walk helpers for check_import_contract.

Holds the allowlist constants, the Violation type, and the per-file AST
checkers.  The public CLI entry point and ``check()`` live in
``check_import_contract``, which imports everything from here.

Nothing outside ``check_import_contract`` should import from this module
directly — treat it as a private implementation detail.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Top-level package names (first dotted component) that kernel modules MAY import.
# Everything else is a violation.  "kernel" itself is also implicitly allowed.
_KERNEL_ALLOWLIST: frozenset[str] = frozenset(
    {
        # stdlib — represented by the _is_stdlib sentinel below; this set is
        # for non-stdlib third-party packages that are explicitly permitted.
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "xgboost",
        "torch",
        "fastapi",
        "starlette",      # fastapi's underlying framework — allowed transitively
        "pydantic",       # fastapi models — allowed
        "kernel",
    }
)

# Top-level names that are *always* violations when found in kernel/ code.
_KERNEL_BANNED_TOPS: frozenset[str] = frozenset(
    {
        "src",
        "domains",
        "api",
        "scripts",
        "nba_api",
        # sport-named libraries
        "nba",
        "nfl",
        "mlb",
        "nhl",
        "soccer",
        "football",
    }
)

# Python 3.9 stdlib module names (complete set from sys.stdlib_module_names
# when available, with a conservative hand-rolled fallback for 3.9 which does
# NOT expose sys.stdlib_module_names — introduced in 3.10).
_STDLIB_TOPS: frozenset[str]
if hasattr(sys, "stdlib_module_names"):
    _STDLIB_TOPS = frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
else:
    # Hand-rolled conservative set covering the modules actually used in this
    # codebase.  Err on the side of inclusion (false-negative < false-positive).
    _STDLIB_TOPS = frozenset(
        {
            "__future__", "_thread", "abc", "ast", "asyncio", "atexit",
            "base64", "bdb", "binascii", "bisect", "builtins", "bz2",
            "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code",
            "codecs", "codeop", "colorsys", "compileall", "concurrent",
            "configparser", "contextlib", "contextvars", "copy", "copyreg",
            "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm",
            "decimal", "difflib", "dis", "doctest", "email", "encodings",
            "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
            "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
            "getpass", "gettext", "glob", "grp", "gzip", "hashlib", "heapq",
            "hmac", "html", "http", "idlelib", "imaplib", "importlib",
            "inspect", "io", "ipaddress", "itertools", "json", "keyword",
            "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox",
            "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
            "netrc", "nis", "nntplib", "numbers", "operator", "optparse",
            "os", "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools",
            "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix",
            "posixpath", "pprint", "profile", "pstats", "pty", "pwd", "py_compile",
            "pyclbr", "pydoc", "queue", "quopri", "random", "re", "readline",
            "reprlib", "resource", "rlcompleter", "runpy", "sched", "secrets",
            "select", "selectors", "shelve", "shlex", "shutil", "signal",
            "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
            "spwd", "sqlite3", "sre_compile", "sre_constants", "sre_parse",
            "ssl", "stat", "statistics", "string", "stringprep", "struct",
            "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
            "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
            "textwrap", "threading", "time", "timeit", "tkinter", "token",
            "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "tty",
            "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
            "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
            "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
            "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
            "typing_extensions",  # near-stdlib shim; ubiquitous in typed code
        }
    )


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Violation(NamedTuple):
    """A single import-contract violation."""

    path: str
    line: int
    kind: str   # "KERNEL_IMPORT_VIOLATION" | "CROSS_ADAPTER_VIOLATION"
    module: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.kind}: {self.module}"


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def _top(module: str) -> str:
    """Return the top-level package name of a dotted module string."""
    return module.split(".")[0]


def _is_allowed_kernel_import(module: str) -> bool:
    """Return True if *module* is permitted inside kernel/ code."""
    top = _top(module)
    if top in _STDLIB_TOPS:
        return True
    if top in _KERNEL_ALLOWLIST:
        return True
    return False


def _collect_imports(tree: ast.AST) -> List[tuple[int, str]]:
    """Walk *tree* and yield ``(lineno, module_name)`` for every import."""
    results: List[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            # ``from . import foo`` → module is None (relative); skip
            if node.module is not None:
                results.append((node.lineno, node.module))
    return results


def _parse(path: Path) -> Optional[ast.AST]:
    """Parse *path* and return the AST, or None on SyntaxError."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# Per-file checkers
# ---------------------------------------------------------------------------

def _check_kernel_file(py_path: Path) -> List[Violation]:
    """Return violations for a single kernel/ source file."""
    tree = _parse(py_path)
    if tree is None:
        return []
    violations: List[Violation] = []
    for lineno, module in _collect_imports(tree):
        top = _top(module)
        # Explicitly banned tops → always a violation
        if top in _KERNEL_BANNED_TOPS:
            violations.append(
                Violation(
                    path=str(py_path),
                    line=lineno,
                    kind="KERNEL_IMPORT_VIOLATION",
                    module=module,
                )
            )
            continue
        # Not in allowlist and not stdlib → also a violation
        if not _is_allowed_kernel_import(module):
            violations.append(
                Violation(
                    path=str(py_path),
                    line=lineno,
                    kind="KERNEL_IMPORT_VIOLATION",
                    module=module,
                )
            )
    return violations


def _check_domain_file(py_path: Path, own_domain: str) -> List[Violation]:
    """Return cross-adapter violations for a single domains/<own_domain>/ file."""
    tree = _parse(py_path)
    if tree is None:
        return []
    violations: List[Violation] = []
    for lineno, module in _collect_imports(tree):
        # Flag imports of domains.<other> where other != own_domain
        if module == "domains" or module.startswith("domains."):
            parts = module.split(".")
            # parts[0]="domains", parts[1]=<sport> if present
            if len(parts) >= 2 and parts[1] != own_domain:
                violations.append(
                    Violation(
                        path=str(py_path),
                        line=lineno,
                        kind="CROSS_ADAPTER_VIOLATION",
                        module=module,
                    )
                )
    return violations
