"""S102: the S82 in-game screen tier, adapted to the NBA in-play tick corpus.

WHAT IS REUSED, VERBATIM AND UNEDITED, FROM S82 (`foundry/ingame_screen.py`)
---------------------------------------------------------------------------
`assert_tick_asof` (truncation-invariance guard), `walk_forward_feature` (the purged,
embargoed, game-disjoint walk-forward and its two fits) and `BAR = 0.004`. Nothing in
that module is changed by this lane, so the MLB screen it published is untouched (B2/B10).

WHAT IS DIFFERENT ON THE NBA SIDE
---------------------------------
1. CORPUS. The rows are the S86 SCREEN-side archive
   `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` -- 232,951 ticks / 797 games,
   the side `foundry.tiers.partition_corpus(seed=0)` assigned to SCREEN on game blocks.
   The 796-game VERDICT side is never read by this lane.
2. ANCHOR. The MLB tier anchors on the `e4_gd` blend; the NBA corpus has no such blend, so
   the anchor is the IN-PLAY MARKET LINE itself and the null arm is S94's global
   recalibration `[1, logit(market)]`, fit walk-forward on exactly the candidate's rows.
   The tier's `p_e4` column therefore holds the market probability, and `brier_e4` in the
   artifact equals `brier_market` by construction -- that identity is the honest label,
   not a coincidence, and the bar is applied to `improvement_vs_null` as in S82.
3. HYPOTHESES. 576 frozen derived-state hypotheses from
   `foundry/ingame_grammar_nba.py`, family `ingame_nba_tickgrid`, not 14 hand-named columns.
4. FOLDS. NBA has ~500 distinct game dates; one fold per date would refit 576 x 500 times.
   Folds are 6 CONTIGUOUS BLOCKS of game-first dates of roughly equal tick count (block 0 is
   the train-only seed), and the block key is passed to `walk_forward_feature` in the
   `game_date` slot. The purge is unchanged: a train game must have produced its LAST tick
   at least 1 day before the fold's first tick, and `train.ts.max() < test.ts.min()` is
   asserted per fold. Blocks are assigned by the game's FIRST date, so folds stay
   game-disjoint (S36).
5. DM. The cluster-robust interval is computed by `_dm_fast`, a vectorised restatement of
   `dm_test.diebold_mariano` -- 576 hypotheses x 233k ticks through the reference
   implementation's per-cluster python loop does not finish. The per-file test asserts the
   two agree to 1e-12 on real rows; the reference is the definition, this is the same
   arithmetic done with `np.bincount`.

A SCREEN IS A NON-FINDING. No ledger row, no prereg seal, no charge: this module imports
nothing from `backtest_runner` and consumes no K. Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_screen_nba.py -q
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import (_student_t_two_tailed_pvalue,
                                                   _student_t_two_tailed_quantile)
from scripts.platformkit.foundry import ingame_grammar_nba as grammar
from scripts.platformkit.foundry import ingame_grammar_nba_pairs as pair_grammar
from scripts.platformkit.foundry.grammar import semantic_hash
from scripts.platformkit.foundry.ingame_incumbent_nba import INCUMBENTS, apply_incumbent
from scripts.platformkit.foundry.ingame_screen import (BAR, ROOT, assert_column_blind,
                                                       gate_features, walk_forward_feature)

S86_CSV = ROOT / "data" / "cache" / "eval_gate" / "s86_nba_every_tick_2026-09-03.csv"
OUT_DIR = ROOT / "data" / "cache" / "eval_gate"
STEM = "s102_nba_sweep"
N_FOLDS = 5                      # test blocks; block 0 is the train-only seed
EMBARGO_DAYS = 1                 # same as S82; the purge rule is S82's, unchanged
COLS = ("game_id", "game_date", "ts", "period", "score_home", "score_away", "margin",
        "elapsed", "rem", "informative", "model", "market", "y")
SCHEMA = """CREATE TABLE IF NOT EXISTS screen (
 hypothesis_id TEXT PRIMARY KEY, label TEXT, feature TEXT, transform TEXT, params TEXT,
 phase TEXT, status TEXT, n_ticks INTEGER, n_games INTEGER, n_informative INTEGER,
 n_eff REAL, brier_market REAL, brier_null REAL, brier_candidate REAL,
 improvement_vs_null REAL, dm_stat REAL, dm_p_raw REAL, ci_lo REAL, ci_hi REAL,
 coverage REAL, clears_bar INTEGER, folds TEXT, seconds REAL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"""


def load_screen(path: Path = S86_CSV, n_folds: int = N_FOLDS,
                incumbent: str = "market") -> pd.DataFrame:
    """The S86 SCREEN-side per-tick archive as the tier's `rows` frame.

    `p_e4` holds the in-play market probability: on this corpus the market IS the
    incumbent the candidate must improve on, and the null arm recalibrates it. `game_date`
    holds the FOLD BLOCK key, not the calendar date -- see point 4 of the module docstring.

    S123(c): `incumbent` names which arm goes in that anchor slot -- "market" (the
    DEFAULT, byte-identical to every screen published before this option existed),
    "recal_null" (S94's walk-forward recalibration of the line) or "ladder_base"
    (`nba_mechanism_ladder` BASE). S92 measured market < recal_null < ladder_base by
    Brier on both NBA tick corpora, so the default already anchors on the strongest of
    the three; the option exists so a future screen can say which one it measured
    against instead of inheriting it. A fitted anchor is out-of-fold only, so the
    seed block's rows are dropped and the survivors re-blocked (see
    `ingame_incumbent_nba.apply_incumbent`).
    """
    frame = pd.read_csv(path, usecols=list(COLS))
    rows = pd.DataFrame({
        "row_id": np.arange(len(frame)),
        "game": frame["game_id"].astype(str),
        "ts": pd.to_datetime(frame["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ts_unix": frame["ts"].astype(float),
        "date": frame["game_date"].astype(str),
        "y": frame["y"].astype(float),
        "p_e4": frame["market"].astype(float),
        "market": frame["market"].astype(float),
        "model": frame["model"].astype(float),
        "informative": frame["informative"].astype(bool),
        "period": frame["period"].astype(int),
        "score_home": frame["score_home"].astype(float),
        "score_away": frame["score_away"].astype(float),
        "margin": frame["margin"].astype(float),
        "elapsed": frame["elapsed"].astype(float),
        "rem": frame["rem"].astype(float)})
    rows = rows.sort_values(["ts", "game"], kind="stable").reset_index(drop=True)
    rows["game_date"] = fold_blocks(rows, n_folds)
    if incumbent != "market":
        rows = apply_incumbent(rows, incumbent)
        rows["game_date"] = fold_blocks(rows, n_folds)
    return rows


def causal_source(rows: pd.DataFrame) -> pd.DataFrame:
    """The state columns the grammar builds from, with the NUMERIC tick stamp it decays on.

    Row order is the tier's own causal ordering (timestamp, then game), so a prefix of this
    frame is a prefix of real time and `assert_tick_asof` truncates something meaningful.
    """
    src = rows[["game", "period", "margin", "rem", "elapsed", "score_home", "score_away"]]
    return src.assign(ts=rows["ts_unix"].to_numpy())


def fold_blocks(rows: pd.DataFrame, n_folds: int = N_FOLDS) -> pd.Series:
    """Contiguous blocks of game-FIRST dates, roughly equal in ticks; every game in one.

    Returns the block key per row ("F0".."Fn"), which sorts in time order because the
    index is zero-padded -- `walk_forward_feature` orders its folds by sorting this value.
    """
    first = rows.groupby("game")["date"].min()
    per_day = rows["game"].map(first).value_counts().sort_index()
    days = list(per_day.index)
    edges = np.linspace(0, len(rows), n_folds + 2)[1:-1]
    cuts = np.searchsorted(per_day.to_numpy().cumsum(), edges)
    bounds = [0] + sorted({min(int(c) + 1, len(days)) for c in cuts}) + [len(days)]
    block_of_day: Dict[str, str] = {}
    index = 0
    for start, stop in zip(bounds[:-1], bounds[1:]):
        if stop <= start:
            continue
        for day in days[start:stop]:
            block_of_day[day] = "F%d" % index
        index += 1
    return rows["game"].map(first).map(block_of_day)


def _dm_fast(delta: np.ndarray, codes: np.ndarray, n_clusters: int) -> Tuple[float, float, list]:
    """`dm_test.diebold_mariano` restated with np.bincount; identical arithmetic.

    Cluster-sum variance with the (G/(G-1)) finite-cluster correction, Student-t with
    G-1 df for both the p-value and the interval half-width. Asserted equal to the
    reference implementation to 1e-12 by the per-file test.
    """
    n = len(delta)
    if n == 0 or float(np.abs(delta).max()) == 0.0:
        return 0.0, 1.0, [0.0, 0.0]
    if n_clusters < 2:
        raise ValueError("at least 2 clusters are required; got %d" % n_clusters)
    mean = float(delta.mean())
    sums = np.bincount(codes, weights=delta - mean, minlength=n_clusters)
    var = float(sums @ sums) / (n * n) * (n_clusters / (n_clusters - 1.0))
    se = float(np.sqrt(var)) if var > 0 else 0.0
    stat = mean / se if se > 0 else 0.0
    p = _student_t_two_tailed_pvalue(abs(stat), n_clusters - 1)
    crit = _student_t_two_tailed_quantile(0.05, n_clusters - 1)
    return float(stat), float(p), [mean - crit * se, mean + crit * se]


def score_fast(rows: pd.DataFrame, candidate: pd.Series, null: pd.Series,
               column: str) -> dict:
    """`ingame_screen.score_feature` with the vectorised DM; same keys, same arithmetic.

    The BAR is applied to `improvement_vs_null`, so the two arms differ ONLY by the
    feature term. `brier_e4` is the in-play market line on this corpus (see the module
    docstring), which is why it equals `brier_market` exactly.
    """
    keep = candidate.notna()
    sub = rows[keep]
    p_c, p_n = candidate[keep].to_numpy(dtype=float), null[keep].to_numpy(dtype=float)
    y = sub["y"].to_numpy(dtype=float)
    p_i, mkt = sub["p_e4"].to_numpy(dtype=float), sub["market"].to_numpy(dtype=float)
    loss_c, loss_n = (p_c - y) ** 2, (p_n - y) ** 2
    loss_i, loss_m = (p_i - y) ** 2, (mkt - y) ** 2
    codes, uniques = pd.factorize(sub["game"], sort=False)
    stat, p_raw, ci = _dm_fast(loss_n - loss_c, codes, len(uniques))
    improvement = float(loss_n.mean() - loss_c.mean())
    delta = pd.Series(loss_n - loss_c, index=sub.index)
    rho = _icc(delta.to_numpy(), codes, len(uniques))
    n_eff = len(sub) / max(1.0, 1.0 + (len(sub) / max(1, len(uniques)) - 1.0) * rho)
    return {"feature": column, "n_ticks": int(len(sub)), "n_games": int(len(uniques)),
            "n_informative": int(sub["informative"].sum()), "n_eff": float(n_eff),
            "brier_e4": float(loss_i.mean()), "brier_null_recal": float(loss_n.mean()),
            "brier_candidate": float(loss_c.mean()), "brier_market": float(loss_m.mean()),
            "improvement_vs_null": improvement, "bar": BAR, "dm_stat": stat,
            "dm_p_raw": p_raw, "dm_ci95": ci, "icc_game": float(rho),
            "improvement_vs_market": float(loss_m.mean() - loss_c.mean()),
            "clears_bar": bool(improvement >= BAR and ci[0] > 0.0),
            "feature_coverage": float(rows[column].notna().mean()), "_index": sub.index}


def _icc(values: np.ndarray, codes: np.ndarray, n_clusters: int) -> float:
    """One-way-ANOVA intraclass correlation of the paired-loss series, clustered by game."""
    counts = np.bincount(codes, minlength=n_clusters).astype(float)
    sums = np.bincount(codes, weights=values, minlength=n_clusters)
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    grand = float(values.mean())
    between = float(((means - grand) ** 2 * counts).sum()) / max(1, n_clusters - 1)
    within = float(((values - means[codes]) ** 2).sum()) / max(1, len(values) - n_clusters)
    mean_size = len(values) / max(1, n_clusters)
    denominator = between + (mean_size - 1.0) * within
    return 0.0 if denominator <= 0 else max(0.0, min(1.0, (between - within) / denominator))
def sweep(rows: pd.DataFrame, grid: pd.DataFrame, hypotheses: Sequence, db: Path,
          *, limit: int = 0, verbose: bool = True, allow_adhoc: bool = False) -> Dict[str, object]:
    """Screen every frozen hypothesis; one committed sqlite row each, so a kill is readable."""
    frozen = grammar.enumerate_hypotheses() + pair_grammar.enumerate_hypotheses()
    adhoc = set(gate_features([semantic_hash(h) for h in hypotheses],
                              map(semantic_hash, frozen), allow_adhoc))
    connection = sqlite3.connect(str(db))
    connection.executescript(SCHEMA)
    done = {row[0] for row in connection.execute("SELECT hypothesis_id FROM screen")}
    slim = rows[["game", "ts", "game_date", "y", "p_e4", "market", "informative"]]
    period = rows["period"]
    started, scored = time.time(), 0
    for position, hypothesis in enumerate(hypotheses):
        key = semantic_hash(hypothesis)
        if key in done or (limit and scored >= limit):
            continue
        label = grammar.hypothesis_label(hypothesis)
        phase = grammar.hypothesis_phase(hypothesis)
        column = grammar.hypothesis_column(hypothesis)
        values = grid[column]
        if phase:
            values = grammar.conditioned(values, period, phase)
        if key in adhoc:
            assert_column_blind(values, rows["y"], column)                  # S124
        tick = time.time()
        frame = slim.assign(**{column: values.to_numpy()})
        candidate, null, folds = walk_forward_feature(frame, column,
                                                      embargo_days=EMBARGO_DAYS)
        if not candidate.notna().any():
            record = {"status": "UNSCORED"}
        else:
            record = score_fast(frame, candidate, null, column)
            record.pop("_index")
            record["status"] = "SCREENED"
        connection.execute(
            "INSERT OR REPLACE INTO screen VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, label, hypothesis.feature, hypothesis.transform,
             json.dumps(list(hypothesis.params)), phase, record["status"],
             record.get("n_ticks"), record.get("n_games"), record.get("n_informative"),
             record.get("n_eff"), record.get("brier_market"), record.get("brier_null_recal"),
             record.get("brier_candidate"), record.get("improvement_vs_null"),
             record.get("dm_stat"), record.get("dm_p_raw"),
             (record.get("dm_ci95") or [None, None])[0],
             (record.get("dm_ci95") or [None, None])[1], record.get("feature_coverage"),
             int(bool(record.get("clears_bar"))), json.dumps(folds, default=str),
             time.time() - tick))
        connection.commit()
        scored += 1
        if verbose:
            print("[%4d/%4d] %-30s %-9s impr %s  %.1fs"
                  % (position + 1, len(hypotheses), label, record["status"],
                     ("%+.6f" % record["improvement_vs_null"]) if record["status"] == "SCREENED"
                     else "-", time.time() - tick), flush=True)
    elapsed = time.time() - started
    connection.close()
    return {"n_scored_this_run": scored, "seconds": elapsed,
            "screens_per_hour": (scored / elapsed * 3600.0) if elapsed > 0 else 0.0}


def write_meta(db: Path, rows: pd.DataFrame, hypotheses: Sequence, probes: List[int],
               extra: Optional[dict] = None) -> None:
    """Corpus, grammar and guard provenance beside the results, in the same DB."""
    summary = grammar.grid_summary()
    meta = {"tier": "in-game screen (S82) on the NBA tick corpus (S102)",
            "verdict": "SCREEN (a non-finding)", "sport": "nba", "bar": BAR,
            "embargo_days": EMBARGO_DAYS, "n_folds": N_FOLDS, "corpus": str(S86_CSV.name),
            "n_ticks": int(len(rows)), "n_games": int(rows["game"].nunique()),
            "n_informative": int(rows["informative"].sum()),
            "incumbent": str(rows["incumbent"].iloc[0]) if "incumbent" in rows else "market",
            "incumbent_options": json.dumps(list(INCUMBENTS)),
            "ts_min": str(rows["ts"].min()), "ts_max": str(rows["ts"].max()),
            "fold_blocks": json.dumps(rows.groupby("game_date").size().to_dict()),
            "n_hypotheses": len(hypotheses), "tick_asof_probes": json.dumps(probes),
            "brier_market_pooled": float(((rows["market"] - rows["y"]) ** 2).mean()),
            "brier_model_asof_pooled": float(((rows["model"] - rows["y"]) ** 2).mean()),
            "grammar": json.dumps(summary, sort_keys=True)}
    meta.update(extra or {})
    connection = sqlite3.connect(str(db))
    connection.executescript(SCHEMA)
    connection.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)",
                           [(k, str(v)) for k, v in sorted(meta.items())])
    connection.commit()
    connection.close()
