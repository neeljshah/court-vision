"""scripts.platformkit.ingame.s83_join_identity_backfill -- one-off S83 backfill.

WHY A BACKFILL AND NOT A RE-RUN: ticker_settlement_join now carries the five
_CARRY_KEYS player-identity fields through the join, so every FUTURE join keeps
player grain. The EXISTING data/cache/ingame_grade_joined/mlb store cannot simply
be re-run: its outcome corpus (data/domains/mlb/espn_boxscores.parquet) has since
shrunk to 2 rows, so backfill_sport resolves 1 of 235 tickers today and a re-run
would DESTROY 226 files.  This module therefore only ADDS the identity fields onto
the rows already on disk.

MATCHED POSITIONALLY, not on (game_id, ts): join_ticker_file emits exactly one
joined row per VALID source tick, in file order, so row i of the joined file IS
tick i of _load_ticks(source).  Verified on the live store -- 227/227 files, 78,986
rows, zero ts mismatches.  A (game_id, ts) dict instead collapses the 22 duplicate
keys the store really contains, which is why the positional match is the one that
reproduces what the fixed join itself would write.  A file whose lengths or ts
sequence disagree is SKIPPED whole -- never a guessed alignment.

It NEVER re-derives outcome, close_prob, close_ts or any probability: a joined row
that gains no identity is re-emitted BYTE-IDENTICAL (the original line, verbatim).

Self-check:  python -m scripts.platformkit.ingame.s83_join_identity_backfill
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.ticker_settlement_join import (
    DEFAULT_GRADE_DIR, DEFAULT_JOINED_DIR, _CARRY_KEYS, _load_ticks,
)


def _joined_lines(path: Path) -> List[str]:
    return [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def backfill_file(joined_path: Path, src_path: Path,
                  out_path: Optional[Path] = None) -> Dict[str, Any]:
    """Add the identity fields to ONE joined file, matched positionally against the
    source ticks. Returns {n_rows, n_enriched, status, path}; status='misaligned'
    (and nothing written) when the two files do not correspond row for row."""
    old = _joined_lines(joined_path)
    ticks = _load_ticks(src_path)
    result: Dict[str, Any] = {"n_rows": len(old), "n_enriched": 0, "status": "ok",
                              "path": str(joined_path)}
    if len(ticks) != len(old):
        return dict(result, status="misaligned", n_rows=len(old))
    lines = []
    for line, tick in zip(old, ticks):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            return dict(result, status="misaligned")
        if str(row.get("ts")) != str(tick.get("ts")):
            return dict(result, status="misaligned")
        ids = {k: tick[k] for k in _CARRY_KEYS if k in tick}
        if ids:
            row.update(ids)
            result["n_enriched"] += 1
            lines.append(json.dumps(row, ensure_ascii=True))
        else:
            lines.append(line)                  # byte-identical passthrough
    target = Path(out_path) if out_path is not None else joined_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")
    result["path"] = str(target)
    return result


def backfill_sport(sport: str = "mlb", *, grade_dir: Optional[Path] = None,
                   joined_dir: Optional[Path] = None,
                   out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """backfill_file() over every joined file of *sport*. out_dir=None edits in place."""
    gdir = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    jdir = Path(joined_dir) if joined_dir is not None else DEFAULT_JOINED_DIR
    files = sorted((jdir / sport).glob("*.jsonl"))
    tot = {"sport": sport, "n_files": len(files), "n_rows": 0, "n_enriched": 0,
           "n_misaligned": 0, "n_files_enriched": 0}
    for jp in files:
        out = None if out_dir is None else Path(out_dir) / sport / jp.name
        r = backfill_file(jp, gdir / sport / jp.name, out)
        tot["n_rows"] += r["n_rows"]
        tot["n_enriched"] += r["n_enriched"]
        tot["n_misaligned"] += 1 if r["status"] == "misaligned" else 0
        tot["n_files_enriched"] += 1 if r["n_enriched"] else 0
    return tot


def demo() -> None:
    """Self-check: identity lands on the right row positionally (the two ticks share
    a ts and would collide in a dict), a tick without identity stays byte-identical,
    and a length mismatch is refused rather than guessed."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        src = base / "grade" / "mlb" / "KXA.jsonl"
        src.parent.mkdir(parents=True)

        def tick(ts, **kw):
            return json.dumps(dict({"game_id": "KXA", "ts": ts, "model_prob": 0.5,
                                    "market_prob": 0.5}, **kw))
        src.write_text("\n".join([tick("t1", mlb_pitcher_id=7, mlb_batter_id=8),
                                  tick("t1", mlb_pitcher_id=9, mlb_batter_id=10),
                                  tick("t2")]) + "\n", encoding="utf-8")
        jp = base / "joined" / "mlb" / "KXA.jsonl"
        jp.parent.mkdir(parents=True)
        orig = [json.dumps({"game_id": "KXA", "ts": t, "model_prob": 0.5,
                            "edge_claimed": False}) for t in ("t1", "t1", "t2")]
        jp.write_text("\n".join(orig) + "\n", encoding="utf-8")

        r = backfill_file(jp, src)
        assert r["status"] == "ok" and r["n_rows"] == 3 and r["n_enriched"] == 2, r
        got = jp.read_text(encoding="utf-8").splitlines()
        assert json.loads(got[0])["mlb_pitcher_id"] == 7    # positional, not last-wins
        assert json.loads(got[1])["mlb_pitcher_id"] == 9
        assert json.loads(got[0])["model_prob"] == 0.5      # untouched
        assert got[2] == orig[2]                            # byte-identical

        short = base / "grade" / "mlb" / "KXB.jsonl"
        short.write_text(tick("t1") + "\n", encoding="utf-8")
        assert backfill_file(jp, short)["status"] == "misaligned"
    print("s83_join_identity_backfill demo OK")


if __name__ == "__main__":  # pragma: no cover
    demo()


__all__ = ["backfill_file", "backfill_sport", "demo"]
