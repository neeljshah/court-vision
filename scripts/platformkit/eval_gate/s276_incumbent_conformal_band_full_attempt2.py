"""S294 full-source CPCV STATIC conformal coverage on frozen S86 blocks."""
from __future__ import annotations

import datetime as dt
import gc
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

try:
    import resource
except ImportError:  # pragma: no cover - the full route is pod-only
    resource = None

from scripts.platformkit.eval_gate import cpcv_engine
from scripts.platformkit.eval_gate import s265_incumbent_conformal_band_sample as s265
from scripts.platformkit.eval_gate import s86_nba_every_tick as s86
from scripts.platformkit.eval_gate import s94_nba_early_shrinkage as s94

REPO = Path(__file__).resolve().parents[3]
PREREG = REPO / "docs/evidence/harness/S294_preregistration_incumbent_conformal_full_s86_blocks_2026-09-04.md"
OUT_JSON = REPO / "docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.json"
PAIR_CSV = REPO / "docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_paired_loss_2026-09-04.csv.gz"
POD_LOG = REPO / "docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_pod_log_tail_2026-09-04.txt"
EXPECTED_TICKS, EXPECTED_GAMES = 465249, 1593
N_GROUPS, N_TEST_GROUPS, EMBARGO_DAYS = 6, 1, 1
DEFAULT_S101_TICKS = s265.S101_TICKS


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def s101_ticks() -> Path:
    """Return the additive S294 override, retaining the local default path."""
    return Path(os.environ.get("S294_S101_TICKS", str(DEFAULT_S101_TICKS)))


def _s101_path(path: Path) -> Path:
    """Retain S265's committed local reference when a pod scratch path is used."""
    class ExternalS101Path(type(Path())):
        def relative_to(self, *other: Path) -> Path:
            try:
                return super().relative_to(*other)
            except ValueError:
                return DEFAULT_S101_TICKS.relative_to(*other)
    return ExternalS101Path(path)


def prereg_seal() -> str:
    """Verify the LF-normalized preregistration seal from the checked-out file."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"SEAL_SHA256:", 1)
    value = hashlib.sha256(prefix).hexdigest()
    assert value == seal.strip().decode("ascii"), "S294 preregistration seal mismatch"
    return value


def _rss() -> int:
    assert resource is not None, "S294 full source route runs on the Linux pod"
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def s86_blocks(rows: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Freeze the exact six tick-balanced S86 date blocks from the landed routine."""
    blocks, date_to_block = [], {}
    for block_id, dates in enumerate(s94.fold_dates(rows)):
        part = rows[rows["date"].isin(set(dates))]
        assert not part.empty
        for day in dates:
            assert day not in date_to_block
            date_to_block[day] = block_id
        blocks.append({"block_id": block_id, "first_game_date": str(min(dates)),
                       "last_game_date": str(max(dates)), "n_ticks": int(len(part)),
                       "n_games": int(part["game"].nunique())})
    assert len(blocks) == N_GROUPS and sum(row["n_ticks"] for row in blocks) == EXPECTED_TICKS
    assert len(date_to_block) == rows["date"].nunique()
    return blocks, date_to_block


def _states(raw: pd.DataFrame, date_to_block: dict[str, int]) -> list[dict[str, Any]]:
    """Make one stable evaluator state per tick, labelled by its frozen S86 block."""
    rows = s265._rows(raw)
    rows = rows.join(s265.incumbent.ladder_base_columns(rows))
    teams = raw.groupby("game_id", sort=False)[["home", "away"]].first()
    teams.index = teams.index.astype(str)
    states = []
    for row in rows.itertuples(index=False):
        game = str(row.game)
        key = "%s|%d|%s" % (game, int(row.source_row), row.ts)
        available = pd.Timestamp(row.ts).isoformat()
        state_ts = (pd.Timestamp(row.ts) + pd.Timedelta(microseconds=1)).isoformat()
        features = {"state_key": key, "source_row": int(row.source_row), "market": float(row.market),
                    "margin": float(row.margin), "rem": float(row.rem), "cell": row.cell,
                    "logit_p0": float(row.logit_p0), "margin_s": float(row.margin_s), "z": float(row.z)}
        states.append({"game_id": game, "state_ts": state_ts, "home": str(teams.loc[game, "home"]),
                       "away": str(teams.loc[game, "away"]), "s86_block": date_to_block[str(row.date)],
                       "features": features, "feature_avail": {name: available for name in features},
                       "outcome": int(row.y)})
    assert len(states) == EXPECTED_TICKS
    assert len({state["features"]["state_key"] for state in states}) == len(states)
    return states


def _evaluate(states: list[dict[str, Any]]) -> pd.DataFrame:
    """Fit only from each shared evaluator path's purged train states."""
    models: dict[int, tuple[pd.Series, pd.Series, LogisticRegression]] = {}
    details: list[dict[str, Any]] = []

    def predict(train: list[dict], test: dict, _: bool) -> float:
        cache_key = int(test["s86_block"])
        if cache_key not in models:
            frame = pd.DataFrame([state["features"] for state in train])
            frame["outcome_home_win"] = [state["outcome"] for state in train]
            cols = s265.incumbent.LADDER_BASE_COLS
            mu, sd = frame[cols].mean(), frame[cols].std(ddof=0).replace(0.0, 1.0)
            model = LogisticRegression(C=1e6, max_iter=2000).fit(
                ((frame[cols] - mu) / sd).to_numpy(), frame["outcome_home_win"].to_numpy())
            models[cache_key] = (mu, sd, model)
        mu, sd, model = models[cache_key]
        features = test["features"]
        p = float(model.predict_proba(pd.DataFrame([features])[s265.incumbent.LADDER_BASE_COLS]
                                      .sub(mu).div(sd).to_numpy())[0, 1])
        details.append({"state_key": features["state_key"], "source_row": features["source_row"],
                        "game": test["game_id"], "date": test["state_ts"][:10],
                        "ts": features["state_key"].rsplit("|", 1)[1], "phase": features["cell"],
                        "period_bucket": features["cell"], "cell": features["cell"],
                        "market": features["market"], "p": p, "s86_block": test["s86_block"]})
        return p

    records = cpcv_engine.cpcv_evaluate(
        states, predict, n_groups=N_GROUPS, n_test_groups=N_TEST_GROUPS, embargo_days=EMBARGO_DAYS,
        strict_redaction=True, group_key="s86_block",
        allow_keys=("state_key", "source_row", "market", "margin", "rem", "cell", "logit_p0", "margin_s", "z", "s86_block"))
    assert len(records) == len(states) == len(details)
    out = pd.DataFrame(details)
    out["split_id"] = [record["split_id"] for record in records]
    out["n_train"] = [record["n_train"] for record in records]
    out["y"] = [record["y"] for record in records]
    out["p_evaluator"] = [record["p_model"] for record in records]
    assert np.allclose(out["p"], out["p_evaluator"])
    assert out["state_key"].nunique() == len(out) and out["game"].nunique() == EXPECTED_GAMES
    assert out.groupby("split_id")["s86_block"].nunique().eq(1).all()
    assert set(out.groupby("split_id")["s86_block"].first()) == set(range(N_GROUPS))
    return out


def _static(evaluated: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fit STATIC bands only from OOS evaluator records and archive grouped units."""
    static, groups = {}, []
    for nominal in s265.s101.NOMINALS:
        held = []
        for split_id in sorted(evaluated["split_id"].unique()):
            train = evaluated[evaluated["split_id"] != split_id]
            test = evaluated[evaluated["split_id"] == split_id]
            scored, _ = s265.s101.run_fold(train.rename(columns={"p": "p_incumbent"}),
                                            test.rename(columns={"p": "p_incumbent"}),
                                            "p_incumbent", round(1.0 - nominal, 10))
            scored["split_id"] = split_id
            held.append(scored)
        ticks = pd.concat(held, ignore_index=True)
        assert len(ticks) == EXPECTED_TICKS and ticks["game"].nunique() == EXPECTED_GAMES
        cells = s265.s101.score(ticks, nominal)["static"]
        for cell in s265.PHASES:
            cells[cell]["mean_interval_half_width"] = None if cells[cell]["coverage"] is None else float(cells[cell]["mean_interval_width"]) / 2.0
        static["%.2f" % nominal] = {"n_scored_ticks": int(len(ticks)),
                                     "n_scored_games": int(ticks["game"].nunique()), "cells": cells}
        groups.extend(s265._archive_groups(ticks, nominal, cells))
    return static, groups


def _s101_regression(ticks_path: Path) -> dict[str, Any]:
    """Replay S101 through its landed S265 callback using the additive input path."""
    previous = s265.S101_TICKS
    s265.S101_TICKS = _s101_path(ticks_path)
    try:
        return s265._s101_regression()
    finally:
        s265.S101_TICKS = previous


def run() -> dict[str, Any]:
    """Score every full-source tick once and write only new S294 evidence."""
    ticks_path = s101_ticks()
    assert ticks_path.exists(), "S294 S101 ticks input is absent: %s" % ticks_path
    raw = s86.load_ticks(s86.CHECKPOINTS)
    loaded = {"n_ticks": int(len(raw)), "n_games": int(raw.game_id.nunique())}
    assert loaded == {"n_ticks": EXPECTED_TICKS, "n_games": EXPECTED_GAMES}
    rows = s265._rows(raw)
    blocks, date_to_block = s86_blocks(rows)
    evaluated = _evaluate(_states(raw, date_to_block))
    del raw, rows
    gc.collect()
    static, groups = _static(evaluated)
    pairs = evaluated.assign(record_type="paired_loss", incumbent_brier=(evaluated.p - evaluated.y) ** 2,
                             market_brier=(evaluated.market - evaluated.y) ** 2)
    archive = pd.concat([pairs, pd.DataFrame(groups)], ignore_index=True, sort=False)
    temporary = PAIR_CSV.with_suffix("")
    archive.to_csv(temporary, index=False, encoding="ascii")
    with temporary.open("rb") as source, PAIR_CSV.open("wb") as destination:
        with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as zipped:
            shutil.copyfileobj(source, zipped)
    temporary.unlink()
    regression = _s101_regression(ticks_path)
    assert regression["passes"]
    report = {"row": "S294", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "prereg": {"path": str(PREREG.relative_to(REPO)), "seal_sha256": prereg_seal()},
              "source": {"path": str(s86.CHECKPOINTS.relative_to(REPO)), "loaded": loaded},
              "s101_ticks_input": {"local_reference": str(DEFAULT_S101_TICKS.relative_to(REPO)),
                                    "used_path": str(ticks_path), "bytes": ticks_path.stat().st_size,
                                    "md5": _md5(ticks_path)},
              "census": {"ticks_loaded": EXPECTED_TICKS, "ticks_scorable": EXPECTED_TICKS,
                         "ticks_scored": EXPECTED_TICKS, "games_loaded": EXPECTED_GAMES,
                         "games_scorable": EXPECTED_GAMES, "games_scored": EXPECTED_GAMES,
                         "excluded_by_reason": {}},
              "design": {"engine": "cpcv_evaluate", "n_groups": N_GROUPS, "n_test_groups": N_TEST_GROUPS,
                         "group_source": "s94_nba_early_shrinkage.fold_dates", "blocks": blocks,
                         "purge": "game-disjoint", "symmetric_embargo_days": EMBARGO_DAYS,
                         "coverage_min_group": s265.s101.COVERAGE_MIN_GROUP,
                         "coverage_max_groups": s265.s101.COVERAGE_MAX_GROUPS},
              "static": static, "pod_rss": {"peak_bytes": _rss()}, "s101_regression": regression,
              "paired_loss_series": {"path": str(PAIR_CSV.relative_to(REPO)), "sha256": _hash(PAIR_CSV)},
              "code_identity": {"s276_attempt2": _hash(Path(__file__)), "cpcv_engine": _hash(Path(cpcv_engine.__file__)),
                                "s265": _hash(Path(s265.__file__)), "s86": _hash(Path(s86.__file__)),
                                "s94": _hash(Path(s94.__file__)), "s101": _hash(Path(s265.s101.__file__)),
                                "s123": _hash(Path(s265.incumbent.__file__)), "aci_online": _hash(Path(s265.aci_online.__file__))}}
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    return report


def main() -> int:
    report = run()
    lines = ["CENSUS ticks_loaded=%d ticks_scorable=%d ticks_scored=%d games_loaded=%d games_scorable=%d games_scored=%d excluded=%s" % tuple(report["census"].values())]
    for block in report["design"]["blocks"]:
        lines.append("BLOCK %(block_id)d first=%(first_game_date)s last=%(last_game_date)s n_ticks=%(n_ticks)d n_games=%(n_games)d" % block)
    for nominal, result in report["static"].items():
        for cell, value in result["cells"].items():
            lines.append("STATIC nominal=%s cell=%s n=%s coverage=%s half_width=%s absent=%s" % (nominal, cell, value["n"], value["coverage"], value.get("mean_interval_half_width"), value.get("absent_because")))
    lines.append("S101_24_CELL_MAX_ABS_COVERAGE_DIFF=%s" % report["s101_regression"]["max_abs_coverage_diff"])
    input_meta = report["s101_ticks_input"]
    lines.append("S101_TICKS_MD5 local_reference=%s used_path=%s bytes=%d md5=%s" %
                 (input_meta["local_reference"], input_meta["used_path"], input_meta["bytes"], input_meta["md5"]))
    lines.append("POD_PEAK_RSS_BYTES=%d" % report["pod_rss"]["peak_bytes"])
    POD_LOG.write_text("\n".join(lines) + "\n", encoding="ascii")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
