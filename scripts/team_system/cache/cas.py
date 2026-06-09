"""
Content-Addressed Cache + Dependency DAG — MASTER_SYSTEM_BUILD section 6.1.
"Recompute only what changed": a node is recomputed iff its definition (node_id)
OR any declared upstream input changed bytes (input_hash).

Public API:
    input_hash(inputs, upstream_keys=None) -> str
    cache_key(node_id, ih, entity="") -> str
    put(node_id, ih, df, entity="", builder="", meta_extra=None) -> str (key)
    get(node_id, ih, entity="") -> pd.DataFrame | None
    has(node_id, ih, entity="") -> bool
    register_node(node_id, builder_fn, inputs, output, entity="", upstream_node_ids=None)
    materialize(node_id, entity="") -> pd.DataFrame
    topo_order(node_ids) -> list[str]
    stale_count() -> dict  # ACCEPTANCE: stale_pct < 5% after one new game
    undeclared_input_lint(node_id, observed_paths) -> list[str]
    gc(cap_gb=20.0) -> dict
"""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
import pandas as pd

# ---------------------------------------------------------------------------
# Root / CAS_ROOT — reassignable for self-test isolation
# ---------------------------------------------------------------------------
# cas.py at <REPO>/scripts/team_system/cache/cas.py
# dirname x4: cache -> team_system -> scripts -> REPO
_THIS = os.path.abspath(__file__)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_THIS))))
CAS_ROOT: str = os.path.join(ROOT, "data", "cache", "cas")


# ---------------------------------------------------------------------------
# 1. PROVENANCE
# ---------------------------------------------------------------------------
def input_hash(inputs: list[str], upstream_keys: list[str] | None = None) -> str:
    """
    Blake2b(digest_size=12) over SORTED (abspath, mtime_ns, size, upstream_key).
    Missing file -> (path, -1, -1, "").  upstream_keys zip 1:1 with inputs then
    continue as ("", -1, -1, key) entries.  Separate from the definition hash
    (node_id), which the caller supplies.
    """
    uk = upstream_keys or []
    entries: list[tuple[str, int, int, str]] = []
    for i, p in enumerate(inputs):
        ap = os.path.abspath(p)
        ukey = uk[i] if i < len(uk) else ""
        try:
            st = os.stat(ap)
            entries.append((ap, st.st_mtime_ns, st.st_size, ukey))
        except OSError:
            entries.append((ap, -1, -1, ukey))
    for ukey in uk[len(inputs):]:
        entries.append(("", -1, -1, ukey))
    entries.sort()
    h = hashlib.blake2b(digest_size=12)
    for ap, mt, sz, ukey in entries:
        h.update(f"{ap}\x00{mt}\x00{sz}\x00{ukey}\n".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 2. CACHE KEY + STORE
# ---------------------------------------------------------------------------
def cache_key(node_id: str, ih: str, entity: str = "") -> str:
    """Blake2b(digest_size=16) of '{node_id}:{entity}:{ih}'.  Per-entity so one
    player's new game invalidates that player's signals only, not the league's."""
    return hashlib.blake2b(
        f"{node_id}:{entity}:{ih}".encode(), digest_size=16
    ).hexdigest()


def _pp(key: str) -> str:
    return os.path.join(CAS_ROOT, key[:2], f"{key}.parquet")

def _mp(key: str) -> str:
    return os.path.join(CAS_ROOT, key[:2], f"{key}.meta.json")

def _atomic_bytes(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def put(node_id: str, ih: str, df: pd.DataFrame,
        entity: str = "", builder: str = "", meta_extra: dict | None = None) -> str:
    """Atomic write of parquet + meta sidecar.  Returns cache key.
    Files: data/cache/cas/<key[:2]>/<key>.parquet + <key>.meta.json"""
    key = cache_key(node_id, ih, entity)
    pp, mp = _pp(key), _mp(key)
    os.makedirs(os.path.dirname(pp), exist_ok=True)
    tmp = pp + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, pp)
    meta: dict[str, Any] = {
        "node_id": node_id, "entity": entity, "input_hash": ih,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "builder": builder, "status": "active", "referenced_by": [],
    }
    if meta_extra:
        meta.update(meta_extra)
    _atomic_bytes(mp, json.dumps(meta, indent=2, ensure_ascii=True).encode())
    return key


def get(node_id: str, ih: str, entity: str = "") -> Optional[pd.DataFrame]:
    """Cache hit -> DataFrame; miss -> None."""
    p = _pp(cache_key(node_id, ih, entity))
    return pd.read_parquet(p) if os.path.exists(p) else None


def has(node_id: str, ih: str, entity: str = "") -> bool:
    """True iff artifact exists in CAS."""
    return os.path.exists(_pp(cache_key(node_id, ih, entity)))


# ---------------------------------------------------------------------------
# 3. DAG
# ---------------------------------------------------------------------------
@dataclass
class _Node:
    node_id: str
    builder_fn: Callable[[], pd.DataFrame]
    inputs: list[str]
    output: str
    entity: str = ""
    upstream_node_ids: list[str] = field(default_factory=list)

_REGISTRY: dict[str, _Node] = {}
_MAT_KEY: dict[str, str] = {}   # node_id -> last materialised cache_key


def register_node(node_id: str, builder_fn: Callable[[], pd.DataFrame],
                  inputs: list[str], output: str, entity: str = "",
                  upstream_node_ids: list[str] | None = None) -> None:
    """Register a builder node.  builder_fn() -> DataFrame.  inputs = file paths
    this node reads; upstream_node_ids = other nodes it depends on (their
    materialised cache keys fold into this node's input_hash)."""
    _REGISTRY[node_id] = _Node(
        node_id=node_id, builder_fn=builder_fn, inputs=inputs, output=output,
        entity=entity, upstream_node_ids=upstream_node_ids or [],
    )


def topo_order(node_ids: list[str]) -> list[str]:
    """Topological sort (Kahn).  Raises ValueError on cycle."""
    ids = set(node_ids)
    deg = {n: 0 for n in node_ids}
    ch: dict[str, list[str]] = {n: [] for n in node_ids}
    for nid in node_ids:
        nd = _REGISTRY.get(nid)
        if nd is None:
            continue
        for up in nd.upstream_node_ids:
            if up in ids:
                deg[nid] += 1
                ch[up].append(nid)
    q = [n for n, d in deg.items() if d == 0]
    out: list[str] = []
    while q:
        cur = q.pop(0)
        out.append(cur)
        for c in ch.get(cur, []):
            deg[c] -= 1
            if deg[c] == 0:
                q.append(c)
    if len(out) != len(node_ids):
        raise ValueError(f"Cycle in DAG: {set(node_ids)-set(out)}")
    return out


def _cur_ih(node_id: str) -> str:
    nd = _REGISTRY[node_id]
    uk = [_MAT_KEY.get(u, "") for u in nd.upstream_node_ids]
    return input_hash(nd.inputs, uk or None)


def materialize(node_id: str, entity: str = "") -> pd.DataFrame:
    """Lazy materialise: recurse upstreams -> check cache -> compute+store if miss.
    LAZY: only runs when called.  Cache hit = no recompute."""
    nd = _REGISTRY[node_id]
    for up in nd.upstream_node_ids:
        materialize(up, entity=_REGISTRY[up].entity)
    ih = _cur_ih(node_id)
    ent = entity or nd.entity
    _MAT_KEY[node_id] = cache_key(node_id, ih, ent)
    cached = get(node_id, ih, ent)
    if cached is not None:
        return cached
    df = nd.builder_fn()
    put(node_id, ih, df, entity=ent, builder=node_id)
    return df


def stale_count() -> dict:
    """For every registered node: is current input_hash in cache (fresh) or not (stale)?
    Returns {total, stale, fresh, stale_pct}.
    ACCEPTANCE TARGET: after ONE new game, stale_pct < 5% (one entity's nodes, not league's).
    stale_pct == 1.0 means the cache is broken."""
    total = fresh = stale = 0
    for nid, nd in _REGISTRY.items():
        total += 1
        uk = [_MAT_KEY.get(u, "") for u in nd.upstream_node_ids]
        ih = input_hash(nd.inputs, uk or None)
        if has(nid, ih, nd.entity):
            fresh += 1
        else:
            stale += 1
    return {"total": total, "stale": stale, "fresh": fresh,
            "stale_pct": round(stale / total, 4) if total else 0.0}


def undeclared_input_lint(node_id: str, observed_paths: list[str]) -> list[str]:
    """Returns observed paths NOT in the node's declared inputs.
    A builder reading an undeclared input is a cache-correctness bug: the
    input_hash won't capture its changes -> stale data passes as a cache hit.
    Usage: call after builder_fn in a debug harness; add returned paths to inputs."""
    declared = {os.path.abspath(p) for p in _REGISTRY[node_id].inputs}
    return [p for p in observed_paths if os.path.abspath(p) not in declared]


# ---------------------------------------------------------------------------
# 4. LRU GC
# ---------------------------------------------------------------------------
def gc(cap_gb: float = 20.0) -> dict:
    """Evict until total CAS size <= cap_gb.
    Policy: (1) evict 'rejected' immediately regardless of LRU,
            (2) LRU-evict (oldest mtime) remaining until under cap,
            (3) NEVER evict 'validated'/'caveat' or non-empty referenced_by.
    Returns {evicted, freed_gb, kept}."""
    cap_bytes = int(cap_gb * 1024 ** 3)
    if not os.path.isdir(CAS_ROOT):
        return {"evicted": 0, "freed_gb": 0.0, "kept": 0}

    arts: list[tuple[float, str, str]] = []  # (mtime, ppath, mpath)
    for shard in os.listdir(CAS_ROOT):
        sd = os.path.join(CAS_ROOT, shard)
        if not os.path.isdir(sd):
            continue
        for fn in os.listdir(sd):
            if not fn.endswith(".parquet"):
                continue
            pp = os.path.join(sd, fn)
            key = fn[:-len(".parquet")]
            mp = os.path.join(sd, key + ".meta.json")
            try:
                mtime = os.path.getmtime(pp)
            except OSError:
                mtime = 0.0
            arts.append((mtime, pp, mp))

    def _stat(mp: str) -> tuple[str, list]:
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            return m.get("status", "active"), m.get("referenced_by", [])
        except (OSError, json.JSONDecodeError):
            return "active", []

    def _rm(pp: str, mp: str) -> int:
        freed = 0
        for p in (pp, mp):
            try:
                freed += os.path.getsize(p)
                os.remove(p)
            except OSError:
                pass
        return freed

    evicted = freed = 0
    # Pass 1: rejected first
    remaining = []
    for mtime, pp, mp in arts:
        st, rb = _stat(mp)
        if st == "rejected" and not rb:
            freed += _rm(pp, mp)
            evicted += 1
        else:
            remaining.append((mtime, pp, mp))

    total = sum(
        os.path.getsize(p) for _, pp, mp in remaining
        for p in (pp, mp) if os.path.exists(p)
    )
    if total <= cap_bytes:
        return {"evicted": evicted, "freed_gb": round(freed/1024**3, 6), "kept": len(remaining)}

    # Pass 2: LRU
    remaining.sort()
    for mtime, pp, mp in remaining:
        if total <= cap_bytes:
            break
        st, rb = _stat(mp)
        if st in ("validated", "caveat") or rb:
            continue
        sz = _rm(pp, mp)
        freed += sz
        total -= sz
        evicted += 1

    kept = sum(1 for _, pp, _ in remaining if os.path.exists(pp))
    return {"evicted": evicted, "freed_gb": round(freed/1024**3, 6), "kept": kept}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running cas.py self-test...")
    import sys
    tmp_dir = tempfile.mkdtemp(prefix="cas_selftest_")
    me = sys.modules[__name__]
    orig_root = CAS_ROOT
    me.CAS_ROOT = os.path.join(tmp_dir, "cas")
    _REGISTRY.clear()
    _MAT_KEY.clear()

    # Temp input files
    fa = os.path.join(tmp_dir, "a.txt")
    fb = os.path.join(tmp_dir, "b.txt")
    open(fa, "w").write("hello")
    open(fb, "w").write("world")

    calls = {"A": 0, "B": 0}
    def bld_a() -> pd.DataFrame:
        calls["A"] += 1; return pd.DataFrame({"x": [1,2,3]})
    def bld_b() -> pd.DataFrame:
        calls["B"] += 1; return pd.DataFrame({"y": [4,5,6]})

    # Test 1: B depends on A; first materialise computes both once
    register_node("A", bld_a, [fa], "out_A")
    register_node("B", bld_b, [fb], "out_B", upstream_node_ids=["A"])
    df = materialize("B")
    assert list(df["y"]) == [4,5,6]
    assert calls == {"A":1,"B":1}, calls
    print("  [PASS] first materialise: A+B computed once")

    # Test 2: second materialise -> cache hits, no recompute
    df2 = materialize("B")
    assert list(df2["y"]) == [4,5,6]
    assert calls == {"A":1,"B":1}, f"recomputed on cache hit: {calls}"
    print("  [PASS] second materialise: cache hits, no recompute")

    # Test 3: touch A's input file -> B becomes stale -> both recompute
    open(fa, "w").write("hello_changed")
    _MAT_KEY.clear()
    sc = stale_count()
    assert sc["stale"] > 0, f"expected stale after input change: {sc}"
    print(f"  [PASS] stale_count after touch: {sc}")
    materialize("B")
    assert calls["A"] == 2, f"A should recompute: {calls}"
    assert calls["B"] == 2, f"B should cascade: {calls}"
    print("  [PASS] after touch A input: B recomputed (cascade)")

    # Test 4: gc evicts rejected, keeps validated
    cas_dir = me.CAS_ROOT
    for key, status in [("aabbccdd"*4, "rejected"), ("11223344"*4, "validated")]:
        sd = os.path.join(cas_dir, key[:2]); os.makedirs(sd, exist_ok=True)
        pd.DataFrame({"z": range(10)}).to_parquet(os.path.join(sd, f"{key}.parquet"), index=False)
        with open(os.path.join(sd, f"{key}.meta.json"), "w") as f:
            json.dump({"status": status, "referenced_by": [], "node_id":"x",
                       "entity":"","input_hash":"x","builder":"","created_utc":""}, f)
    res = gc(cap_gb=0.0)
    rej_p = os.path.join(cas_dir, "aa", "aabbccdd"*4 + ".parquet")
    val_p = os.path.join(cas_dir, "11", "11223344"*4 + ".parquet")
    assert not os.path.exists(rej_p), "rejected should be evicted"
    assert os.path.exists(val_p), "validated should be kept"
    assert res["evicted"] >= 1, res
    print(f"  [PASS] gc: rejected evicted, validated kept. {res}")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    me.CAS_ROOT = orig_root
    _REGISTRY.clear(); _MAT_KEY.clear()
    print("cas.py self-test PASS")
