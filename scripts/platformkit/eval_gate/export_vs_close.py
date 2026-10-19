"""Export the soccer O/U 2.5 holdout rows (devigged probabilities only) for score_vs_close.

Read-only reuse of dm_recompute_pregame.rows_soccer (the DM memo's row builder): same
model, same proportional devig, same chronological fit/holdout split, cluster_id as
match_id. Writes only the six public columns; no prices, no bookmaker fields.
ATP is not exported: its matches/outcomes come from the Sackmann corpus, licence
ledger row 10 = UNREAD.

Run from the full (private) checkout:
  python -m scripts.platformkit.eval_gate.export_vs_close --out-dir docs/evidence/pregame_vs_close
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from scripts.platformkit.eval_gate.dm_recompute_pregame import INPUTS, _REPO, rows_soccer

COLUMNS = ["date_utc", "match_id", "p_model", "p_close_devig", "devig_method", "y"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    m = rows_soccer()
    h = m[m["split"] == "holdout"].copy()
    out = h.assign(date_utc=h["date"].dt.strftime("%Y-%m-%d"), match_id=h["cluster_id"],
                   p_close_devig=h["p_close"], devig_method="proportional",
                   y=h["y"].astype(int))[COLUMNS]
    out = out.sort_values(["date_utc", "match_id"], kind="mergesort")
    path = args.out_dir / "soccer_ou25_holdout.csv"
    out.to_csv(path, index=False, lineterminator="\n", encoding="ascii")
    print(f"wrote {len(out)} rows -> {path}")
    for p in INPUTS["soccer_ou25"]:
        print(f"{p}: {hashlib.sha256((_REPO / p).read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
