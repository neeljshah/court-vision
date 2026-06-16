"""scripts.platformkit.knowledge.warm -- pre-warm a per-game intel cache.

Pre-assembles a scouting-context bundle once (async/offline) and writes it to
data/cache/intel_warm/<game_id>.json (gitignored). The LIVE read path reads only
that JSON -- NO embedding, NO rerank, NO LLM in the hot loop -- keeping the live
overlay budget tiny. The bundle obeys the same HARD BOUNDARY (no probability/odds/
edge; honest-reject is first-class). ASCII only. Per-file test: tests/test_warm.py
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List, Optional

from . import config
from .assemble import assemble, check_bundle


def warm_game(game_id: str, sport: str, home_id: str = "", away_id: str = "",
              question: Optional[str] = None,
              cache_dir: Path = config.WARM_CACHE_DIR) -> dict:
    """Assemble + persist a per-game bundle JSON. Returns the payload dict."""
    t0 = time.time()
    bundle = assemble(sport, home_id=home_id, away_id=away_id, question=question)
    violations = check_bundle(bundle)
    if violations:
        raise RuntimeError(f"boundary violation in warmed bundle: {violations}")
    payload = {
        "game_id": game_id, "sport": sport, "home_id": home_id, "away_id": away_id,
        "question": question, "bundle": bundle.markdown,
        "citations": bundle.citations, "reject": bundle.reject,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_s": round(time.time() - t0, 2),
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{game_id}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="ascii")
    return payload


def read_warm(game_id: str, cache_dir: Path = config.WARM_CACHE_DIR) -> Optional[dict]:
    """Fast live read of a pre-warmed bundle (no index load). None on miss."""
    p = cache_dir / f"{game_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="ascii"))


def warm_many(matchups: List[dict], cache_dir: Path = config.WARM_CACHE_DIR) -> int:
    n = 0
    for m in matchups:
        warm_game(m["game_id"], m["sport"], m.get("home_id", ""),
                  m.get("away_id", ""), m.get("question"), cache_dir)
        n += 1
    return n


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser(description="Pre-warm a per-game intel cache.")
    ap.add_argument("--game-id", default=None)
    ap.add_argument("--sport", default="NBA")
    ap.add_argument("--home-id", default="")
    ap.add_argument("--away-id", default="")
    ap.add_argument("--question", default=None)
    ap.add_argument("--from-json", default=None,
                    help="JSON list of {game_id,sport,home_id,away_id,question?}.")
    args = ap.parse_args()
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="ascii"))
        print(f"warmed {warm_many(data)} games -> {config.WARM_CACHE_DIR}")
    else:
        gid = args.game_id or f"adhoc-{int(time.time())}"
        pl = warm_game(gid, args.sport, args.home_id, args.away_id, args.question)
        print(f"warmed {gid} ({pl['build_s']}s, reject={pl['reject']})")
