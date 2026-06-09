"""CONTENT-HASH IDS -- structural dedup is the no-redundancy guarantee (MASTER_SYSTEM_BUILD section 3).

signal_id = "sig_" + blake2b(canon, digest_size=12).hexdigest(), where canon is the JSON dump
(sort_keys, compact) of EXACTLY {grain, entity_scope, domain_tags, source, formula_ast,
transform_chain, asof_fn_name, causal_sign}. The hash covers the DEFINITION, never the data
(data freshness is a separate input_hash, cache/cas.py).

formula_ast is the PARSED + normalized expression so that `a+b` == `b+a` and `a*b*c` == `c*b*a`,
whitespace stripped, float literals quantized to 6 significant figures. register() is therefore pure:
the same definition always yields the same id, so re-registering is a no-op (dedup is structural).

  from registry.ids import signal_id
  sid = signal_id(dict(grain="possession", entity_scope="team", domain_tags=["transition"],
                       source="pbp", formula_ast="off_to_share*ppp_off_to", transform_chain=["rate"],
                       asof_fn_name="asof_team_game", causal_sign=1))
"""
from __future__ import annotations
import ast
import hashlib
import json
import math
import re
from typing import Any

# the EXACT fields that define a signal's identity (order-independent; sorted in canon)
_SIGNAL_KEYS = ("grain", "entity_scope", "domain_tags", "source", "formula_ast",
                "transform_chain", "asof_fn_name", "causal_sign")
_MODEL_KEYS = ("domain_tag", "entity_scope", "signal_id_set", "method")
# an engine's IDENTITY is its name + methodology; consumes_models/owns_nodes are MUTABLE wiring state
# (they grow as validated domain models are routed in), so they are NOT part of the content id.
_ENGINE_KEYS = ("name", "method")

_COMMUTATIVE = (ast.Add, ast.Mult, ast.BitAnd, ast.BitOr, ast.BitXor)


def _quantize_float(x: float, sig: int = 6) -> float:
    """Quantize a float to `sig` significant figures so 0.1000001 and 0.1 hash identically."""
    if x == 0 or not math.isfinite(x):
        return 0.0 if x == 0 else x
    d = sig - int(math.floor(math.log10(abs(x)))) - 1
    return round(x, d)


class _Normalizer(ast.NodeTransformer):
    """Sort operands of commutative ops + quantize float constants -> canonical AST."""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, float):
            return ast.copy_location(ast.Constant(value=_quantize_float(node.value)), node)
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, _COMMUTATIVE):
            operands = _flatten(node, type(node.op))
            operands = sorted(operands, key=lambda n: ast.dump(n))
            return _rebuild(operands, node.op)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        node.values = sorted(node.values, key=lambda n: ast.dump(n))
        return node


def _flatten(node: ast.BinOp, op_type) -> list:
    """Flatten a left-assoc chain of one commutative op (a+b+c -> [a,b,c])."""
    out = []
    for side in (node.left, node.right):
        if isinstance(side, ast.BinOp) and isinstance(side.op, op_type):
            out.extend(_flatten(side, op_type))
        else:
            out.append(side)
    return out


def _rebuild(operands: list, op: ast.operator) -> ast.AST:
    """Rebuild a balanced (left-fold) BinOp chain from sorted operands."""
    cur = operands[0]
    for nxt in operands[1:]:
        cur = ast.BinOp(left=cur, op=op, right=nxt)
    return cur


def normalize_formula(expr: Any) -> str:
    """Canonical form of a formula. Parseable Python expr -> normalized AST dump; otherwise a
    whitespace-collapsed, lower-cased string (descriptive formulas still hash deterministically)."""
    if expr is None:
        return ""
    s = str(expr).strip()
    if not s:
        return ""
    try:
        tree = ast.parse(s, mode="eval")
        tree = _Normalizer().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.dump(tree.body, annotate_fields=False)
    except (SyntaxError, ValueError, RecursionError):
        return re.sub(r"\s+", " ", s.lower()).strip()


def _canon(defn: dict, keys: tuple) -> str:
    """Stable JSON of exactly `keys`. Lists are sorted (set semantics); formula_ast is normalized."""
    out = {}
    for k in keys:
        v = defn.get(k)
        if k == "formula_ast":
            v = normalize_formula(v)
        elif isinstance(v, (list, tuple, set)):
            v = sorted(str(x) for x in v)
        elif isinstance(v, float):
            v = _quantize_float(v)
        out[k] = v
    return json.dumps(out, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(defn: dict, keys: tuple, prefix: str, digest_size: int = 12) -> str:
    canon = _canon(defn, keys)
    return f"{prefix}_{hashlib.blake2b(canon.encode('utf-8'), digest_size=digest_size).hexdigest()}"


def signal_id(defn: dict) -> str:
    return content_hash(defn, _SIGNAL_KEYS, "sig")


def model_id(defn: dict) -> str:
    return content_hash(defn, _MODEL_KEYS, "mdl")


def engine_id(defn: dict) -> str:
    return content_hash(defn, _ENGINE_KEYS, "eng")


def family_key(defn: dict) -> str:
    """Anti-re-roll key (MASTER_SYSTEM_BUILD 4A): grain+entity+transform-FAMILY, IGNORING tuning
    constants. Two signals in the same family (same grain/entity/transform shape, different window or
    threshold) share a family_key so re-rolling a rejected family until it passes-by-chance is blocked."""
    fam = {
        "grain": defn.get("grain"),
        "entity_scope": defn.get("entity_scope"),
        "domain_tags": sorted(str(x) for x in (defn.get("domain_tags") or [])),
        # transform family = the chain shape minus numeric params (window sizes, thresholds)
        "transform_family": sorted(re.sub(r"[\d.]+", "#", str(t)) for t in (defn.get("transform_chain") or [])),
        "source": defn.get("source"),
    }
    canon = json.dumps(fam, sort_keys=True, separators=(",", ":"), default=str)
    return f"fam_{hashlib.blake2b(canon.encode('utf-8'), digest_size=8).hexdigest()}"


if __name__ == "__main__":
    # self-test: commutativity, float-quantize, dedup, family grouping
    a = dict(grain="possession", entity_scope="team", domain_tags=["transition", "pace"],
             source="pbp", formula_ast="off_to_share*ppp + 0.1000001", transform_chain=["rate"],
             asof_fn_name="asof_team", causal_sign=1)
    b = dict(a); b["formula_ast"] = "0.1*ppp*off_to_share/ppp*ppp + off_to_share*ppp"  # not equal -> diff id
    c = dict(a); c["formula_ast"] = "ppp*off_to_share + 0.1"          # commutative-equal to a
    c["domain_tags"] = ["pace", "transition"]                         # order-flipped -> same id
    assert signal_id(a) == signal_id(c), "commutativity/order/quantize must dedup"
    assert signal_id(a) != signal_id(b), "different formula must differ"
    f1 = dict(a, formula_ast="roll(x, 5)", transform_chain=["roll_5"])
    f2 = dict(a, formula_ast="roll(x, 10)", transform_chain=["roll_10"])
    assert family_key(f1) == family_key(f2), "same transform family, different window -> same family_key"
    assert signal_id(f1) != signal_id(f2), "but distinct ids"
    print("ids.py self-test PASS")
    print("  signal_id(a) =", signal_id(a))
    print("  family_key   =", family_key(f1))
