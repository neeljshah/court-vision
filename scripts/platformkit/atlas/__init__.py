"""scripts.platformkit.atlas — Multi-sport atlas build driver package.

Public surface
--------------
``build_all``    CLI driver: builds per-sport atlases and the unified hub note.
``hub_writer``   Emits ``vault/Sports/_Hub.md`` (the Obsidian memory-graph root).

Usage::

    python scripts/platformkit/atlas/build_all.py --sport all --out vault/Sports

See ``build_all.py`` for the full CLI reference.
"""
from __future__ import annotations
