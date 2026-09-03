"""S177 -- re-quote S88's archived calibration readout by real-game cluster.

The archived probabilities are never refit.  The ticker basis remains the default
and the real-game basis only changes the cluster used for the paired-loss quote.
The one output artifact contains both bases and the per-unit differential needed to
recompute their intervals.

Run: python -m scripts.platformkit.eval_gate.s88_requote
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq, cluster_ids
from scripts.platformkit.ingame.s88_phase_recal import score_bucket

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "docs" / "evidence" / "harness" / "s88_phase_recal_2026-09-04.csv"
JOINED_STORE = ROOT / "data" / "cache" / "ingame_grade_joined" / "mlb"
OUT = ROOT / "docs" / "evidence" / "harness" / "s88_cluster_unit_2026-09-04.json"
_BUCKETS = ("pooled", "late|leading_big", "mid|trailing")


def _joined_rows(store: Path) -> pd.DataFrame:
    """Read each bounded joined file once and retain only split inputs."""
    rows: List[Dict[str, str]] = []
    for path in sorted(store.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                rows.append({"game_id": str(item["game_id"]), "ts": str(item["ts"]),
                             "state_summary": str(item.get("state_summary") or "")})
    return pd.DataFrame(rows).drop_duplicates(["game_id", "ts"], keep="first").reset_index(drop=True)


def attach_real_game_clusters(archive: pd.DataFrame, store: Path = JOINED_STORE) -> Dict[str, Any]:
    """Join S106's pure real-game labels onto every archived S88 tick."""
    joined = _joined_rows(store)
    split, summary = assign_real_game_seq(joined)
    split["real_game_cluster"] = cluster_ids(split)
    lookup = dict(zip(zip(split["game_id"], split["ts"]), split["real_game_cluster"]))
    out = archive.copy()
    out["real_game_cluster"] = [lookup.get((str(g), str(t)))
                                for g, t in zip(out["game_id"], out["ts"])]
    if out["real_game_cluster"].isna().any():
        raise ValueError("archive tick missing from joined store")
    return {"frame": out, "split_summary": summary}


def _row(records: List[Dict[str, Any]], basis: str, bucket: str) -> Dict[str, Any]:
    score = score_bucket(records, cluster_column=basis)
    return {"basis": "ticker" if basis == "game_id" else "real_game", "bucket": bucket,
            "n_eval_ticks": score["n"], "n_informative_ticks": score["n_informative"],
            "n_clusters": score["n_games_informative"],
            "delta_vs_incumbent_mean": score["delta_vs_incumbent_mean"],
            "delta_vs_incumbent_ci95": score["delta_vs_incumbent_ci95"],
            "verdict_vs_incumbent": score["verdict_vs_incumbent"]}


def _paired_series(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    informative = frame[frame["is_informative"].astype(bool)]
    out = []
    for row in informative.itertuples(index=False):
        out.append({"cluster_id": row.real_game_cluster, "timestamp": row.ts,
                    "incumbent_loss": (row.model_prob - row.outcome) ** 2,
                    "recal_loss": (row.recal_prob - row.outcome) ** 2})
    return out


def build_artifact(archive: pd.DataFrame, split_summary: Dict[str, Any]) -> Dict[str, Any]:
    """Publish all informative ticks under both unchanged probability columns."""
    if int(archive["is_informative"].astype(bool).sum()) != 11087:
        raise ValueError("S88 informative denominator drift")
    table = []
    for basis in ("game_id", "real_game_cluster"):
        for bucket in _BUCKETS:
            block = archive if bucket == "pooled" else archive[archive["phase_bucket"] == bucket]
            table.append(_row(block.to_dict("records"), basis, bucket))
    paired = _paired_series(archive)
    units = []
    for cluster, block in archive[archive["is_informative"].astype(bool)].groupby("real_game_cluster", sort=True):
        inc = (block["model_prob"] - block["outcome"]) ** 2
        recal = (block["recal_prob"] - block["outcome"]) ** 2
        units.append({"cluster_id": str(cluster), "n_informative_ticks": int(len(block)),
                      "incumbent_brier": float(inc.mean()), "recal_brier": float(recal.mean()),
                      "loss_delta": float((inc - recal).mean())})
    return {"row": "S177", "sport": "mlb", "source_archive": str(ARCHIVE),
            "n_eval_ticks": int(len(archive)), "n_informative_ticks": 11087,
            "split_summary": split_summary, "readout": table,
            "real_game_cluster_series": units, "paired_loss_series": paired,
            "not_verified": ["No probabilities were refit.", "No live deployment was evaluated."],
            "calibration_only": True}


def write_artifact(out_path: Path = OUT, archive_path: Path = ARCHIVE,
                   store: Path = JOINED_STORE) -> Dict[str, Any]:
    """Write the one self-contained re-quote artifact outside data/."""
    joined = attach_real_game_clusters(pd.read_csv(archive_path), store)
    artifact = build_artifact(joined["frame"], joined["split_summary"])
    out_path.write_text(json.dumps(artifact, indent=1, sort_keys=True), encoding="ascii")
    return artifact


def main() -> int:
    artifact = write_artifact()
    for row in artifact["readout"]:
        print("%s %s clusters=%d verdict=%s" % (row["basis"], row["bucket"],
              row["n_clusters"], row["verdict_vs_incumbent"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
