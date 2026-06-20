"""scripts.platformkit.ingame.gate_run_nba_possession -- GATE-RUN for the NBA in-game
POSSESSION / PACE / SCORING-RUN detail layer (UNTESTED_DATA lane).

The PBP possession micro-state from domains.basketball_nba.ingest_possession_states
(possessions_elapsed / pace_so_far / run_diff / poss_since_lead_change) has never been
gate-run as an in-game DETAIL layer on top of the PROVEN (margin, time) in-game base.
This runner threads each additive detail column -- AND a PLANTED-NULL pure-noise control
-- through the EXISTING, UNWEAKENED detail-layer gate
(possession_layer_gate_nba.gate_column -> detail_layer_gate.gate_detail_layer ->
ingame_gate_generic.gate_cross): BASE = sigmoid((a+b*frac)*state_diff) fit on TRAIN only,
+DETAIL blends a per-row squashed detail via a TRAIN-fit weight surface, DM CLUSTERED by
game_id, degenerate-base guard, graceful-degrade negative control, cross-corpus A<->B
(2024_25 <-> 2025_26) in BOTH directions.

WHAT THIS RUNNER ADDS (no new scoring math -- it CONSUMES the gate):
  (a) real on-disk corpora load via possession_layer_gate_nba.load_corpus (>=2
      independent seasons; INSUFFICIENT_DATA reported honestly if a corpus is absent);
  (b) a PLANTED-NULL pure-noise detail column injected into BOTH corpora and run through
      the IDENTICAL gate, which MUST NOT replicate. If the null DOES replicate, the whole
      run is UNTRUSTWORTHY -> layer verdict NOT_TESTABLE and we say so loudly;
  (c) a single honest layer verdict + a serialized verdict JSON under
      data/frontend/funnel/ (this lane's OWN file -- no shared append, no registry).

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, creates NO sentinel,
autostarts nothing. CALIBRATION only (held-out Brier) -- NO $ / ROI / edge field anywhere;
vs_close stays UNPROVEN (held-out yardstick, never a feature). A REJECT is the EXPECTED,
honest, SUCCESSFUL outcome: the 4-sport meta-finding rejected generic in-game micro-state.
A REJECTED column is kept as VALIDATED SCOUTING; it is NEVER force-fed into the model.
ASCII-only; numpy/pandas + stdlib; <=300 LOC. Never edit src/ or kernel/.
CLI: python -m scripts.platformkit.ingame.gate_run_nba_possession --a 2024_25 --b 2025_26
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import possession_layer_gate_nba as PG

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "data" / "frontend" / "funnel" / "nba_possession_ingame_gate.json"

_NULL_COL = "planted_null_diff"   # pure-noise control -- MUST NOT replicate
# verdicts that count as "the gate rejected this column" (gate CAN fail a signal)
_REJECTING = ("REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA")


def _inject_null(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Add a seeded N(0,1) pure-noise column (no outcome dependence, no leak).

    Returns a COPY so the caller's frame is untouched. The null is independent of the
    label, so a correct gate must route its TRAIN weight surface to w->0 and REJECT it.
    """
    out = df.copy()
    rng = np.random.default_rng(seed)
    out[_NULL_COL] = rng.standard_normal(len(out))
    return out


def _verdict_to_dict(col: str, v) -> Dict[str, object]:
    """Serialize a GenericVerdict for one detail column (held-out Brier both dirs)."""
    return {
        "column": col,
        "verdict": v.verdict,
        "a_to_b": dict(v.a_to_b) if v.a_to_b else {},
        "b_to_a": dict(v.b_to_a) if v.b_to_a else {},
    }


def run(season_a: str = "2024_25", season_b: str = "2025_26",
        *, min_ticks: int = 200, eps: float = 0.05, seed: int = 0,
        write: bool = True) -> Dict[str, object]:
    """Gate every possession detail column + the planted null cross-corpus A<->B.

    Returns an honest verdict dict and (write=True) serializes it to the funnel JSON.
    INSUFFICIENT_DATA (honest) if either season's parquet is absent -- need >=2
    independent corpora to replicate.
    """
    try:
        df_a = PG.load_corpus(season_a)
        df_b = PG.load_corpus(season_b)
    except FileNotFoundError as exc:
        res = {"layer": "nba_possession_ingame", "verdict": "INSUFFICIENT_DATA",
               "reason": str(exc), "n_corpora": 0, "columns": {}, "null": None,
               "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge"}
        if write:
            _write(res)
        return res

    # inject the SAME planted-null into both corpora (gated identically to real cols)
    df_a_n = _inject_null(df_a, seed)
    df_b_n = _inject_null(df_b, seed + 1)

    columns: Dict[str, object] = {}
    for col in PG.DETAIL_COLS:
        v = PG.gate_column(df_a, df_b, col, min_ticks=min_ticks, eps=eps)
        columns[col] = _verdict_to_dict(col, v)

    null_v = PG.gate_column(df_a_n, df_b_n, _NULL_COL, min_ticks=min_ticks, eps=eps)
    null = _verdict_to_dict(_NULL_COL, null_v)
    null_rejects = null_v.verdict in _REJECTING

    any_replicated = any(c["verdict"] == "REPLICATED" for c in columns.values())
    if not null_rejects:
        layer_verdict = "NOT_TESTABLE"          # gate could not fail a noise column
    elif any_replicated:
        layer_verdict = "REPLICATED"            # surfaced as a PROPOSAL only
    else:
        layer_verdict = "REJECT"

    res: Dict[str, object] = {
        "layer": "nba_possession_ingame",
        "verdict": layer_verdict,
        "season_a": season_a, "season_b": season_b, "n_corpora": 2,
        "a_games": int(df_a["game_id"].nunique()), "a_states": int(len(df_a)),
        "b_games": int(df_b["game_id"].nunique()), "b_states": int(len(df_b)),
        "eps": eps, "min_ticks": min_ticks,
        "base_model": "sigmoid((a+b*frac_elapsed)*state_diff); a,b FIT per corpus on TRAIN",
        "detail_model": "blend(squash(detail), BASE, w(time,margin)); w fit on TRAIN only",
        "design": "cross-corpus A<->B (2 seasons); DM clustered by game_id; "
                  "degenerate-base guard; graceful-degrade negative control",
        "columns": columns,
        "null": null, "null_rejects": null_rejects, "proposal_only": True,
        "wired_into_repricer": False,
        "scouting_note": "REJECTED columns kept as VALIDATED SCOUTING; NEVER force-fed "
                         "into the model as a feature (that destroys calibration).",
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "no_dollar_field": True,
    }
    if write:
        _write(res)
    return res


def _write(res: Dict[str, object]) -> None:
    """Write this lane's OWN verdict JSON (no shared append -> no write collision)."""
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(res, indent=2, sort_keys=True), encoding="ascii")


def _fmt_dir(d: dict) -> str:
    if not d:
        return "(none)"
    return (f"BASE {d.get('brier_base')} -> +detail {d.get('brier_prior')} "
            f"(delta {d.get('brier_delta')}) DM p {d.get('dm_p')} "
            f"detail_beats_base={d.get('prior_beats_base')} "
            f"degenerate={d.get('base_degenerate')}")


def _report(res: Dict[str, object]) -> str:
    lines = ["=" * 76,
             "NBA IN-GAME POSSESSION/PACE/RUN DETAIL-LAYER GATE-RUN (cross-corpus A<->B)",
             "=" * 76,
             "GATE   : possession_layer_gate_nba -> detail_layer_gate -> gate_cross",
             "         (BASE fit on TRAIN; DM clustered by game_id; degenerate guard;",
             "          graceful-degrade null control). PROPOSAL-ONLY; CALIBRATION only.",
             f"LAYER  : nba_possession_ingame   VERDICT: {res['verdict']}"]
    if res["verdict"] == "INSUFFICIENT_DATA":
        lines += [f"  {res.get('reason')}", "=" * 76]
        return "\n".join(lines)
    lines += [f"A={res['season_a']} ({res['a_games']} games / {res['a_states']} states)  "
              f"B={res['season_b']} ({res['b_games']} games / {res['b_states']} states)",
              f"vs_close: {res['vs_close']}", "-" * 76]
    for col, c in res["columns"].items():           # type: ignore[union-attr]
        lines.append(f"\n[{col}]  VERDICT={c['verdict']}")
        lines.append(f"   A->B: {_fmt_dir(c['a_to_b'])}")
        lines.append(f"   B->A: {_fmt_dir(c['b_to_a'])}")
    n = res["null"]
    lines += ["\n" + "-" * 76,
              f"PLANTED-NULL control [{_NULL_COL}]: verdict {n['verdict']}  "       # type: ignore[index]
              f"REJECTS={res['null_rejects']}",
              f"   A->B: {_fmt_dir(n['a_to_b'])}",                                   # type: ignore[index]
              f"   B->A: {_fmt_dir(n['b_to_a'])}"]                                   # type: ignore[index]
    if not res["null_rejects"]:
        lines.append("  *** GATE UNTRUSTWORTHY: noise column did NOT reject. ***")
    else:
        lines.append("  null rejected as required -> the gate CAN fail a signal.")
    lines += ["-" * 76,
              f"wired_into_repricer={res['wired_into_repricer']}  "
              "(REJECT/PARTIAL kept as VALIDATED SCOUTING, never force-fed).",
              "Calibration (held-out Brier) only; NO $/edge; vs-close UNPROVEN.",
              "=" * 76]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate the NBA in-game possession/pace/run detail layer (proposal-only).")
    ap.add_argument("--a", default="2024_25")
    ap.add_argument("--b", default="2025_26")
    ap.add_argument("--min-ticks", type=int, default=200)
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    res = run(a.a, a.b, min_ticks=a.min_ticks, eps=a.eps, seed=a.seed,
              write=not a.no_write)
    print(_report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run", "main", "_inject_null", "_NULL_COL"]
