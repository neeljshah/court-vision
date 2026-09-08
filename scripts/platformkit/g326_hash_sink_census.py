"""G326 hash-sink census -- an AST walk over every .py in scripts/platformkit/**, replacing the
same-line `grep` denominator the G326 verifier rejected (a grep only sees a sink whose read and
hash share ONE line, so it drops every streamed/multiline one). A row per `hashlib.<algo>()`
call, per `.update()` on one, and per call to an imported hash helper; each classified EXACTLY
once by data flow (FILE_STREAM > FILE_WHOLE > TAINTED > MEMORY), then TEXT/BINARY and
COMMITTED/RECORD_ONLY. TEXT + COMMITTED is a DEFECT: `core.autocrlf` makes the digest a function
of the CHECKOUT. Sealed in `g326_prereg_supplement_2026-09-07.md`; UNKNOWN is always reported.
"""
from __future__ import annotations

import ast
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TREE = ROOT / "scripts" / "platformkit"
OUT_CSV = ROOT / "docs/evidence/tracking/g326_artifact/hash_sinks.csv"
ALGOS = {"sha256", "sha1", "md5", "sha224", "sha384", "sha512", "blake2b", "blake2s", "new"}
TEXT_EXT = (".md", ".csv", ".json", ".txt", ".yaml", ".yml", ".py")
BIN_EXT = (".mp4", ".png", ".jpg", ".pt", ".pth", ".parquet", ".npy", ".npz", ".gz", ".zip", ".bin")
PARSE_CALLS = {"loads", "load", "read_text", "read_csv", "safe_load", "read_json"}
READS = ("read_bytes", "'read'", "'open'", "read_text")
STREAM, WHOLE, TAINT, MEM = "FILE_STREAM", "FILE_WHOLE", "TAINTED", "MEMORY"
RANK = {MEM: 0, TAINT: 1, WHOLE: 2, STREAM: 3}
HEADER = ["file", "line", "api", "input_class", "text_or_binary", "compared", "verdict"]
HELPERS: dict = {}                      # module dotted path -> (helper names, newline-safe subset)


def dotted(node: ast.AST) -> str:
    """`a.b.c` for an Attribute/Name chain, else ''."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join(reversed(parts + [node.id])) if isinstance(node, ast.Name) else ""


def scope_nodes(scope: ast.AST):
    """Every node under `scope` that is not inside a nested function/class."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def names_in(node: ast.AST) -> list:      # every Name in a target, tuple unpacking included
    return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


def bindings(scope: ast.AST) -> dict:
    """name -> [(kind, value_node)]; kind 'for' means bound to an ELEMENT of the value."""
    out: dict = {}
    for node in scope_nodes(scope):
        pairs = []                                       # (kind, bound names, value node)
        if isinstance(node, ast.Assign):
            pairs = [("val", [n for t in node.targets for n in names_in(t)], node.value)]
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name) and node.value:
            pairs = [("val", [node.target.id], node.value)]
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            pairs = [("for", names_in(node.target), node.iter)]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            pairs = [("val", names_in(i.optional_vars), i.context_expr) for i in node.items if i.optional_vars]
        for kind, names, value in pairs:
            for name in names:
                out.setdefault(name, []).append((kind, value))
    return out


def helper_names(tree: ast.AST) -> tuple:
    """(helpers defined here, the newline-safe subset). A helper reads a file AND returns the
    digest; requiring the return keeps generic names (`main`, `run`) out of the set."""
    plain, safe = set(), set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        body = ast.dump(fn)
        if "hexdigest" not in body or not any(k in body for k in READS):
            continue
        binds = bindings(fn)
        rets = [n.value for n in scope_nodes(fn) if isinstance(n, ast.Return) and n.value]
        rets += [v for r in list(rets) if isinstance(r, ast.Name) for _, v in binds.get(r.id, [])]
        if any("hexdigest" in ast.dump(r) for r in rets):
            plain.add(fn.name)
            safe |= {fn.name} if "\\r\\n" in body or "read_text" in body else set()
    return plain, safe


def mod_path(path: Path) -> str:          # `scripts.platformkit.x.y` for a file inside the repo
    return path.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")


class Scan:
    """Classify every hash sink in one parsed file."""

    def __init__(self, path: Path, tree: ast.AST) -> None:
        self.rel, self.tree, self.local = path.relative_to(ROOT).as_posix(), tree, {}
        self.mod = bindings(tree)
        self.parents = {id(c): p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        self.funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.taint, self.safe = (set(s) for s in HELPERS.get(mod_path(path), (set(), set())))
        self.hash_names, self.alias, me = {"hashlib"}, {}, mod_path(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in [a for a in node.names if a.name == "hashlib" or a.name in HELPERS]:
                    self.alias[a.asname or a.name] = a.name
                    self.hash_names |= {a.asname or a.name} if a.name == "hashlib" else set()
            elif isinstance(node, ast.ImportFrom):
                base = (".".join(me.split(".")[:-node.level] + ([node.module] if node.module else []))
                        if node.level else (node.module or ""))
                plain, safe = HELPERS.get(base, (set(), set()))
                for a in node.names:
                    local = a.asname or a.name
                    self.hash_names |= {local} if base == "hashlib" else set()
                    self.taint |= {local} if a.name in plain else set()
                    self.safe |= {local} if a.name in safe else set()
                    self.alias.update({local: base + "." + a.name} if base + "." + a.name in HELPERS else {})

    def lookup(self, name: str) -> list:
        return self.local.get(name) or self.mod.get(name) or []

    def tainted(self, name: str) -> tuple:
        """(is a hash-helper call, is its digest newline-safe) for a dotted call name."""
        head, _, tail = name.rpartition(".")
        if not head:
            return tail in self.taint, tail in self.safe
        plain, safe = HELPERS.get(self.alias.get(head, ""), (set(), set()))
        return tail in plain, tail in safe

    def is_ctor(self, node: ast.AST) -> bool:
        """True for a hashlib constructor call, however hashlib was imported."""
        if not isinstance(node, ast.Call):
            return False
        head, _, tail = dotted(node.func).rpartition(".")
        return (head in self.hash_names and tail in ALGOS) or (not head and tail in self.hash_names - {"hashlib"})

    def flow(self, node, seen=frozenset(), loop=False) -> tuple:
        """(data-flow class, newline-safe?) of the expression feeding a sink."""
        if node is None or id(node) in seen or len(seen) > 40:
            return MEM, False
        seen = seen | {id(node)}
        top = lambda kids: max(kids, key=lambda c: RANK[c[0]], default=(MEM, False))
        if isinstance(node, ast.Name):
            return top([self.flow(v, seen, loop or k == "for") for k, v in self.lookup(node.id)])
        if isinstance(node, ast.Lambda):
            return self.flow(node.body, seen, loop)
        if isinstance(node, ast.Attribute):
            return self.flow(node.value, seen, loop)
        if isinstance(node, (ast.BinOp, ast.BoolOp, ast.IfExp, ast.JoinedStr, ast.FormattedValue)):
            return top([self.flow(k, seen, loop) for k in ast.iter_child_nodes(node) if isinstance(k, ast.expr)])
        if not isinstance(node, ast.Call):
            return MEM, False
        name = dotted(node.func)
        tail = name.rpartition(".")[2]
        recv = node.func.value if isinstance(node.func, ast.Attribute) else None
        chunked = STREAM if loop else WHOLE
        if tail in ("read_bytes", "read_text"):
            return chunked, tail == "read_text"          # text mode translates CRLF on read
        if tail == "read":
            return (STREAM if (node.args or loop) else WHOLE), self.flow(recv, seen, loop)[1]
        if tail == "open":                # mode is args[1] for builtin open, args[0] for Path.open
            const = [a.value for a in node.args if isinstance(a, ast.Constant)] + \
                    [k.value.value for k in node.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)]
            modes = [v for v in const if isinstance(v, str) and len(v) <= 4 and set(v) <= set("rwxabt+")]
            return chunked, not any("b" in m for m in modes)
        if tail == "iter":
            return top([self.flow(a, seen, True) for a in node.args])
        if tail == "replace" and any(isinstance(a, ast.Constant) and a.value in (b"\r\n", "\r\n") for a in node.args):
            return self.flow(recv, seen, loop)[0], True
        hit, safe = self.tainted(name)
        return (TAINT, safe) if hit and not self.is_ctor(node) else top(
            [self.flow(a, seen, loop) for a in node.args])

    def exts(self, node, seen=frozenset()) -> set:   # filename suffixes reachable from `node`
        found: set = set()
        if node is None or id(node) in seen or len(seen) > 60:
            return found
        seen = seen | {id(node)}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                found |= {e for e in TEXT_EXT + BIN_EXT if sub.value.lower().endswith(e)}
            elif isinstance(sub, ast.Name):
                for _, val in self.lookup(sub.id):
                    found |= self.exts(val, seen)
        return found

    def committed(self, node, seen=frozenset()) -> bool:
        """True if this operand's value lives in the repo (hex literal or parsed committed data)."""
        if node is None or id(node) in seen or len(seen) > 40:
            return False
        seen = seen | {id(node)}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                text = sub.value.strip()
                if len(text) in (32, 40, 64) and not text.strip("0123456789abcdefABCDEF"):
                    return True
            elif isinstance(sub, ast.Call):
                tail = dotted(sub.func).rpartition(".")[2]
                if tail in PARSE_CALLS or (tail in self.funcs and self.committed(self.funcs[tail], seen)):
                    return True                    # one hop into a local helper returning repo data
            elif isinstance(sub, ast.Name) and any(self.committed(v, seen) for _, v in self.lookup(sub.id)):
                return True
        return False

    def compared(self, sink: ast.AST, scope: ast.AST) -> str:
        """COMMITTED if the digest is checked against a repo value, else RECORD_ONLY. One
        store-then-check hop (`d = sha(p)` ... `assert d == <seal>`) does not hide a seal."""
        node, stored = sink, None
        for _ in range(30):
            parent = self.parents.get(id(node))
            if isinstance(parent, ast.Compare):
                rest = [o for o in [parent.left] + list(parent.comparators) if not any(s is node for s in ast.walk(o))]
                return "COMMITTED" if any(self.committed(o) for o in rest) else "RECORD_ONLY"
            if parent is None or (isinstance(parent, ast.Assign) and len(parent.targets) == 1
                                  and isinstance(parent.targets[0], ast.Name)):
                stored = parent.targets[0].id if parent is not None else None
                break
            node = parent
        for node in scope_nodes(scope) if stored else []:
            ops = [node.left] + list(node.comparators) if isinstance(node, ast.Compare) else []
            uses = [o for o in ops if stored in names_in(o)]
            if uses and any(self.committed(o) for o in ops if o not in uses):
                return "COMMITTED"
        return "RECORD_ONLY"

    def row(self, node: ast.Call, api: str, data, scope: ast.AST) -> list:
        """One classified census row."""
        cls, safe = self.flow(data)
        if cls == MEM:
            return [self.rel, node.lineno, api, MEM, "-", "-", "FINE_MEMORY"]
        exts = self.exts(data)
        kind = "TEXT" if exts & set(TEXT_EXT) else ("BINARY" if exts & set(BIN_EXT) else "UNKNOWN")
        cmp_ = self.compared(node, scope)
        verdict = ("ALREADY_LF" if safe else "FINE_BINARY" if kind == "BINARY"
                   else "FINE_RECORD_ONLY" if cmp_ == "RECORD_ONLY"
                   else "DEFECT" if kind == "TEXT" else "REVIEW_UNKNOWN")
        return [self.rel, node.lineno, api, cls, kind, cmp_, verdict]

    def rows(self) -> list:
        """A row per hashlib construction, per .update() on one, and per hash-helper call."""
        out = []
        fns = [n for n in ast.walk(self.tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for scope in [self.tree] + fns:
            self.local = {} if scope is self.tree else bindings(scope)
            here = getattr(scope, "name", None)
            ctors = {t.id for n in scope_nodes(scope) if isinstance(n, ast.Assign)
                     for t in n.targets if isinstance(t, ast.Name) and self.is_ctor(n.value)}
            for node in scope_nodes(scope):
                if not isinstance(node, ast.Call):
                    continue
                name = dotted(node.func)
                if isinstance(node.func, ast.Attribute) and node.func.attr == "update" \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id in ctors:
                    out.append(self.row(node, "update", node.args[0] if node.args else None, scope))
                elif self.is_ctor(node):
                    args = node.args[1:] if name.rpartition(".")[2] == "new" else node.args
                    out.append(self.row(node, name, args[0], scope) if args else
                               [self.rel, node.lineno, name + ":ctor", MEM, "-", "-", "FINE_CTOR"])
                elif self.tainted(name)[0] and name.rpartition(".")[2] != here:
                    out.append(self.row(node, name, node, scope))     # the call IS the tainted flow
        return out          # one row per call node; several sinks may legitimately share a line


def census() -> list:
    """Two passes over the tree: discover hash helpers per module, then classify every sink."""
    files, rows = sorted(TREE.rglob("*.py")), []
    for path in files:
        try:
            HELPERS[mod_path(path)] = helper_names(ast.parse(path.read_bytes()))
        except SyntaxError:
            continue
    for path in files:
        try:
            rows.extend(list(r) for r in Scan(path, ast.parse(path.read_bytes())).rows())
        except SyntaxError:
            rows.append([path.relative_to(ROOT).as_posix(), 0, "-", "PARSE_ERROR", "-", "-", "REVIEW_UNKNOWN"])
    return sorted(rows, key=lambda r: (r[0], r[1], r[2]))


def main() -> None:
    """Write the census CSV and print counts by class and verdict."""
    rows = census()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="ascii") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)
    entry = [r for r in rows if r[6] != "FINE_CTOR" and r[3] != "PARSE_ERROR"]
    print("rows %d  data-entry sinks %d  empty ctors %d  parse errors %d  file-reading %d" % (
        len(rows), len(entry), sum(r[6] == "FINE_CTOR" for r in rows),
        sum(r[3] == "PARSE_ERROR" for r in rows), sum(r[3] != MEM for r in entry)), flush=True)
    for label, cnt in (("input_class", Counter(r[3] for r in entry)), ("verdict", Counter(r[6] for r in entry))):
        print(label + ": " + "  ".join("%s=%d" % kv for kv in sorted(cnt.items())))
    for r in [r for r in rows if r[6] in ("DEFECT", "REVIEW_UNKNOWN")]:
        print("%s %s:%s %s %s %s %s" % (r[6], r[0], r[1], r[2], r[3], r[4], r[5]))


if __name__ == "__main__":
    sys.exit(main())
