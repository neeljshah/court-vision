"""scripts.platformkit.execution.writer_identity -- one-writer guard for the SHARED ledger.

The paper CLV ledger has exactly ONE sanctioned writer: the pod paper node
(memory: pod_paper_node_2026_08_31). Until now that was operational discipline
only -- any host that imported the record path could append to the default
ledger. This module is the code-level check: writes to the DEFAULT ledger path
are refused unless this process is the sanctioned writer. Explicitly injected
ledger paths (tests, scratch replays) are never gated -- the guard protects the
shared file, not the mechanism.

Identity rule (checked at write time, never at import):
  * CV_LEDGER_WRITER env set truthy ("1"/"true"/"yes"/"pod") -> armed writer.
  * CV_LEDGER_WRITER env set falsy ("0"/"false"/"no")         -> never a writer.
  * unset -> posix hosts (the pod) are the writer; Windows (this dev box, where
    the paper daemon must never run) is not.

ponytail: host-class check (posix vs nt), not a pod-id allowlist -- it targets
the one real incident class (paper daemon booted on the local Windows box).
Upgrade to a hostname/pod-id allowlist if a second Linux writer ever exists.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/execution/test_writer_identity.py -q
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

ARM_ENV = "CV_LEDGER_WRITER"
_TRUTHY = frozenset({"1", "true", "yes", "pod"})
_FALSY = frozenset({"0", "false", "no"})


def default_ledger_write_allowed(environ: Optional[Mapping[str, str]] = None,
                                 host_os: Optional[str] = None) -> bool:
    """True iff this process may append to the DEFAULT (shared) CLV ledger."""
    env = os.environ if environ is None else environ
    osname = os.name if host_os is None else host_os
    flag = str(env.get(ARM_ENV, "")).strip().lower()
    if flag in _TRUTHY:
        return True
    if flag in _FALSY:
        return False
    return osname != "nt"


__all__ = ["ARM_ENV", "default_ledger_write_allowed"]
