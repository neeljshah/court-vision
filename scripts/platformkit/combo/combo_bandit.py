"""scripts.platformkit.combo.combo_bandit -- persistent Beta-Thompson over the combo space.

The enumerator (combination_enum) already ranks a SUPPLIED list with a per-family
Beta posterior, but it owns NO state across cycles. This module is the persistent,
deterministic bandit STATE: a per-family Beta(ships, rejects) posterior carried in
data/cache/improve/combo/combo_bandit_state.json, updated each cycle from gate verdicts,
and FROZEN family-wide the instant a planted-null combination ships.

Design invariants (each load-bearing):
  * DETERMINISTIC (UH3 no-favorite): the selection score is the POSTERIOR MEAN (no RNG
    sampling), so a restart re-derives the identical batch order and NO family carries a
    built-in favorite. A skeptical Beta(1,4) prior means a family must EARN its pass-rate.
  * FREEZE on null-ship: when a family's planted-null combination ever ships, the family
    is frozen (null_shipped=True) -- emitted in the ledger row shape prioritizer.frozen_families
    READS verbatim, so the loop-level FWER tripwire is inherited, not re-derived. A frozen
    family's real candidates never gate again until a human reviews.
  * REPLICATION_PENDING is a PARTIAL -- neither a ship nor a reject (it does not move the
    Beta posterior; it is recorded so the cycle is observable).
  * Atomic temp+fsync+os.replace persistence (never torn) under data/cache/improve/combo/.

State ONLY under data/cache/improve/combo/**. NEVER writes data/registry/, MEMORY.md,
never flips a flag, never creates the sentinel. Calibration, not edge; no $/ROI token.
stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Verdict tokens the bandit consumes (mirror combo_gate.SHIP/REJECT + the partial state).
SHIP = "SHIP"
REJECT = "REJECT"
PARTIAL = "REPLICATION_PENDING"

# Skeptical prior: a family must EARN its pass-rate posterior from gate verdicts.
_BETA_A, _BETA_B = 1.0, 4.0

_REPO = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_STATE = _REPO / "data" / "cache" / "improve" / "combo" / "combo_bandit_state.json"


@dataclass
class BanditState:
    """Per-family bandit posterior + the frozen-family tripwire.

    arms : {family: {"ships": int, "rejects": int, "partials": int,
            "null_shipped": bool, "last_k": int}}
    """

    arms: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def arm(self, family: str) -> Dict[str, Any]:
        return self.arms.setdefault(
            str(family),
            {"ships": 0, "rejects": 0, "partials": 0, "null_shipped": False, "last_k": 0})

    def to_dict(self) -> Dict[str, Any]:
        return {"arms": self.arms}

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "BanditState":
        if not isinstance(d, dict):
            return cls()
        arms = d.get("arms")
        return cls(arms=dict(arms) if isinstance(arms, dict) else {})


def post_mean(state: BanditState, family: str) -> float:
    """Beta(1,4)-posterior MEAN pass rate for a family (deterministic; no sampling)."""
    a = state.arm(family)
    s, r = int(a.get("ships", 0)), int(a.get("rejects", 0))
    return (_BETA_A + s) / (_BETA_A + _BETA_B + s + r)


def is_frozen(state: BanditState, family: str) -> bool:
    """True iff the family's planted null ever shipped (loop-level FWER freeze)."""
    return bool(state.arm(family).get("null_shipped", False))


def frozen_ledger(state: BanditState) -> Dict[str, Dict[str, Any]]:
    """A {family: {"null_shipped": bool}} ledger in the EXACT shape prioritizer reads.

    prioritizer.frozen_families consumes a mapping of family -> row with a truthy
    "null_shipped" flag; emitting it here lets the existing prioritizer freeze logic
    fire UNCHANGED (tests-mirror-real: no parallel freeze rule).
    """
    return {fam: {"null_shipped": bool(a.get("null_shipped", False))}
            for fam, a in state.arms.items()}


def update(state: BanditState, family: str, verdict: str, *,
           is_null: bool = False, k: Optional[int] = None) -> BanditState:
    """Apply ONE gate verdict to a family arm (mutates + returns state).

    SHIP -> +1 ship; REJECT -> +1 reject; REPLICATION_PENDING -> +1 partial (the Beta
    posterior does NOT move on a partial). A planted-null SHIP FREEZES the family
    (null_shipped=True) -- the loop-level FWER tripwire. Unknown verdicts are ignored.
    """
    a = state.arm(family)
    if k is not None:
        a["last_k"] = int(k)
    if verdict == SHIP:
        a["ships"] = int(a.get("ships", 0)) + 1
        if is_null:
            a["null_shipped"] = True  # FREEZE: a known null shipped (manufactured win).
    elif verdict == REJECT:
        a["rejects"] = int(a.get("rejects", 0)) + 1
    elif verdict == PARTIAL:
        a["partials"] = int(a.get("partials", 0)) + 1
    return state


def family_order(state: BanditState, families) -> list:
    """Deterministic family draw order: posterior-mean DESC, frozen families LAST, then name.

    No RNG -- a restart re-derives the identical order (UH3 no-favorite: the order is a pure
    function of the persisted ledger). Frozen families sink unconditionally below live ones.
    """
    fams = list(dict.fromkeys(str(f) for f in families))

    def _key(f: str):
        return (1 if is_frozen(state, f) else 0, -post_mean(state, f), f)
    return sorted(fams, key=_key)


def _atomic_write(path: pathlib.Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_state(path: Optional[str] = None) -> BanditState:
    """Load the bandit state; a missing/torn/garbage file -> a fresh empty state."""
    p = pathlib.Path(path) if path else DEFAULT_STATE
    if not p.exists():
        return BanditState()
    try:
        return BanditState.from_dict(json.loads(p.read_text(encoding="ascii")))
    except (OSError, ValueError, TypeError):
        return BanditState()


def save_state(state: BanditState, path: Optional[str] = None) -> pathlib.Path:
    """Persist the bandit state atomically (temp+fsync+os.replace -- never torn)."""
    p = pathlib.Path(path) if path else DEFAULT_STATE
    _atomic_write(p, json.dumps(state.to_dict(), sort_keys=True, indent=2))
    return p


# A per-family (pass, fail) ledger view for the enumerator's _family_post_mean.
def enum_ledger(state: BanditState) -> Dict[str, tuple]:
    """{family: (pass, fail)} view consumed by combination_enum's per-family Beta term.

    A FROZEN family is reported with zero passes so it sinks in the enum ranking too
    (the freeze is honoured in BOTH the bandit order and the enum's posterior).
    """
    out: Dict[str, tuple] = {}
    for fam, a in state.arms.items():
        if a.get("null_shipped"):
            out[fam] = (0, int(a.get("rejects", 0)) + int(a.get("ships", 0)))
        else:
            out[fam] = (int(a.get("ships", 0)), int(a.get("rejects", 0)))
    return out


__all__ = [
    "SHIP", "REJECT", "PARTIAL", "BanditState", "post_mean", "is_frozen",
    "frozen_ledger", "update", "family_order", "load_state", "save_state",
    "enum_ledger", "DEFAULT_STATE",
]
