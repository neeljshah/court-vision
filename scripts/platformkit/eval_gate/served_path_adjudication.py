"""served_path_adjudication.py -- S452 REPORT ONLY construct probes.

Three static, source-derived checks for the served player-props path. Nothing
here imports src.prediction or api.stitch_router (both can hit private caches
or the network at import time) -- every check reads source text or parquet
footer metadata only, never executes a production loader and never decodes a
parquet column payload.

  classify_trainer_synthetic  -- RNG / simulation token scan over a line range
                                 of a source file (static text read only).
  rest_travel_statements      -- per-column min/max from pyarrow row-group
                                 statistics only; the joined 2024-25 row-level
                                 shift is out of this metadata-only scope and
                                 is always reported INSUFFICIENT, never as a
                                 passing construct.
  stitch_router_binding_proof -- selects the single predict_props call inside
                                 get_player_props via AST (refuses on zero or
                                 more than one candidate), and gets the
                                 callee's parameters through inspect.signature
                                 applied to a LOADER-SAFE STUB compiled from
                                 the parsed def node's line and argument list
                                 only (never an import of the production
                                 module); cross-checks that stub route against
                                 the plain AST parameter list and never
                                 fabricates a feature-value diff.

CLI: python -m scripts.platformkit.eval_gate.served_path_adjudication
     runs all three against the real repo paths and prints one JSON object
     (allow_nan=False) for byte-for-byte reproduction against the S452 memo.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import math
import re
from pathlib import Path
from typing import Optional

# ---- classify_trainer_synthetic ----

_RNG_LITERALS = (
    ("default_rng", "np.random.default_rng"),
    ("normal_call", ".normal("),
    ("choice_call", ".choice("),
)
_WORD_TOKEN_RE = re.compile(r"(?i)\b(simulate|noise)\b")


def _require_int_bound(name: str, value) -> Optional[dict]:
    """None when value is a real int (bool excluded); else a refusal dict.
    Never truncates a float via int() -- a fractional bound is a counted
    refusal, not a silently rounded one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return {"refused": "non_integer_line_bound",
                "reason": "%s must be a real int, got %s %r" % (name, type(value).__name__, value)}
    return None


def classify_trainer_synthetic(path: str, line_lo, line_hi) -> dict:
    """Static source-text scan of path[line_lo:line_hi] (1-indexed, inclusive)
    for RNG / simulation tokens. Never imports or executes the module. line_lo
    / line_hi must be real int (float and bool refused, never truncated)."""
    for name, value in (("line_lo", line_lo), ("line_hi", line_hi)):
        bad = _require_int_bound(name, value)
        if bad is not None:
            return {"path": path, "line_lo": line_lo, "line_hi": line_hi, **bad}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    lo = max(line_lo, 1)
    hi = min(line_hi, len(lines))
    matched: list = []
    for lineno in range(lo, hi + 1):
        text = lines[lineno - 1]
        for label, literal in _RNG_LITERALS:
            start = text.find(literal)
            while start != -1:
                matched.append({"line": lineno, "token": label, "text": literal})
                start = text.find(literal, start + 1)
        for m in _WORD_TOKEN_RE.finditer(text):
            matched.append({"line": lineno, "token": "word", "text": m.group(0).lower()})
    return {
        "path": path, "line_lo": lo, "line_hi": hi,
        "matched_tokens": matched, "token_count": len(matched),
        "synthetic": len(matched) > 0,
    }


# ---- rest_travel_statements ----

_REST_TRAVEL_COLUMNS = ("is_b2b", "is_b3b", "miles_traveled", "altitude_ft")
_SERVED_DEFAULT = 0.0


def rest_travel_statements(parquet_path: str) -> dict:
    """Per-column min/max from pyarrow row-group statistics only -- never
    decodes a column payload. MISMATCH when a column's metadata range holds
    a nonzero value against the served all-zero default; MATCH when the
    metadata range is exactly zero. The joined 2024-25 row-level shift needs
    decoded row payloads against the served holdout corpus, which is out of
    this metadata-only scope, so it is always reported INSUFFICIENT."""
    import pyarrow.parquet as pq  # local import: keep module import light

    pf = pq.ParquetFile(parquet_path)
    meta = pf.metadata
    col_index = {name: i for i, name in enumerate(meta.schema.names)}
    columns: dict = {}
    for col in _REST_TRAVEL_COLUMNS:
        if col not in col_index:
            columns[col] = {"verdict": "INSUFFICIENT", "reason": "column absent from schema"}
            continue
        idx = col_index[col]
        col_min: Optional[float] = None
        col_max: Optional[float] = None
        have_stats = True
        for rg in range(meta.num_row_groups):
            stats = meta.row_group(rg).column(idx).statistics
            if stats is None or not stats.has_min_max:
                have_stats = False
                break
            rmin, rmax = float(stats.min), float(stats.max)
            if not (math.isfinite(rmin) and math.isfinite(rmax)):
                have_stats = False
                break
            col_min = rmin if col_min is None else min(col_min, rmin)
            col_max = rmax if col_max is None else max(col_max, rmax)
        if not have_stats:
            columns[col] = {"verdict": "INSUFFICIENT", "reason": "no usable row-group statistics"}
            continue
        is_zero = (col_min == _SERVED_DEFAULT and col_max == _SERVED_DEFAULT)
        columns[col] = {"min": col_min, "max": col_max, "verdict": "MATCH" if is_zero else "MISMATCH"}
    joined = {
        "status": "INSUFFICIENT",
        "reason": ("%d row group(s) / metadata-only scope; a joined 2024-25 row-level shift "
                   "needs decoded row payloads against the served holdout corpus, which this "
                   "metadata-only probe never reads" % meta.num_row_groups),
    }
    return {
        "parquet_path": parquet_path, "num_row_groups": meta.num_row_groups,
        "columns": columns, "joined_2024_25_row_level_shift": joined,
    }


# ---- stitch_router_binding_proof ----

def _callee_name(call: ast.Call) -> Optional[str]:
    fn = call.func
    return fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)


def _find_funcdef(tree: ast.AST, func_name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None


def _select_call(tree: ast.AST, caller_name: str, func_name: str):
    """The func_name call(s) strictly inside caller_name's body. Returns
    (call_or_None, candidate_count) -- exactly one candidate selects it;
    zero or more than one is the caller's job to refuse (duplicate_call_sites),
    never a first-match guess sensitive to source order."""
    caller = _find_funcdef(tree, caller_name)
    if caller is None:
        return None, 0
    candidates = [n for n in ast.walk(caller)
                  if isinstance(n, ast.Call) and _callee_name(n) == func_name]
    return (candidates[0] if len(candidates) == 1 else None), len(candidates)


def _arg_text(node: ast.AST) -> str:
    return node.id if isinstance(node, ast.Name) else ast.dump(node)


def _build_stub(funcdef) -> object:
    """A loader-safe stub function object compiled from the parsed def node's
    line and argument list ONLY (body replaced with `pass`) -- never imports
    or executes a byte of the source module it came from. `from __future__
    import annotations` defers annotation evaluation so a type hint naming an
    unimported symbol (e.g. Optional) can't raise NameError at def time."""
    args_src = ast.unparse(funcdef.args)
    stub_src = "from __future__ import annotations\ndef %s(%s):\n    pass\n" % (funcdef.name, args_src)
    ns: dict = {}
    exec(compile(stub_src, "<loader-safe-stub:%s>" % funcdef.name, "exec"), ns)  # noqa: S102
    return ns[funcdef.name]


def stitch_router_binding_proof(router_path: str, callee_path: str,
                                 func_name: str = "predict_props",
                                 caller_name: str = "get_player_props") -> dict:
    """Selects the single func_name call inside caller_name (AST; refuses
    duplicate_call_sites on zero or >1 candidates) and gets the callee's
    parameters through inspect.signature applied to a loader-safe stub built
    from the parsed def node -- never an import of api.stitch_router or
    src.prediction (both can read private caches / hit the network on
    import). Cross-checks the stub route against the plain AST parameter
    list and reports whether they agree, and never fabricates a
    feature-value difference."""
    router_src = Path(router_path).read_text(encoding="utf-8", errors="replace")
    callee_src = Path(callee_path).read_text(encoding="utf-8", errors="replace")
    call, n_candidates = _select_call(ast.parse(router_src), caller_name, func_name)
    funcdef = _find_funcdef(ast.parse(callee_src), func_name)
    base = {"router_path": router_path, "callee_path": callee_path,
            "caller_name": caller_name, "func_name": func_name}
    if funcdef is None:
        return {**base, "refused": "definition_not_found", "candidate_count": n_candidates}
    if call is None:
        return {**base, "refused": "duplicate_call_sites", "candidate_count": n_candidates}

    ast_params = [p.arg for p in funcdef.args.args]
    try:
        stub_params = list(inspect.signature(_build_stub(funcdef)).parameters.keys())
        stub_error = None
    except Exception as exc:  # counted, never crashes the probe
        stub_params = None
        stub_error = "%s: %s" % (type(exc).__name__, exc)
    params_agree = stub_error is None and stub_params == ast_params

    call_args = [_arg_text(a) for a in call.args]
    bindings = [{"position": i, "call_arg": call_args[i], "param": ast_params[i]}
                for i in range(min(len(call_args), len(ast_params)))]
    mismatch = any(b["call_arg"] != b["param"] for b in bindings)
    return {
        **base, "call_line": call.lineno, "callee_line": funcdef.lineno,
        "call_positional_args": call_args,
        "ast_params": ast_params, "stub_params": stub_params, "stub_error": stub_error,
        "params_agree": params_agree,
        "bindings": bindings, "mismatch": mismatch,
        "numerical_impact": ("NOT VERIFIED -- not measurable without executing a production "
                              "loader; the opponent-defence factors may return identical "
                              "neutral values across differing inputs in that slot"),
    }


# ---- CLI / reproduction ----

def _sha256_raw(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _default_paths(repo_root: Path) -> dict:
    return {
        "player_props": str(repo_root / "src/prediction/player_props.py"),
        "prop_pergame": str(repo_root / "src/prediction/prop_pergame.py"),
        "stitch_router": str(repo_root / "api/stitch_router.py"),
        "rest_travel_parquet": str(repo_root / "data/rest_travel.parquet"),
    }


def run_all(repo_root: Optional[Path] = None) -> dict:
    root = repo_root or Path(__file__).resolve().parents[3]
    paths = _default_paths(root)
    result = {
        "case1_trainer_synthetic": classify_trainer_synthetic(paths["player_props"], 2690, 2731),
        "case2_pergame_real": classify_trainer_synthetic(paths["prop_pergame"], 5266, 5341),
        "binding_proof": stitch_router_binding_proof(paths["stitch_router"], paths["player_props"]),
    }
    try:
        result["rest_travel"] = rest_travel_statements(paths["rest_travel_parquet"])
        result["rest_travel_sha256"] = _sha256_raw(Path(paths["rest_travel_parquet"]))
    except FileNotFoundError as exc:
        reason = "data/rest_travel.parquet not present in this worktree: %s" % str(exc).strip()
        result["rest_travel"] = {"status": "INSUFFICIENT", "reason": reason}
        result["rest_travel_sha256"] = {"status": "INSUFFICIENT", "reason": reason}
    return result


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    print(json.dumps(run_all(), indent=1, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
