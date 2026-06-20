"""One-off driver: build soccer_cardstates__<combo>.parquet for the combo corpora used by
INCREMENT-3's detail_layer_gate. Combo corpora span two leagues, so for each game_id we try
both member leagues' summary endpoint and keep whichever returns commentary. Writes the SAME
schema as ingest_cardstate_states.build_card_states. Bounded by --max games for runtime.

NOT a gated tree; lives under domains/soccer/. Zero new network tier (same summary endpoint).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List

import pandas as pd

from domains.soccer.ingest_cardstate_states import (
    _SUMMARY, _STATE_DIR, _get, build_card_states, card_events,
)

_COMBO_LEAGUES = {
    "combo_eng_ger": ("eng.1", "ger.1"),
    "combo_esp_ita": ("esp.1", "ita.1"),
}


def build(combo: str, max_games: int) -> Path:
    base = _STATE_DIR / f"soccer_states__{combo}.parquet"
    ids = list(pd.read_parquet(base)["game_id"].astype(str).unique())[:max_games]
    leagues = _COMBO_LEAGUES[combo]
    rows: List[dict] = []
    red_games = ok = 0
    for i, eid in enumerate(ids):
        payload = {}
        for lg in leagues:
            p = _get(_SUMMARY.format(l=lg, e=eid))
            if p.get("commentary"):
                payload = p
                break
        ev = card_events(payload) if payload else []
        if payload:
            ok += 1
        st = build_card_states(eid, ev)
        if any(r["home_reds"] or r["away_reds"] for r in st):
            red_games += 1
        rows.extend(st)
        if (i + 1) % 50 == 0:
            print("%s %d/%d fetched_ok=%d red_games=%d" % (combo, i + 1, len(ids), ok, red_games), flush=True)
        time.sleep(0.05)
    df = pd.DataFrame(rows)
    out = _STATE_DIR / f"soccer_cardstates__{combo}.parquet"
    df.to_parquet(out, index=False)
    print("DONE %s games=%d fetched_ok=%d red_games=%d rows=%d -> %s"
          % (combo, len(ids), ok, red_games, len(df), out), flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--combo", required=True, choices=list(_COMBO_LEAGUES))
    ap.add_argument("--max", type=int, default=400)
    a = ap.parse_args()
    build(a.combo, a.max)


if __name__ == "__main__":
    main()
