"""scripts.platformkit.ingame.run_soccer_ingest_expanded -- Expand soccer corpora.

Ingests two new independent corpora: ger1 (Bundesliga) and ita1 (Serie A) for
the same 2024-25 season window that proved reliable for eng1 and esp1.

ESPN's older event summary API (2023-24 IDs ~671k) returns 504 errors, so we
stay within the 2024-25 window where IDs ~700k+ are reliably served.

After ingestion, builds two large combined corpora:
  soccer_states__combo_eng_ger.parquet  (eng1 + ger1)
  soccer_states__combo_esp_ita.parquet  (esp1 + ita1)

The gate picks first two alphabetically: combo_eng_ger (A) + combo_esp_ita (B),
giving ~300-400 games per corpus with independent league-pair mixing.

INVARIANTS: <=300 LOC; ASCII only; no fabrication; additive only.
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from domains.soccer.ingest_soccer_states import ingest_league  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Same window that worked for eng1/esp1 (IDs ~700k range, no 504 errors seen)
START = date(2024, 8, 1)
END = date(2025, 6, 1)

# New leagues only -- additive, do NOT overwrite existing eng1/esp1
NEW_LEAGUES = [
    ("ger.1", "ger1"),   # Bundesliga
    ("ita.1", "ita1"),   # Serie A
]

_OUT_DIR = _REPO / "data" / "cache" / "ingame"


def _corpus_stats(path: Path) -> tuple:
    """Return (games, rows, p0_fallback_rate) for a parquet corpus."""
    if not path.exists():
        return 0, 0, 1.0
    df = pd.read_parquet(path)
    games = df["game_id"].nunique()
    rows = len(df)
    p0_default = 1.0 / (1.0 + 10.0 ** (-50.0 / 400.0))
    fallback_rate = float((abs(df["p0"] - p0_default) < 0.0001).mean())
    return games, rows, fallback_rate


def _build_combo(label_a: str, label_b: str, combo_label: str) -> Path:
    """Merge two single-league parquets into one combined corpus parquet."""
    pa = _OUT_DIR / f"soccer_states__{label_a}.parquet"
    pb = _OUT_DIR / f"soccer_states__{label_b}.parquet"
    parts = []
    if pa.exists():
        parts.append(pd.read_parquet(pa))
        log.info("  combo %s: loaded %s (%d rows)", combo_label, label_a, len(parts[-1]))
    else:
        log.warning("  combo %s: %s not found", combo_label, pa)
    if pb.exists():
        parts.append(pd.read_parquet(pb))
        log.info("  combo %s: loaded %s (%d rows)", combo_label, label_b, len(parts[-1]))
    else:
        log.warning("  combo %s: %s not found", combo_label, pb)
    out = _OUT_DIR / f"soccer_states__{combo_label}.parquet"
    if not parts:
        log.warning("No source parquets found for combo %s", combo_label)
        return out
    combo = pd.concat(parts, ignore_index=True)
    # Atomic write: gates reading this path mid-rebuild must never see a
    # truncated/partial parquet (the parquet-rebuild-race landmine).
    tmp = out.with_suffix(out.suffix + ".tmp")
    combo.to_parquet(tmp, index=False)
    tmp.replace(out)
    log.info("combo %s written: games=%d rows=%d -> %s",
             combo_label, combo["game_id"].nunique(), len(combo), out)
    return out


def main() -> None:
    # Step 1: ingest new independent leagues
    new_results = []
    for league, label in NEW_LEAGUES:
        log.info("=== Ingesting %s -> %s ===", league, label)
        out = ingest_league(league, label, START, END)
        games, rows, fb = _corpus_stats(out)
        new_results.append((league, label, games, rows, fb))
        log.info("  %s: games=%d rows=%d p0_fallback=%.3f", label, games, rows, fb)

    # Step 2: build combined corpora (gate picks alphabetically first two)
    log.info("=== Building combined corpora ===")
    combo_a = _build_combo("eng1", "ger1", "combo_eng_ger")
    combo_b = _build_combo("esp1", "ita1", "combo_esp_ita")

    # Gather stats
    eng1_g, eng1_r, eng1_fb = _corpus_stats(_OUT_DIR / "soccer_states__eng1.parquet")
    esp1_g, esp1_r, esp1_fb = _corpus_stats(_OUT_DIR / "soccer_states__esp1.parquet")
    ca_g, ca_r, ca_fb = _corpus_stats(combo_a)
    cb_g, cb_r, cb_fb = _corpus_stats(combo_b)

    print()
    print("=" * 72)
    print("INGESTION SUMMARY")
    print("=" * 72)
    print("Single-league corpora:")
    print(f"  eng1  (eng.1 existing): games={eng1_g:4d}  rows={eng1_r:5d}  "
          f"p0_fallback={eng1_fb:.3f}")
    print(f"  esp1  (esp.1 existing): games={esp1_g:4d}  rows={esp1_r:5d}  "
          f"p0_fallback={esp1_fb:.3f}")
    for league, label, games, rows, fb in new_results:
        print(f"  {label:5s} ({league:7s} new  ): games={games:4d}  rows={rows:5d}  "
              f"p0_fallback={fb:.3f}")
    print()
    print("Combined corpora (gate uses these -- alphabetically first two):")
    print(f"  combo_eng_ger (A) [eng1+ger1]: games={ca_g:4d}  rows={ca_r:5d}  "
          f"p0_fallback={ca_fb:.3f}")
    print(f"  combo_esp_ita (B) [esp1+ita1]: games={cb_g:4d}  rows={cb_r:5d}  "
          f"p0_fallback={cb_fb:.3f}")
    total = ca_r + cb_r
    print(f"  TOTAL rows (combo A + B): {total}")
    print("=" * 72)
    print("Gate corpus order: sorted(soccer_states__*.parquet) -> A=combo_eng_ger, B=combo_esp_ita")
    print("Corpora are independent (different league pairs: EPL+Bundesliga vs La Liga+Serie A)")


if __name__ == "__main__":
    main()
