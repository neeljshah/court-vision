"""Wave 2 folder: render durability_availability signals into player notes.

Adds a "## Durability & Availability" section into the canonical
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY EXIST (does not create stubs).

Signals rendered:
  - Games missed to injury per season (last 3 full seasons)
  - Availability rate per season (games appeared / total eligible)
  - Mean minutes per game and high-min-game rate per season
  - Rolling L10 minutes at most-recent game (prior-game-only, pregame safe)
  - Age and position on aging curve (years from canonical peak)
  - Rampup flag: games/days since last 7+ day inter-game gap

Leak status displayed in the section header so consumers know what is
scouting-only vs. pregame-safe vs. in-game-safe.

Run after build_durability_availability.py:
  python scripts/signals/fold_durability_availability.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "durability_availability.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:durability_availability START -->"
END = "<!-- SIGNALS:durability_availability END -->"

TARGET_SEASONS = ["2022-23", "2023-24", "2024-25"]


# ── rendering helpers ─────────────────────────────────────────────────────────

def _fmt_pct(v, decimals: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return f"{float(v) * 100:.{decimals}f}%"


def _fmt_f(v, decimals: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return f"{float(v):.{decimals}f}"


def _fmt_i(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return str(int(float(v)))


def _season_row(r, season: str) -> str:
    tag = season.replace("-", "_")
    gmi = _fmt_i(getattr(r, f"games_missed_injury_{tag}", None))
    gmcd = _fmt_i(getattr(r, f"games_missed_cd_{tag}", None))
    avail = _fmt_pct(getattr(r, f"avail_rate_{tag}", None))
    mpg = _fmt_f(getattr(r, f"min_mpg_{tag}", None))
    hmr = _fmt_pct(getattr(r, f"high_min_rate_{tag}", None))
    return (f"**{season}** — inj missed: {gmi} · coach-dec: {gmcd} · "
            f"avail rate: {avail} · MPG: {mpg} · high-min (≥32 min): {hmr}")


def _aging_line(r) -> str:
    age = _fmt_f(getattr(r, "age_as_of", None), 1)
    yfp = getattr(r, "years_from_peak", None)
    if yfp is None or (isinstance(yfp, float) and pd.isna(yfp)):
        return f"Age: {age}"
    direction = "past peak" if float(yfp) >= 0 else "before peak"
    return f"Age: {age} · {abs(float(yfp)):.1f} yrs {direction} (position canonical peak)"


def _rampup_line(r) -> str:
    gsince = getattr(r, "games_since_last_7d_absence", None)
    dsince = getattr(r, "days_since_last_7d_absence", None)
    if gsince is None or (isinstance(gsince, float) and pd.isna(gsince)):
        return "Rampup: no 7-day+ gap found in history"
    return (f"Last 7d+ gap: {_fmt_i(gsince)} game(s) / {_fmt_i(dsince)} day(s) ago "
            f"(rampup window: <5 games = cautious minutes)")


def build_block(r) -> str:
    avail_l3 = _fmt_pct(getattr(r, "avail_rate_l3seas", None))
    l10 = _fmt_f(getattr(r, "min_l10_latest", None))

    lines = [
        START, "",
        "## Durability & Availability",
        ("*Games-missed, availability rate (games appeared / eligible), and minutes load. "
         "Season-agg signals are scouting-only (no in-game leak). Rolling L10 minutes "
         "uses shift(1) — pregame-safe. Aging curve = canonical position peak ±years.*"),
        "",
    ]
    for s in TARGET_SEASONS:
        lines.append("- " + _season_row(r, s))
    lines += [
        "",
        f"**L3-season avail rate:** {avail_l3}",
        f"**Rolling L10 MPG (prior-game):** {l10}",
        f"**{_aging_line(r)}**",
        f"**{_rampup_line(r)}**",
        "",
        END, "",
    ]
    return "\n".join(lines)


# ── upsert logic ──────────────────────────────────────────────────────────────

def upsert(note_path: str, block: str) -> None:
    txt = open(note_path, encoding="utf-8").read()
    if START in txt and END in txt:
        txt = re.sub(
            re.escape(START) + r".*?" + re.escape(END) + r"\n?",
            "",
            txt,
            flags=re.S,
        )
    txt = txt.rstrip() + "\n\n" + block
    open(note_path, "w", encoding="utf-8").write(txt)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    df = pd.read_parquet(SIG)
    folded = skipped = 0
    for _, row in df.iterrows():
        pid = int(row.player_id)
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped += 1
            continue
        block = build_block(row)
        upsert(cands[0], block)
        folded += 1
    print(
        f"DONE: folded durability_availability into {folded} player notes "
        f"({skipped} skipped: no vault note)."
    )


if __name__ == "__main__":
    main()
