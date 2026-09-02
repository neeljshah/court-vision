"""Leak-free walk-forward backtest harness -- the eval gate's long pole (blueprint N1).

Self-contained (stdlib only). This is where leak-freeness is ENFORCED, not assumed:
  - expanding window: train only on states strictly before the test state's timestamp (no lookahead);
  - purge: drop same-team games within 48h of the test game (kills back-to-back autocorrelation);
  - embargo: drop the same matchup within 3 days of the boundary (rolling-window spillover);
  - vintage alignment: every feature must be known strictly before the prediction time;
  - feature selection / tuning MUST happen inside the window -> the `select_inside` flag is recorded,
    and a caller that selects on the full history (select_inside=False) is surfaced so the gate fails.

predict_fn(train_states, test_state, select_inside) -> p in [0,1]. The harness never trains a model;
it orchestrates the leak-free split and collects per-state probabilities for scoring (scoring.py).
Calibration-first; no dollar edge is computed.

Red-team hardening (2026-09-01): each invocation deep-copies the caller's states, so a
predictor that mutates its train/test views cannot poison the caller's list and read the
plant back on a later walk_forward call over the same states. The test view also drops
"index" (a raw-row pointer some callers attach for train-side lookups). NOTE the limit:
the harness redacts the VIEWS it hands out; it cannot police a predict_fn that closes
over the raw corpus arrays directly -- callers must route test-row inputs through the
declared, vintage-checked `features` channel (see combo_search.py / pbo.py).
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Sequence, Tuple

PURGE_HOURS = 48
EMBARGO_DAYS = 3

# S40b / RT-18. The legacy redaction was a DENY-list of four known settled names, so the
# NEXT settled column added to a state schema reached the predictor by default (measured:
# a state carrying `final_margin` scored Brier 0.0000 with no LeakError). TEST_VIEW_KEYS is
# the ALLOW-list: the structural keys backtest_runner._redact already keeps, plus the
# non-settled descriptors the golden corpus carries. A caller declares anything else it
# genuinely needs on the test row via `allow_keys`; in strict mode an UNDECLARED key is a
# LeakError instead of a silent pass-through.
TEST_VIEW_KEYS = ("game_id", "state_ts", "features", "feature_avail", "home", "away",
                  "season", "sport", "game_date", "regime")
# Legacy (non-strict) behaviour, byte-identical to the pre-S40b deny-list.
_SETTLED_DENY = ("outcome", "devig_close_prob", "truth_wp", "index")


class LeakError(AssertionError):
    """Assertion-compatible failure for every eval-gate leak contract violation."""

    def __init__(self, message: str) -> None:
        text = str(message)
        super().__init__(text if "LEAK" in text else f"LEAK: {text}")


def _teams(s: dict) -> set:
    return {s["home"], s["away"]}


def _same_team(a: dict, b: dict) -> bool:
    return len(_teams(a) & _teams(b)) > 0


def _same_matchup(a: dict, b: dict) -> bool:
    return _teams(a) == _teams(b)


def redact_test_view(state: dict, *, allow_keys: Sequence[str] = (),
                     strict: bool = False) -> dict:
    """Return the view a predictor may see for THIS test row (RT-18).

    strict=False (default) keeps the pre-S40b deny-list survivors exactly, so no existing
    caller changes. strict=True keeps only TEST_VIEW_KEYS + `allow_keys` and raises
    LeakError on any undeclared key -- a new settled column then fails closed.
    """
    if not strict:
        return {k: v for k, v in state.items() if k not in _SETTLED_DENY}
    allowed = set(TEST_VIEW_KEYS) | set(allow_keys)
    # The four historically-known settled keys stay silently dropped (that part always
    # worked). What must fail closed is a key that is NEITHER allowed NOR known settled.
    undeclared = sorted(k for k in state if k not in allowed and k not in _SETTLED_DENY)
    if undeclared:
        raise LeakError(
            f"undeclared test-row key(s) {undeclared} in {state.get('game_id')}; "
            "declare them via allow_keys or keep them out of the test view"
        )
    return {k: v for k, v in state.items() if k in allowed}


def assert_vintage(s: dict) -> None:
    """LEAK GUARD: every feature must be known strictly before the prediction time."""
    features = s.get("features", {})
    availability = s.get("feature_avail", {})
    if not availability:
        raise LeakError(f"empty feature_avail in {s.get('game_id')}")
    if set(features) != set(availability):
        raise LeakError(f"feature_avail keys do not match features in {s.get('game_id')}")
    try:
        state_ts = datetime.fromisoformat(s["state_ts"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LeakError(f"unparseable state_ts {s.get('state_ts')} in {s.get('game_id')}") from exc
    for f, avail in availability.items():
        if not isinstance(avail, str) or len(avail) == 10:
            raise LeakError(f"date-only or unparseable availability {avail} for feature {f}")
        try:
            avail_ts = datetime.fromisoformat(avail)
        except (TypeError, ValueError) as exc:
            raise LeakError(f"unparseable availability {avail} for feature {f}") from exc
        if (avail_ts.tzinfo is None) != (state_ts.tzinfo is None):
            raise LeakError(f"mixed naive/aware timestamps for feature {f} in {s.get('game_id')}")
        if not avail_ts < state_ts:
            raise LeakError(
                f"feature {f} availability {avail} >= state_ts {s['state_ts']} "
                f"in {s.get('game_id')}"
            )


@dataclass
class WalkForwardResult:
    records: List[dict]          # per-state {game_id, ts, p_model, p_close, y}
    select_inside: bool          # recorded; False -> the gate must FAIL the run
    n_train_sizes: List[int]     # train-set size at each step (for diagnostics)


def walk_forward(states: List[dict],
                 predict_fn: Callable[[List[dict], dict, bool], float],
                 select_inside: bool = True,
                 *, strict_redaction: bool = False,
                 allow_keys: Sequence[str] = ()) -> WalkForwardResult:
    """Expanding-window walk-forward with purge + embargo + vintage. Returns per-state records."""
    # Deep copy: predictor-side mutation of train/test dicts must never reach the
    # caller's states (cross-invocation plant attack -- red-team 2026-09-01).
    states = copy.deepcopy(sorted(states, key=lambda s: s["state_ts"]))
    records: List[dict] = []
    sizes: List[int] = []
    for i, test in enumerate(states):
        t = datetime.fromisoformat(test["state_ts"])
        train: List[dict] = []
        for s in states[:i]:
            ts = datetime.fromisoformat(s["state_ts"])
            if ts >= t:                                   # never look ahead (tie-safe)
                continue
            if _same_matchup(s, test) and (t - ts) < timedelta(days=EMBARGO_DAYS):
                continue                                  # embargo same matchup near boundary
            if _same_team(s, test) and (t - ts) < timedelta(hours=PURGE_HOURS):
                continue                                  # purge same-team back-to-back
            train.append(s)
        assert_vintage(test)                              # defense in depth (schema also checks)
        test_view = redact_test_view(test, allow_keys=allow_keys, strict=strict_redaction)
        p = predict_fn(train, test_view, select_inside)
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"predict_fn returned {p} out of [0,1]")
        records.append({
            "game_id": test["game_id"], "ts": test["state_ts"],
            "p_model": float(p), "p_close": test.get("devig_close_prob"),
            "y": int(test["outcome"]),
        })
        sizes.append(len(train))
    return WalkForwardResult(records, bool(select_inside), sizes)
