"""Self-check: WNBA elo_refresh gate rows replayed through reprocess_harness
must reproduce elo_refresh_verdict.json's own brier_base/brier_cand numbers
within 1e-6 (mission spine 2, wave-33 gap closure PART C).

Reuses domains.basketball_wnba.elo_refresh_gate_io.build_harness_rows (which
itself reuses elo_refresh_gate._replay_candidate -- no new scoring path
invented). Compares against the COMMITTED verdict.json on disk so a real
mismatch (not a schema issue) is reported honestly rather than silently
tuned away.

CLI:
    python -m scripts.platformkit.reprocess.selfcheck_elo
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
_VERDICT_PATH = _REPO / "data" / "domains" / "wnba" / "elo_refresh_verdict.json"
_ROWS_OUT = _REPO / "data" / "domains" / "wnba" / "elo_refresh_harness_rows.parquet"
_SELFCHECK_OUT = _REPO / "data" / "domains" / "wnba" / "reprocess_selfcheck_elo.json"

TOL = 1e-6


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def run_selfcheck() -> dict[str, Any]:
    from domains.basketball_wnba.elo_refresh_gate import (
        CANDIDATES, TRAIN_FRAC, _SCOREBOARD, build_corpus,
    )
    from domains.basketball_wnba.elo_refresh_gate_io import build_harness_rows

    if not _VERDICT_PATH.exists() or not _SCOREBOARD.exists():
        return {
            "component": "reprocess_selfcheck_elo", "status": "BLOCKED_MISSING_INPUT",
            "reason": [f"required input missing: verdict={_VERDICT_PATH.exists()} "
                       f"scoreboard={_SCOREBOARD.exists()}"],
            "matched": None, "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    committed = json.loads(_VERDICT_PATH.read_text(encoding="ascii"))
    feat = build_corpus()
    rows = build_harness_rows(feat, TRAIN_FRAC)
    _ROWS_OUT.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(_ROWS_OUT, index=False)

    fields_compared: list[dict[str, Any]] = []
    max_abs_diff = 0.0
    all_matched = True

    for cname in CANDIDATES:
        corpus = f"wnba_elo_refresh_{cname}"
        committed_folds = {f["season"]: f for f in committed["candidate_folds"].get(cname, [])}
        for season, fold in committed_folds.items():
            g = rows[(rows["corpus_id"] == corpus) & (rows["fold_id"] == season)]
            if g.empty:
                all_matched = False
                fields_compared.append({
                    "candidate": cname, "season": season, "matched": False,
                    "reason": "no exported rows for this candidate/season",
                })
                continue
            y = g["outcome"].to_numpy(dtype=float)
            replay_base = _brier(g["p_base"].to_numpy(dtype=float), y)
            replay_cand = _brier(g["p_variant"].to_numpy(dtype=float), y)

            d_base = abs(replay_base - fold["brier_base"])
            d_cand = abs(replay_cand - fold["brier_cand"])
            ok = d_base <= TOL and d_cand <= TOL
            all_matched = all_matched and ok
            max_abs_diff = max(max_abs_diff, d_base, d_cand)
            fields_compared.append({
                "candidate": cname, "season": season, "matched": bool(ok),
                "committed_brier_base": fold["brier_base"], "replay_brier_base": replay_base,
                "abs_diff_base": d_base,
                "committed_brier_cand": fold["brier_cand"], "replay_brier_cand": replay_cand,
                "abs_diff_cand": d_cand,
                "n_test": int(len(g)),
            })

    payload = {
        "component": "reprocess_selfcheck_elo",
        "status": "MATCHED" if all_matched else "MISMATCH",
        "matched": bool(all_matched),
        "tolerance": TOL,
        "max_abs_diff": max_abs_diff,
        "fields_compared": fields_compared,
        "target_reference": _VERDICT_PATH.relative_to(_REPO).as_posix(),
        "harness_rows_path": _ROWS_OUT.relative_to(_REPO).as_posix(),
        "method": "domains.basketball_wnba.elo_refresh_gate_io.build_harness_rows reuses "
                  "elo_refresh_gate._replay_candidate on the SAME cold-start within-season "
                  "fold construction the committed gate scored; per-row p_base/p_variant/"
                  "outcome re-aggregated to Brier here and diffed against the committed "
                  "verdict.json brier_base/brier_cand -- no new scoring path, no re-fitting.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
    }
    return payload


def write_selfcheck(payload: dict[str, Any], dest: Path = _SELFCHECK_OUT) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1), encoding="ascii")
    return str(dest)


def main() -> int:
    payload = run_selfcheck()
    print(f"status={payload['status']} matched={payload.get('matched')} "
          f"max_abs_diff={payload.get('max_abs_diff')}")
    write_selfcheck(payload)
    print(f"wrote {_SELFCHECK_OUT}")
    return 0 if payload.get("matched") else 1


if __name__ == "__main__":
    raise SystemExit(main())
