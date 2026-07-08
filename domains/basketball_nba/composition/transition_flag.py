"""domains.basketball_nba.composition.transition_flag -- a DERIVED transition-
possession flag built on top of shot_clock_proxy's possession-segment chain
(no possession pace-state/transition flag exists anywhere in the corpus --
see nba_hypotheses.BLOCKED_REASONS["lineup spacing x transition frequency"]).

transition = shot taken within TRANSITION_WINDOW_S=6.0s of its own possession
start (the standard NBA-analytics cut; same possession chain
shot_clock_proxy.resolve_segments already builds -- no new inference here).

VALIDATE against the one place a real signal exists: the 196 CDN-native files
carry a 'fastbreak' qualifier on shot actions. Report precision/recall of the
derived flag against that qualifier (CDN files only -- ESPN files carry no
qualifiers at all, so there is nothing to check the ESPN-derived flag against
directly; its quality is bounded by shot_clock_proxy.cdn_semantic_agreement's
96.8% number, since it rides the same inferred chain).

Descriptive/measurement only. NETWORK: zero.
CLI: python -m domains.basketball_nba.composition.transition_flag
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from domains.basketball_nba.composition.shot_clock_proxy import _detect_mode, _PBP_DIR, resolve_segments

TRANSITION_WINDOW_S = 6.0


def build_transition_frame(pbp_dir: Path = _PBP_DIR, limit: Optional[int] = None) -> pd.DataFrame:
    """One row per 2pt/3pt shot attempt with the derived is_transition flag,
    plus (CDN files only) the real 'fastbreak' qualifier for validation."""
    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    rows = []
    for fp in files:
        d = json.loads(fp.read_text(encoding="utf-8"))
        game_id = d["game"]["gameId"]
        actions = d["game"]["actions"]
        mode = _detect_mode(actions)
        resolved = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
        for a in actions:
            if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId"):
                continue
            r = resolved[a["actionNumber"]]
            if r["seg_team"] is None:
                continue
            since_start = r["elapsed_s"] - r["seg_start_s"]
            rows.append({
                "game_id": game_id, "team_id": a["teamId"], "period": a["period"],
                "elapsed_s": r["elapsed_s"],
                "is_transition": int(0 <= since_start <= TRANSITION_WINDOW_S),
                "has_fastbreak_qualifier": int("fastbreak" in (a.get("qualifiers") or [])) if mode == "cdn_field" else None,
                "source_mode": mode,
            })
    return pd.DataFrame(rows)


def validate_vs_fastbreak_qualifier(df: pd.DataFrame) -> Dict[str, Any]:
    """Precision/recall of is_transition against the real 'fastbreak'
    qualifier, CDN-native shots only (mode=='cdn_field')."""
    cdn = df[df["source_mode"] == "cdn_field"]
    if cdn.empty:
        return {"n": 0, "precision": None, "recall": None}
    tp = int(((cdn["is_transition"] == 1) & (cdn["has_fastbreak_qualifier"] == 1)).sum())
    fp = int(((cdn["is_transition"] == 1) & (cdn["has_fastbreak_qualifier"] == 0)).sum())
    fn = int(((cdn["is_transition"] == 0) & (cdn["has_fastbreak_qualifier"] == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {"n": int(len(cdn)), "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall}


def main() -> int:
    df = build_transition_frame()
    n_transition = int(df["is_transition"].sum())
    pr = validate_vs_fastbreak_qualifier(df)
    print(f"transition_flag: n_shots={len(df)} n_transition={n_transition} "
          f"pct_transition={n_transition / len(df):.4f}")
    print(f"vs fastbreak qualifier (CDN only): n={pr['n']} precision={pr['precision']:.4f} "
          f"recall={pr['recall']:.4f} tp={pr['tp']} fp={pr['fp']} fn={pr['fn']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
