"""Registry spine: content-hash IDs + sharded, transactional, deduped registry I/O.

The registries (signal/model/engine/calibration) ARE the operational memory (MASTER_SYSTEM_BUILD
section 3/5): hashed, deduped, the single source of truth. This package gives every artifact a
content-addressed id (ids.py) and an append-only, atomic, lock-serialized store (store.py).
"""
from .ids import signal_id, model_id, engine_id, content_hash, normalize_formula  # noqa: F401
from .store import Registry, registry_lock, transactional_write, SCHEMAS  # noqa: F401
