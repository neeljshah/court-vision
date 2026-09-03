"""S106 -- RE-QUOTE the S82 and S87 in-game headline CIs on CORRECTED clusters.

Nothing model-side is recomputed: the archived per-tick paired losses are read as
written and only the CLUSTER UNIT changes, from the re-used Kalshi ticker
(`game_id`) to `(game_id, real_game_seq)` from `real_game_split`.  Every published
CI is reproduced from its own series CSV first; a failed reproduction is reported,
never silently replaced.  No charge, no seal, no bar moved, no archived artifact
rewritten -- output goes to a NEW `s106_requote_<date>.json`.

  python -m scripts.platformkit.eval_gate.s106_requote
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from scripts.platformkit.eval_gate.archive_read import read_series
from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq, cluster_ids
# reuse: the SAME DM + clustered-ESS quote S87 published with (no second implementation)
from scripts.platformkit.eval_gate.tick_informative import _quote

_REPO = Path(__file__).resolve().parents[3]
_CACHE = _REPO / "data" / "cache" / "eval_gate"
_JOINED = _REPO / "data" / "cache" / "ingame_grade_joined" / "mlb"

S82_SERIES = "s82_ingame_screen_series_2026-09-03.csv"
S82_JSON = "s82_ingame_screen_2026-09-03.json"
S87_JSON = "s87_requote_2026-09-03.json"
S58A_SERIES = "s58_trialA_clamp_family_series_2026-09-03.csv"
TOP_N_S82 = 3


def load_joined(joined: Path = _JOINED) -> pd.DataFrame:
    """Every joined MLB tick as (game_id, ts, state_summary).  Read-only."""
    rows: List[Dict[str, Any]] = []
    for path in sorted(joined.glob("*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("ts"):
                    rows.append({"game_id": str(rec.get("game_id") or path.stem),
                                 "ts": rec["ts"],
                                 "state_summary": rec.get("state_summary", "")})
    return pd.DataFrame(rows)


def _seq_map(joined_frame: pd.DataFrame) -> Dict[tuple, int]:
    """(game_id, ts) -> real_game_seq, the only bridge into an archived series."""
    return dict(zip(zip(joined_frame["game_id"].astype(str), joined_frame["ts"].astype(str)),
                    joined_frame["real_game_seq"].astype(int)))


def _attach(frame: pd.DataFrame, seq_by: Dict[tuple, int], game_col: str,
            ts_col: str) -> Dict[str, Any]:
    """Attach `real_game_seq` + `cluster` in place; return the join coverage."""
    keys = list(zip(frame[game_col].astype(str), frame[ts_col].astype(str)))
    seqs = [seq_by.get(k) for k in keys]
    n_missing = sum(1 for s in seqs if s is None)
    # an unmatched tick keeps its own game_id as its cluster (seq 1): never dropped
    frame["real_game_seq"] = [1 if s is None else s for s in seqs]
    frame["cluster"] = cluster_ids(frame, game_col=game_col)
    return {"n_rows": int(len(frame)), "n_unmatched_in_joined_store": int(n_missing)}


def _pair(frame: pd.DataFrame, game_col: str, loss_col: str) -> Dict[str, Any]:
    """before (cluster = game_id) vs after (cluster = game_id#real_game_seq)."""
    before = _quote(frame, game_col, loss_col)
    after = _quote(frame, "cluster", loss_col)
    return {"before_game_id_clusters": before, "after_real_game_clusters": after,
            "verdict_status": ("unchanged" if before["ci_excludes_zero_favouring_candidate"]
                               == after["ci_excludes_zero_favouring_candidate"]
                               else "RE-LABEL REQUIRED")}


def requote_s82(seq_by: Dict[tuple, int], cache: Path = _CACHE,
                top_n: int = TOP_N_S82) -> List[Dict[str, Any]]:
    """Re-quote the top-`top_n` S82 screen features (by published improvement_vs_null)."""
    published = json.loads((cache / S82_JSON).read_text(encoding="utf-8"))
    ranked = sorted(published["results"], key=lambda r: -float(r["improvement_vs_null"]))[:top_n]
    series = read_series(cache / S82_SERIES)
    out: List[Dict[str, Any]] = []
    for row in ranked:
        sub = series[series["feature"] == row["feature"]].copy()
        sub["_d"] = ((sub["p_null"] - sub["y"]) ** 2) - ((sub["p_candidate"] - sub["y"]) ** 2)
        coverage = _attach(sub, seq_by, "game", "timestamp")
        pair = _pair(sub, "game", "_d")
        pub_ci = [float(v) for v in row["dm_ci95"]]
        reproduced = max(abs(a - b) for a, b in
                         zip(pub_ci, pair["before_game_id_clusters"]["dm_ci95"])) < 1e-9
        out.append({
            "artifact": "s82_ingame_screen", "feature": row["feature"],
            "series_csv": S82_SERIES, "summary_json": S82_JSON,
            "published_status": row["status"], "published_clears_bar": bool(row["clears_bar"]),
            "published_n_games": int(row["n_games"]), "published_n_ticks": int(row["n_ticks"]),
            "published_ci95": pub_ci, "published_ci_reproduced_from_series": bool(reproduced),
            "note": "d = loss(null_recal) - loss(candidate); cluster unit corrected only",
            "join_coverage": coverage, **pair,
        })
    return out


def requote_s87_trial_a(seq_by: Dict[tuple, int], cache: Path = _CACHE) -> Dict[str, Any]:
    """Re-quote S87's trial-A (s58_trialA_clamp) headline CI on corrected clusters."""
    series = read_series(cache / S58A_SERIES)
    series["_d"] = (((series["incumbent_e4_gd"] - series["y"]) ** 2)
                    - ((series["candidate"] - series["y"]) ** 2))
    coverage = _attach(series, seq_by, "game", "timestamp")
    pair = _pair(series, "game", "_d")
    s87 = json.loads((cache / S87_JSON).read_text(encoding="utf-8"))
    entry = next(r for r in s87["results"] if r["artifact"] == "s58_trialA_clamp")
    pub_ci = [float(v) for v in entry["before_all_rows"]["dm_ci95"]]
    reproduced = max(abs(a - b) for a, b in
                     zip(pub_ci, pair["before_game_id_clusters"]["dm_ci95"])) < 1e-9
    return {"artifact": "s87_requote:s58_trialA_clamp", "series_csv": S58A_SERIES,
            "summary_json": S87_JSON, "published_verdict": entry["published_verdict"],
            "published_n_games": int(entry["before_all_rows"]["n_games"]),
            "published_n": int(entry["before_all_rows"]["n"]),
            "published_ci95": pub_ci, "published_ci_reproduced_from_series": bool(reproduced),
            "note": "d = loss(incumbent e4_gd) - loss(candidate); cluster unit corrected only",
            "join_coverage": coverage, **pair}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="S106: re-quote MLB in-game CIs on real-game clusters")
    parser.add_argument("--out", default=str(_CACHE / "s106_requote_2026-09-03.json"))
    args = parser.parse_args(argv)

    joined = load_joined()
    joined, store = assign_real_game_seq(joined)
    seq_by = _seq_map(joined)
    print("joined store: %d game_ids -> %d real games (%d multi), %d ticks, %d reassigned" % (
        store["n_game_ids"], store["n_real_games"], store["n_multi"], store["n_ticks"],
        store["n_ticks_reassigned"]))
    print("  boundary reasons: %s" % store["boundary_reasons"])

    results = requote_s82(seq_by) + [requote_s87_trial_a(seq_by)]
    for row in results:
        before, after = row["before_game_id_clusters"], row["after_real_game_clusters"]
        print("%s%s | reproduced %s | %s" % (
            row["artifact"], (" / " + row["feature"]) if "feature" in row else "",
            row["published_ci_reproduced_from_series"], row["verdict_status"]))
        print("  n_games %d -> %d | n_eff %.2f -> %.2f | ci95 [%.6f, %.6f] -> [%.6f, %.6f]" % (
            before["n_games"], after["n_games"], before["n_eff"], after["n_eff"],
            before["dm_ci95"][0], before["dm_ci95"][1], after["dm_ci95"][0], after["dm_ci95"][1]))

    payload = {"gap": "S106", "generated_at": datetime.now(timezone.utc).isoformat(),
               "tier": "RE-QUOTE (no charge, no seal, no bar moved, no model recomputed)",
               "joined_store_split": store, "results": results}
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
