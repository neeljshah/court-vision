"""domains.tennis.ingest_setdetail_states -- per-SET / TIEBREAK trailing as-of.

CEILING-CONFIRMING leak-free state layer.  Emits the FROZEN base join key
(``event_id``, 1:1 to matches.parquet) PLUS additive, strictly-as-of trailing
player aggregates distilled from the per-SET / tiebreak structure that IS on
disk (the Sackmann ``score`` string).  This is the finest resolution genuinely
available zero-network -- one step finer than match, NOT point-level.

ADDITIVE AS-OF COLUMNS (per side p1/p2, prior matches ONLY, shift1 on membership):
  tiebreak_win_pct_asof   -- tiebreaks won / tiebreaks played (prior matches)
  sets_dropped_rate_asof  -- sets lost / sets played (prior matches)
  close_set_rate_asof     -- fraction of sets decided 7-6 or 7-5 (prior matches)
  avg_games_per_set_asof  -- mean games played per set (prior matches)
  + per-surface splits (_hard / _clay / _grass) of each of the four
  + *_n_prior count + p1-minus-p2 diffs for each overall metric.

LEAK DISCIPLINE (mirrors domains/tennis/asof_hold.py EXACTLY):
  * snapshot-BEFORE-update walk-forward: match i's row reads ONLY matches < i
    chronologically (the current match's own sets are NEVER in the snapshot).
  * the current ``score`` is parsed only to UPDATE history AFTER the snapshot is
    taken -- it is never read into the row for its own event_id.
  * debut players get NaN (n_prior == 0); a no-future-leak assertion is embedded.
  * NO match-final aggregate (minutes, winner, bpFaced totals) is read; only the
    per-set game counts derived from the score string are folded in.
  * the close / odds is NEVER touched -- it is a held-out yardstick, not a feature.

SCORE ORIENTATION: Sackmann ``score`` is WINNER-first.  ``winner`` (1/2) is the
STABLE-identity winner.  When winner==2 the parsed (g1,g2) tuples are swapped so
every per-side realized quantity is attributed to the correct STABLE player id
(p1_id / p2_id) -- without this swap the aggregates would track the winner.

TRAIN/INFERENCE PARITY: there is ONE builder (``build_asof_setdetail``).  The
same function produces train rows and inference rows; a feature added here reads
identically in both because both call this builder.  No parallel inference path.

HONEST EXPECTED VERDICT: REJECT-leaning.  Tiebreak / close-set "clutch on serve"
is largely re-expressed serve+return strength already captured by asof_hold /
asof_return.  A truthful REJECT here CONFIRMS the on-disk per-set ceiling and
motivates the Tier-3 (network) Match-Charting / point-by-point fetch as the only
path to a NEW signal class.  True point-by-point is NOT on disk.

NETWORK: zero (matches.parquet only).  Pure pandas/numpy.  No src/kernel/api.
CALIBRATION only -- NO $ field, NO edge claimed.  ASCII-only; <=300 LOC.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_REPO = Path(__file__).resolve().parents[2]
_ATP_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_WTA_MATCHES = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_ATP_OUT = _REPO / "data" / "domains" / "tennis" / "asof_setdetail.parquet"
_WTA_OUT = _REPO / "data" / "domains" / "tennis" / "asof_setdetail_wta.parquet"
# Materialized in-game cache mirror (the gate-facing canonical location).
_CACHE_DIR = _REPO / "data" / "cache" / "ingame"
_ATP_CACHE = _CACHE_DIR / "tennis_setdetail__atp.parquet"
_WTA_CACHE = _CACHE_DIR / "tennis_setdetail__wta.parquet"

_SURFACES = ("Hard", "Clay", "Grass")
_METRICS = ("tiebreak_win_pct", "sets_dropped_rate", "close_set_rate",
            "avg_games_per_set")

# Frozen base join key + additive as-of column manifest.
_OVERALL = tuple(f"{m}_asof" for m in _METRICS)
_SURF = tuple(f"{m}_{s.lower()}_asof" for m in _METRICS for s in _SURFACES)
_DIFFS = tuple(f"{m}_asof_diff" for m in _METRICS)

OUT_COLS: List[str] = (
    ["event_id"]
    + [f"p1_{c}" for c in _OVERALL] + [f"p2_{c}" for c in _OVERALL]
    + [f"p1_{c}" for c in _SURF] + [f"p2_{c}" for c in _SURF]
    + list(_DIFFS)
    + ["p1_n_prior", "p2_n_prior", "surface"]
)

_ROUND_ORDER = {
    "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
    "QF": 10, "SF": 11, "BR": 12, "F": 13,
}

_SCORE_RE = re.compile(r"(\d+)-(\d+)(\(\d+\))?")


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O, leak-free by construction)
# ---------------------------------------------------------------------------

def parse_sets_detail(score_str: str) -> Optional[List[Tuple[int, int, bool]]]:
    """Parse Sackmann score -> [(g1, g2, is_tiebreak), ...] WINNER-first.

    Tiebreak notation '7-6(5)' -> is_tiebreak True.  Returns None on unparseable
    / empty input.  PURE -- no I/O, reads only the supplied string.
    """
    if not isinstance(score_str, str) or not score_str.strip():
        return None
    found = _SCORE_RE.findall(score_str)
    if not found:
        return None
    return [(int(g1), int(g2), bool(tb)) for g1, g2, tb in found]


def _is_close_set(g1: int, g2: int) -> bool:
    """A set decided 7-6 or 7-5 (either side).  PURE."""
    hi, lo = (g1, g2) if g1 >= g2 else (g2, g1)
    return hi == 7 and lo in (5, 6)


def match_realized(score_str: str, winner: int
                   ) -> Optional[Tuple[dict, dict]]:
    """Per-match realized per-set quantities for (p1, p2), STABLE-identity signed.

    Returns ({tb_won, tb_played, sets_lost, sets_played, close_sets, games,
    n_sets}, {...for p2}) or None.  Sackmann score is WINNER-first; when
    winner==2 the tuples are swapped so each side's counts attach to its STABLE
    id.  PURE -- reads only this match's score; no future, no other match.
    """
    sets = parse_sets_detail(score_str)
    if sets is None or len(sets) < 2 or winner not in (1, 2):
        return None
    if winner == 2:
        sets = [(g2, g1, tb) for (g1, g2, tb) in sets]

    p1 = {"tb_won": 0, "tb_played": 0, "sets_lost": 0, "sets_played": 0,
          "close_sets": 0, "games": 0, "n_sets": 0}
    p2 = {k: 0 for k in p1}
    for g1, g2, tb in sets:
        for side, mine, theirs in ((p1, g1, g2), (p2, g2, g1)):
            side["sets_played"] += 1
            side["n_sets"] += 1
            side["games"] += mine + theirs
            if mine < theirs:
                side["sets_lost"] += 1
            if _is_close_set(g1, g2):
                side["close_sets"] += 1
            if tb:
                side["tb_played"] += 1
                if mine > theirs:
                    side["tb_won"] += 1
    return p1, p2


# ---------------------------------------------------------------------------
# Per-player running history -- overall + per surface
# ---------------------------------------------------------------------------

class _PlayerHistory:
    """Running counters for the four per-set metrics, overall + per surface."""
    __slots__ = ("n_matches", "_c")

    def __init__(self) -> None:
        self.n_matches = 0
        # key -> {tb_won, tb_played, sets_lost, sets_played, close_sets,
        #         games, n_sets}
        self._c: dict = {}

    @staticmethod
    def _metrics(c: dict) -> dict:
        sp = c.get("sets_played", 0)
        tbp = c.get("tb_played", 0)
        ns = c.get("n_sets", 0)
        return {
            "tiebreak_win_pct": c["tb_won"] / tbp if tbp > 0 else np.nan,
            "sets_dropped_rate": c["sets_lost"] / sp if sp > 0 else np.nan,
            "close_set_rate": c["close_sets"] / sp if sp > 0 else np.nan,
            "avg_games_per_set": c["games"] / ns if ns > 0 else np.nan,
        }

    def snapshot(self) -> dict:
        out: dict = {}
        for key in ("all", *_SURFACES):
            c = self._c.get(key)
            m = self._metrics(c) if c else {k: np.nan for k in _METRICS}
            for metric, val in m.items():
                out[f"{key}_{metric}"] = val
        return out

    def update(self, realized: dict, surface: str) -> None:
        self.n_matches += 1
        for key in ("all", surface):
            c = self._c.setdefault(
                key, {"tb_won": 0, "tb_played": 0, "sets_lost": 0,
                      "sets_played": 0, "close_sets": 0, "games": 0,
                      "n_sets": 0})
            for k in c:
                c[k] += realized[k]


# ---------------------------------------------------------------------------
# Leak guard + chrono sort (mirror asof_hold)
# ---------------------------------------------------------------------------

def _stable_chrono_sort(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)

    def _col(name, default):
        return df[name] if name in df.columns else pd.Series([default] * n, index=df.index)

    key_df = pd.DataFrame({
        "k0": pd.to_datetime(_col("date", None)).values,
        "k1": _col("tour", "").astype(str).values,
        "k2": _col("tourney_id", "").astype(str).values,
        "k3": _col("round", "").map(_ROUND_ORDER).fillna(6).astype(int).values,
        "k4": pd.to_numeric(_col("match_num", 0), errors="coerce").fillna(0).astype("int64").values,
    }, index=df.index)
    order = key_df.sort_values(["k0", "k1", "k2", "k3", "k4"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def assert_no_future_leak(df: pd.DataFrame) -> None:
    """Debut rows (n_prior==0) MUST have NaN as-of metrics, else future-leak."""
    bad = 0
    for side in ("p1", "p2"):
        m0 = df[f"{side}_n_prior"] == 0
        for metric in _METRICS:
            bad += df.loc[m0, f"{side}_{metric}_asof"].notna().sum()
    if bad > 0:
        raise AssertionError(
            f"Future-leak: {bad} debut-row cells with non-NaN as-of metric.")


# ---------------------------------------------------------------------------
# Builder -- the SINGLE train==inference code path
# ---------------------------------------------------------------------------

def build_asof_setdetail(matches: pd.DataFrame,
                         out_path: Optional[str] = None) -> pd.DataFrame:
    """Build leak-free per-set/tiebreak as-of features keyed by ``event_id``.

    Snapshot-BEFORE-update walk-forward identical to asof_hold.  Returns the
    DataFrame (and writes parquet when ``out_path`` is given).  Debut players get
    NaN.  Raises AssertionError on detected future-leak.
    """
    spine = matches[["event_id", "date", "tour", "tourney_id", "round",
                     "match_num", "p1_id", "p2_id", "winner", "score",
                     "surface", "retirement"]].copy()
    spine = _stable_chrono_sort(spine)

    n = len(spine)
    eids = spine["event_id"].to_numpy()
    p1_ids = pd.to_numeric(spine["p1_id"], errors="coerce").to_numpy()
    p2_ids = pd.to_numeric(spine["p2_id"], errors="coerce").to_numpy()
    surfaces = spine["surface"].fillna("Unknown").to_numpy(dtype=str)
    scores = spine["score"].to_numpy()
    winners = pd.to_numeric(spine["winner"], errors="coerce").fillna(0).astype(int).to_numpy()
    retired = spine["retirement"].fillna(False).to_numpy()

    hist: dict = {}
    rows: List[dict] = []
    for i in range(n):
        p1 = float(p1_ids[i]); p2 = float(p2_ids[i]); surf = surfaces[i]
        h1 = hist.setdefault(p1, _PlayerHistory())
        h2 = hist.setdefault(p2, _PlayerHistory())

        s1 = h1.snapshot(); s2 = h2.snapshot()
        row: dict = {"event_id": eids[i], "surface": surf,
                     "p1_n_prior": h1.n_matches, "p2_n_prior": h2.n_matches}
        for metric in _METRICS:
            v1 = s1[f"all_{metric}"]; v2 = s2[f"all_{metric}"]
            row[f"p1_{metric}_asof"] = v1
            row[f"p2_{metric}_asof"] = v2
            row[f"{metric}_asof_diff"] = (v1 - v2) if (
                not np.isnan(v1) and not np.isnan(v2)) else np.nan
        for s in _SURFACES:
            for metric in _METRICS:
                row[f"p1_{metric}_{s.lower()}_asof"] = s1[f"{s}_{metric}"]
                row[f"p2_{metric}_{s.lower()}_asof"] = s2[f"{s}_{metric}"]
        rows.append(row)

        # UPDATE strictly AFTER the snapshot (this match never enters its own row).
        # Retirements have unreliable per-set tails -> skip the update.
        if not bool(retired[i]):
            realized = match_realized(str(scores[i]), int(winners[i]))
            if realized is not None:
                r1, r2 = realized
                h1.update(r1, surf)
                h2.update(r2, surf)

    result = pd.DataFrame(rows)[OUT_COLS].copy()
    result["p1_n_prior"] = result["p1_n_prior"].astype("int64")
    result["p2_n_prior"] = result["p2_n_prior"].astype("int64")

    assert_no_future_leak(result)

    if out_path is not None:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(result, preserve_index=False), dest)
    return result


def _main() -> None:
    ap = argparse.ArgumentParser(
        description="Build tennis per-set/tiebreak as-of features (ATP + WTA).")
    ap.add_argument("--tour", choices=["atp", "wta", "both"], default="both")
    args = ap.parse_args()

    tours = {"atp": (_ATP_MATCHES, _ATP_OUT, _ATP_CACHE),
             "wta": (_WTA_MATCHES, _WTA_OUT, _WTA_CACHE)}
    selected = list(tours) if args.tour == "both" else [args.tour]
    for tour in selected:
        src, dst, cache = tours[tour]
        if not src.exists():
            print("Missing: %s -- skipping %s" % (src, tour))
            continue
        matches = pd.read_parquet(src)
        # The builder writes the domains/ artifact; we ALSO materialize the
        # canonical in-game cache mirror the gate reads (same bytes, no recompute).
        df = build_asof_setdetail(matches, out_path=str(dst))
        cache.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), cache)
        print("[%s] matches=%d rows=%d -> %s ; cache -> %s"
              % (tour.upper(), len(df), len(df), dst, cache))
    print("Done.")


if __name__ == "__main__":
    _main()
