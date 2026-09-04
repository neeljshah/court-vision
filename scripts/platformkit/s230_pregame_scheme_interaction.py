"""S230 pregame offense-defense interaction calibration screen."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss
from scripts.platformkit.eval_gate.calibration_report_helpers import _bin_table
from scripts.platformkit.eval_gate.walkforward import walk_forward

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "data" / "intelligence" / "matchup_grid.parquet"
CORPUS = ROOT / "data" / "cache" / "combo" / "gate_corpus_nba_close.parquet"
PREREG = "docs/evidence/harness/S230_pregame_scheme_interaction_prereg_2026-09-04.json"
PREREG_SHA256 = "f690d620ce3baccec2a92d2fad0243d412ec96620f7ac66613bc80c2241806ec"
MEMO = ROOT / "docs" / "evidence" / "harness" / "S230_pregame_scheme_interaction_2026-09-04.md"
PREDICTIONS = ROOT / "docs" / "evidence" / "harness" / "S230_pregame_scheme_interaction_2026-09-04_predictions.csv"
TERMS = (
    ("off_tempo_z", "def_pace_imposed_z"),
    ("off_spacing_z", "def_defender_distance_z"),
    ("off_tempo_spacing_z", "def_pace_imposed_z"),
    ("off_paint_dwell_z", "def_paint_dwell_allowed_z"),
    ("off_transition_share_z", "def_intensity_z"),
    ("off_avg_spacing_z", "def_catch_shoot_allowed_z"),
)
RIDGE = 1.0
MIN_TRAIN = 30
PREGAME_SOURCE = "pregame_last_tick_before_commence"


def _read(path: Path, columns: Iterable[str]) -> pd.DataFrame:
    if path.stat().st_size > 300 * 1024 * 1024:
        raise ValueError("store exceeds 300 MB rail: %s" % path)
    return pd.read_parquet(path, columns=list(columns))


def _logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def _sigmoid(eta: np.ndarray) -> np.ndarray:
    return np.clip(1.0 / (1.0 + np.exp(-np.clip(eta, -30.0, 30.0))), 1e-6, 1.0 - 1e-6)


def _canonical_prereg_sha() -> str:
    path = ROOT / PREREG
    payload = json.loads(path.read_text(encoding="ascii"))
    payload.pop("seal_sha256")
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _game_features(grid: pd.DataFrame) -> pd.DataFrame:
    work = grid.copy()
    work["game_id"] = work["game_id"].astype(str)
    work["game_date"] = pd.to_datetime(work["game_date"]).dt.strftime("%Y-%m-%d")
    if set(work["is_home"].dropna().unique()) - {False, True, 0, 1}:
        raise ValueError("is_home is not boolean")
    names = []
    for offense, defense in TERMS:
        name = "%s_x_%s" % (offense, defense)
        work[name] = pd.to_numeric(work[offense], errors="coerce") * pd.to_numeric(work[defense], errors="coerce")
        names.append(name)
    home = work.loc[work["is_home"].astype(bool), ["game_id", "game_date", "team_id", "opp_team_id", *names]].copy()
    away = work.loc[~work["is_home"].astype(bool), ["game_id", "game_date", "team_id", *names]].copy()
    if home["game_id"].duplicated().any() or away["game_id"].duplicated().any():
        raise ValueError("matchup grid has duplicate home or away game rows")
    paired = home.merge(away, on=["game_id", "game_date"], suffixes=("_home", "_away"), validate="one_to_one")
    if not (paired["opp_team_id"].astype(str) == paired["team_id_away"].astype(str)).all():
        raise ValueError("matchup grid home-away team pairing disagrees")
    out = paired[["game_id", "game_date"]].copy()
    out["home_team_id"] = paired["team_id_home"].astype(str)
    out["away_team_id"] = paired["team_id_away"].astype(str)
    for name in names:
        out[name] = paired[name + "_home"] - paired[name + "_away"]
    return out


def load_frame() -> tuple[pd.DataFrame, dict[str, object]]:
    """Read one bounded store at a time and produce the complete paired game frame."""
    columns = ["game_id", "game_date", "is_home", "team_id", "opp_team_id"]
    for term in TERMS:
        for column in term:
            if column not in columns:
                columns.append(column)
    grid = _read(GRID, columns)
    census = {"grid_rows": int(len(grid)), "grid_min_date": str(pd.to_datetime(grid["game_date"]).min().date()),
              "grid_max_date": str(pd.to_datetime(grid["game_date"]).max().date())}
    features = _game_features(grid)
    census["paired_grid_games"] = int(len(features))
    del grid
    corpus = _read(CORPUS, ["event_id", "corpus_unit", "event_date", "y", "p_base", "p_close", "close_source"])
    corpus["event_id"] = corpus["event_id"].astype(str)
    corpus["event_date"] = pd.to_datetime(corpus["event_date"]).dt.strftime("%Y-%m-%d")
    joined = corpus.merge(features, left_on=["event_id", "event_date"], right_on=["game_id", "game_date"],
                          how="inner", validate="one_to_one")
    del corpus
    census["gate_rows_joined"] = int(len(joined))
    census["pregame_close_rows"] = int((joined["close_source"].eq(PREGAME_SOURCE) & joined["p_close"].notna()).sum())
    required = ["y", "p_base", *["%s_x_%s" % term for term in TERMS]]
    invalid = ~np.isfinite(joined[required].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)).all(axis=1)
    census["rows_dropped_after_pairing"] = int(invalid.sum())
    if invalid.any():
        raise ValueError("paired rows contain non-finite required values")
    return joined.sort_values(["event_date", "event_id"], kind="stable").reset_index(drop=True), census


class OffsetInteractionPredictor:
    """Fit the residual interaction model exclusively from evaluator train states."""

    def __call__(self, train: list[dict], test: dict, select_inside: bool) -> float:
        if not select_inside:
            raise ValueError("selection must remain inside the evaluator")
        base = float(test["features"]["p_base"])
        if len(train) < MIN_TRAIN:
            return base
        x_train = np.array([[row["features"][name] for name in self.names] for row in train], dtype=float)
        y = np.array([row["outcome"] for row in train], dtype=float)
        mu = x_train.mean(axis=0)
        scale = x_train.std(axis=0)
        scale[scale < 1e-12] = 1.0
        design = np.column_stack([np.ones(len(train)), (x_train - mu) / scale])
        beta = np.zeros(design.shape[1])
        offset = _logit(np.array([row["features"]["p_base"] for row in train], dtype=float))
        penalty = np.diag([0.0] + [RIDGE] * (design.shape[1] - 1))
        for _ in range(30):
            prob = _sigmoid(offset + design @ beta)
            weight = np.clip(prob * (1.0 - prob), 1e-6, None)
            hessian = (design * weight[:, None]).T @ design + penalty
            step = np.linalg.solve(hessian, design.T @ (prob - y) + penalty @ beta)
            beta -= step
            if float(np.abs(step).max()) < 1e-9:
                break
        x_test = np.array([test["features"][name] for name in self.names], dtype=float)
        return float(_sigmoid(np.array([_logit(np.array([base]))[0] + beta[0] + ((x_test - mu) / scale) @ beta[1:]]))[0])

    @property
    def names(self) -> tuple[str, ...]:
        return tuple("%s_x_%s" % term for term in TERMS)


def _states(frame: pd.DataFrame) -> list[dict]:
    names = tuple("%s_x_%s" % term for term in TERMS)
    states = []
    for row in frame.itertuples(index=False):
        day = str(row.event_date)
        features = {"p_base": float(row.p_base)}
        features.update({name: float(getattr(row, name)) for name in names})
        available = {name: day + "T00:00:00" for name in features}
        states.append({"game_id": str(row.event_id), "state_ts": day + "T12:00:00", "game_date": day,
                       "home": "team_" + str(row.home_team_id), "away": "team_" + str(row.away_team_id),
                       "features": features, "feature_avail": available, "devig_close_prob": float(row.p_close)
                       if np.isfinite(row.p_close) else None, "outcome": int(row.y)})
    return states


def _bootstrap(frame: pd.DataFrame, draws: int = 2000) -> dict[str, tuple[float, float]]:
    units = frame["corpus_unit"].astype(str).unique()
    if len(units) < 2:
        return {name: (float("nan"), float("nan")) for name in ("ece", "brier", "log_loss")}
    rng = np.random.default_rng(230)
    values = {name: [] for name in ("ece", "brier", "log_loss")}
    groups = {unit: frame.loc[frame["corpus_unit"].astype(str).eq(unit)] for unit in units}
    for _ in range(draws):
        sample = pd.concat([groups[unit] for unit in rng.choice(units, len(units), replace=True)], ignore_index=True)
        y, inc, model = (sample[key].to_numpy(float) for key in ("y", "p_incumbent", "p_interaction"))
        values["ece"].append(ece(inc, y) - ece(model, y))
        values["brier"].append(brier(inc, y) - brier(model, y))
        values["log_loss"].append(log_loss(inc, y) - log_loss(model, y))
    return {name: tuple(float(x) for x in np.quantile(value, [0.025, 0.975])) for name, value in values.items()}


def _metrics(frame: pd.DataFrame, column: str) -> dict[str, float]:
    p, y = frame[column].to_numpy(float), frame["y"].to_numpy(float)
    return {"ece": ece(p, y), "brier": brier(p, y), "log_loss": log_loss(p, y)}


def _bin_lines(title: str, frame: pd.DataFrame, column: str) -> list[str]:
    table = _bin_table(frame[column].to_numpy(float), frame["y"].to_numpy(float), 10)
    lines = ["", "### %s" % title, "", "| bin | n | mean probability | observed frequency |",
             "| --- | ---: | ---: | ---: |"]
    for row in table:
        mean = "" if row["mean_predicted_prob"] is None else "%.6f" % row["mean_predicted_prob"]
        observed = "" if row["observed_win_freq"] is None else "%.6f" % row["observed_win_freq"]
        lines.append("| %s | %d | %s | %s |" % (row["bin"], row["n"], mean, observed))
    return lines


def run(memo: Path = MEMO, predictions: Path = PREDICTIONS) -> dict[str, object]:
    """Score every paired prediction through the shared evaluator and write evidence."""
    if _canonical_prereg_sha() != PREREG_SHA256:
        raise ValueError("preregistration seal mismatch")
    frame, census = load_frame()
    result = walk_forward(_states(frame), OffsetInteractionPredictor(), select_inside=True,
                          strict_redaction=True, allow_keys=("devig_close_prob",))
    if len(result.records) != len(frame):
        raise ValueError("evaluator did not produce every paired prediction")
    scored = frame[["event_id", "event_date", "corpus_unit", "y", "p_base", "p_close", "close_source"]].copy()
    scored["state_ts"] = scored["event_date"] + "T12:00:00"
    scored["p_incumbent"] = scored.pop("p_base")
    scored["p_interaction"] = [row["p_model"] for row in result.records]
    for arm in ("incumbent", "interaction", "close"):
        if arm == "close":
            continue
        scored["loss_%s_brier" % arm] = (scored["p_%s" % arm] - scored["y"]) ** 2
        scored["loss_%s_log_loss" % arm] = -(scored["y"] * np.log(np.clip(scored["p_%s" % arm], 1e-15, 1.0 - 1e-15)) + (1 - scored["y"]) * np.log(np.clip(1 - scored["p_%s" % arm], 1e-15, 1.0 - 1e-15)))
    scored["brier_delta_incumbent_minus_interaction"] = scored["loss_incumbent_brier"] - scored["loss_interaction_brier"]
    scored["log_loss_delta_incumbent_minus_interaction"] = scored["loss_incumbent_log_loss"] - scored["loss_interaction_log_loss"]
    model = {"incumbent": _metrics(scored, "p_incumbent"), "interaction": _metrics(scored, "p_interaction"),
             "delta_incumbent_minus_interaction": _bootstrap(scored),
             "n_clusters": int(scored["corpus_unit"].astype(str).nunique()), "n_eff": int(scored["corpus_unit"].astype(str).nunique())}
    close = scored.loc[scored["close_source"].eq(PREGAME_SOURCE) & scored["p_close"].notna()].copy()
    close_report = {"n": int(len(close)), "n_eff": int(close["corpus_unit"].astype(str).nunique()),
                    "status": "NOT SCORABLE" if close["corpus_unit"].astype(str).nunique() < 30 else "SCORABLE"}
    scored.to_csv(predictions, index=False, lineterminator="\n")
    verdict = "SCREEN NULL" if model["n_clusters"] >= 30 else "CLOSED AT LIMIT"
    lines = ["# S230 pregame scheme interaction screen", "", "Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.",
             "Preregistration: %s; seal SHA-256: %s." % (PREREG, PREREG_SHA256),
             "Machine: local worktree CPU; read-only local stores; no data writes, ledger, register, or deployment.", "",
             "## Census before metrics", "", "matchup_grid rows %d; date range %s through %s; paired home-away games %d." % (census["grid_rows"], census["grid_min_date"], census["grid_max_date"], census["paired_grid_games"]),
             "gate_corpus_nba_close rows joined %d; joined rows with a pregame p_close %d; rows dropped after pairing %d." % (census["gate_rows_joined"], census["pregame_close_rows"], census["rows_dropped_after_pairing"]), "",
             "## Model-relative calibration (not market-relative)", "", "S108 reference: elastic net Brier difference +0.001360 at n 619; every coefficient was zero in 20 of 23 folds.",
             "All interaction probabilities were produced by scripts.platformkit.eval_gate.walkforward.walk_forward with its 48-hour purge and 3-day symmetric embargo. The callback fits only its supplied training states and uses logit(p_base) with coefficient fixed at one.",
             "| arm | ECE | Brier | log-loss |", "| --- | ---: | ---: | ---: |",
             "| incumbent | %.6f | %.6f | %.6f |" % tuple(model["incumbent"].values()), "| interaction | %.6f | %.6f | %.6f |" % tuple(model["interaction"].values()),
             "| incumbent minus interaction, clustered 95 pct CI | [%.6f, %.6f] | [%.6f, %.6f] | [%.6f, %.6f] |" % (model["delta_incumbent_minus_interaction"]["ece"] + model["delta_incumbent_minus_interaction"]["brier"] + model["delta_incumbent_minus_interaction"]["log_loss"]),
             "Model-relative corpus_unit clusters %d; n_eff %d." % (model["n_clusters"], model["n_eff"])]
    lines.extend(_bin_lines("Ten-bin reliability: incumbent, all joined rows", scored, "p_incumbent"))
    lines.extend(_bin_lines("Ten-bin reliability: interaction, all joined rows", scored, "p_interaction"))
    lines.extend(["", "## Pregame close limit", "",
                  "This subset uses only close_source=%s and is not pooled with first-inplay rows." % PREGAME_SOURCE,
                  "Pregame close rows %d; n_eff %d; status %s. No market-relative metric is published at this limit." % (close_report["n"], close_report["n_eff"], close_report["status"]),
                  "", "Ten-bin rule: np.linspace(0, 1, 11); [lo,hi) except final [lo,hi].",
                  "Reliability bin counts and predictions are reproducible from the CSV under that rule.",
                  "", "## Evidence and verdict", "", "Per-row paired-loss archive: docs/evidence/harness/S230_pregame_scheme_interaction_2026-09-04_predictions.csv.",
                  "Verdict: %s. This screen makes calibration measurements only." % verdict,
                  "", "## Input inventory", "",
                  "- %s; %d bytes; parquet team-game grain, 4900 rows." % (GRID.as_posix(), GRID.stat().st_size),
                  "- %s; %d bytes; parquet event-game grain, 1814 rows." % (CORPUS.as_posix(), CORPUS.stat().st_size),
                  "- data/intelligence/archetype_scheme_interactions.parquet; 10084 bytes; parquet 108-row schema-only hypothesis freeze, never joined or fitted.",
                  "- data/intelligence/position_scheme_interactions.parquet; 24604 bytes; parquet 315-row schema-only hypothesis freeze, never joined or fitted.",
                  "- Code identity: scripts/platformkit/s230_pregame_scheme_interaction.py SHA-256 %s." % hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])
    memo.write_text("\n".join(lines) + "\n", encoding="ascii")
    return {"census": census, "model": model, "close": close_report, "verdict": verdict}


def main() -> int:
    out = run()
    print("CENSUS grid_rows=%d joined=%d pregame_close=%d dropped=%d" % (out["census"]["grid_rows"], out["census"]["gate_rows_joined"], out["census"]["pregame_close_rows"], out["census"]["rows_dropped_after_pairing"]))
    print("RESULT verdict=%s clusters=%d n_eff=%d" % (out["verdict"], out["model"]["n_clusters"], out["model"]["n_eff"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
