"""S254 sealed, purged CPCV recalibration family measurement (calibration only)."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pandas as pd

from scripts.platformkit import hedge_trial_arms as arms
from scripts.platformkit.cpcv import cpcv_splits
from scripts.platformkit.eval_gate.cpcv_engine import _blocked_indices, _purged, cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
from scripts.platformkit.ingame import bucket_recalibration as recal
from scripts.platformkit.ingame.ingame_id_resolver_mlb import KALSHI_ABBR
from scripts.platformkit.ingame.ingame_outcome_label import _KALSHI_TO_ESPN, parse_mlb_ticker
from scripts.platformkit.ingame import s88_phase_recal as s88
from scripts.platformkit.ingame import state_bucket_benchmark as buckets
from scripts.platformkit.ingame_replay_scoreboard import discover_store

ROOT = Path(__file__).resolve().parents[3]
PREREG = ROOT / "docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_PREREG_attempt2.md"
OUT = ROOT / "docs/evidence/harness"
PAIR_PATH = OUT / "S254_mlb_phase_recal_fwer_sealed_2026-09-04_paired_loss_attempt2.csv"
SUMMARY_PATH = OUT / "S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary_attempt2.json"
MEMO_PATH = OUT / "S254_mlb_phase_recal_fwer_sealed_2026-09-04_attempt2.md"
Q, EMBARGO_DAYS = 0.05, 1
FAMILY = ("early|leading", "early|leading_big", "early|tied", "early|trailing", "early|trailing_big",
          "late|leading", "late|leading_big", "late|tied", "late|trailing", "late|trailing_big",
          "mid|leading", "mid|leading_big", "mid|tied", "mid|trailing", "mid|trailing_big")
TEAM_ABBRS = frozenset(KALSHI_ABBR.values()).union(_KALSHI_TO_ESPN.values())


def _stamp(value: str) -> datetime:
    text = str(value).replace("Z", "+00:00")
    if "." in text and "+" in text[10:]:
        head, tail = text.split(".", 1)
        fraction, offset = tail.split("+", 1)
        text = "%s.%s+%s" % (head, fraction[:6], offset)
    return datetime.fromisoformat(text)


def _teams(game_id: str) -> tuple[str, str]:
    """Canonical variable-width MLB identities via ingame_outcome_label.parse_mlb_ticker."""
    parsed = parse_mlb_ticker(game_id, TEAM_ABBRS)
    if parsed is None:
        raise ValueError("unresolved canonical MLB teams for %s" % game_id)
    _, away, home, _ = parsed
    return tuple(sorted((away, home)))


def prereg_identity(path: Path = PREREG) -> dict:
    raw = path.read_bytes()
    marker = b"seal_sha256: "
    assert b"\r\n" not in raw and raw.count(marker) == 1, "prereg must use one LF seal line"
    head, seal_line = raw.split(marker, 1)
    seal = seal_line.splitlines()[0].decode("ascii")
    got = hashlib.sha256(head).hexdigest()
    assert got == seal, "prereg seal mismatch"
    sealed = next(line.split(": ", 1)[1] for line in raw.decode("ascii").splitlines()
                  if line.startswith("sealed_at_utc: "))
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": seal,
            "header_lines": head.count(b"\n"), "sealed_at_utc": sealed}


def states(records: Sequence[Dict[str, Any]]) -> List[dict]:
    """One evaluator state per S06 tick; all test probabilities come from its callback."""
    out = []
    for row_id, row in enumerate(records):
        ts = _stamp(row["ts"])
        home, away = _teams(row["game_id"])
        features = {"row_id": row_id, "model_prob": float(row["model_prob"]),
                    "phase": row["phase"], "margin": float(row["margin"])}
        available = (ts - timedelta(microseconds=1)).isoformat()
        out.append({"game_id": row["game_id"], "state_ts": ts.isoformat(), "home": home, "away": away,
                    "features": features, "feature_avail": {key: available for key in features},
                    "outcome": int(row["outcome"])})
    return out


def callback_predictions(source_states: List[dict]) -> tuple[Dict[int, float], List[dict]]:
    """Run CPCV once; the callback fits only its received purged train rows."""
    cache: Dict[int, tuple[List[dict], Any]] = {}
    predicted: Dict[int, float] = {}
    fit_fn, apply_fn = recal.SPECS["phase_platt"]

    def predict(train: List[dict], test: dict, _: bool) -> float:
        key = id(train)
        if key not in cache:
            train_rows = [{"model_prob": s["features"]["model_prob"], "phase": s["features"]["phase"],
                           "margin": s["features"]["margin"], "outcome": s["outcome"]} for s in train]
            cache[key] = (train, fit_fn(train_rows))
        row = {"model_prob": test["features"]["model_prob"], "phase": test["features"]["phase"],
               "margin": test["features"]["margin"]}
        probability = float(apply_fn(row, cache[key][1]))
        predicted[int(test["features"]["row_id"])] = probability
        return probability

    evaluated = cpcv_evaluate(source_states, predict, n_groups=8, n_test_groups=1,
                               embargo_days=EMBARGO_DAYS, strict_redaction=True,
                               allow_keys=("row_id", "model_prob", "phase", "margin"))
    assert len(predicted) == len(source_states) == len(evaluated), "CPCV callback coverage failed"
    return predicted, evaluated


def purge_log(source_states: List[dict], evaluated: List[dict]) -> List[dict]:
    """Name every game cluster removed from a split's train set and the policy reason."""
    ordered = sorted(source_states, key=lambda s: s["state_ts"])
    stamps = [_stamp(s["state_ts"]) for s in ordered]
    route_counts = {split: {row["n_train"] for row in evaluated if row["split_id"] == split}
                    for split in range(8)}
    logs = []
    for split_id, (train_idx, test_idx) in enumerate(cpcv_splits([s["state_ts"] for s in ordered], 8, 1, 0)):
        blocked = _blocked_indices(ordered, stamps, test_idx, EMBARGO_DAYS)
        test_dates = {stamps[i].date() for i in test_idx}
        reasons: Dict[str, set[str]] = defaultdict(set)
        for index in set(train_idx).intersection(blocked):
            state, ts = ordered[index], stamps[index]
            if any(abs((ts.date() - day).days) <= EMBARGO_DAYS for day in test_dates):
                reasons[state["game_id"]].add("calendar_day_embargo")
            else:
                for test_index in test_idx:
                    test, test_ts = ordered[test_index], stamps[test_index]
                    if _purged(state, ts, test, test_ts, EMBARGO_DAYS):
                        reason = "same_matchup_embargo" if {state["home"], state["away"]} == {test["home"], test["away"]} else "same_team_purge"
                        reasons[state["game_id"]].add(reason)
                        break
        assert blocked and reasons and len(route_counts[split_id]) == 1, "nonempty symmetric purge audit required"
        evaluated_n_train = route_counts[split_id].pop()
        audit_n_train = len([i for i in train_idx if i not in blocked])
        assert audit_n_train == evaluated_n_train, "split %d n_train mismatch" % split_id
        print("S254 split=%d audit_n_train=%d evaluated_n_train=%d" % (split_id, audit_n_train, evaluated_n_train))
        logs.append({"split_id": split_id, "n_test_ticks": len(test_idx), "n_train_before": len(train_idx),
                     "n_train_after": audit_n_train, "evaluated_n_train": evaluated_n_train,
                     "excluded_game_clusters": [{"game_id": gid, "reasons": sorted(value)}
                                                 for gid, value in sorted(reasons.items())]})
    return logs


def _score(frame: pd.DataFrame) -> dict:
    delta = frame["incumbent_loss"] - frame["candidate_loss"]
    game_delta = delta.groupby(frame["game_id"], sort=True).mean()
    dm = diebold_mariano(game_delta.tolist(), game_delta.index.tolist())
    ci = buckets._cluster_bootstrap_ci(game_delta.tolist())
    return {"n_ticks": int(len(frame)), "n_game_clusters": int(frame["game_id"].nunique()),
            "brier_incumbent": float(frame["incumbent_loss"].mean()), "brier_candidate": float(frame["candidate_loss"].mean()),
            "delta": float(game_delta.mean()), "ci95": [float(ci[0]), float(ci[1])], "raw_p": float(dm.p_value)}


def _bh(rows: List[dict]) -> None:
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["raw_p"], rows[i]["bucket"]))
    passed, m = 0, len(rows)
    for rank, index in enumerate(order, 1):
        rows[index]["bh_rank"], rows[index]["bh_threshold"] = rank, rank * Q / m
        if rows[index]["raw_p"] <= rows[index]["bh_threshold"]:
            passed = rank
    running = 1.0
    for rank in range(m, 0, -1):
        index = order[rank - 1]
        running = min(running, rows[index]["raw_p"] * m / rank)
        rows[index]["bh_p"], rows[index]["bh_survivor"] = running, rank <= passed


def _replication_side(game_id: str) -> str:
    value = hashlib.sha256(("S254-replication-v1:" + game_id).encode("ascii")).digest()[0]
    return "primary" if value % 2 == 0 else "replication"


def summarize(frame: pd.DataFrame, prereg: dict, purge: List[dict], first_score: str, store: Path) -> dict:
    informative, info = flag_ticks(frame, game_col="game_id", ts_col="ts", market_col="market_prob", model_col="model_prob")
    scored = informative[informative["is_informative"].astype(bool)].copy()
    assert set(scored["phase_bucket"].unique()) == set(FAMILY), "family definition drift"
    scored["replication_side"] = scored["game_id"].map(_replication_side)
    rows = []
    for bucket in FAMILY:
        full, replica = scored[scored["phase_bucket"] == bucket], scored[(scored["phase_bucket"] == bucket) & (scored["replication_side"] == "replication")]
        row = dict(_score(full), bucket=bucket, replication=_score(replica))
        row["raw_label"] = recal._verdict(tuple(row["ci95"]), row["n_game_clusters"], buckets.MIN_GAMES, buckets.EPS_BRIER, "IMPROVED", "WORSE")
        rows.append(row)
    _bh(rows)
    for row in rows:
        ci, raw = row["replication"]["ci95"], row["raw_label"]
        row["label_after_bh"] = raw if row["bh_survivor"] else "NO_CHANGE"
        row["replication_label"] = "REPLICATED" if row["bh_survivor"] and ((raw == "IMPROVED" and ci[0] > buckets.EPS_BRIER) or (raw == "WORSE" and ci[1] < -buckets.EPS_BRIER)) else "NOT_REPLICATED"
    split_sets = scored.groupby("game_id")["replication_side"].nunique()
    game_sides = scored.groupby("game_id")["replication_side"].first()
    side_counts = game_sides.value_counts().to_dict()
    assert int(split_sets.max()) == 1 and side_counts == {"primary": 83, "replication": 75}
    assert EMBARGO_DAYS > 0 and _stamp(prereg["sealed_at_utc"]) < _stamp(first_score)
    files = list(store.rglob("*.jsonl"))
    return {"s254": "mlb_phase_recal_fwer_sealed", "prereg": prereg, "first_score_at_utc": first_score,
            "source": {"path": str(store), "file_count": len(files), "bytes": sum(p.stat().st_size for p in files)},
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "q": Q, "family": list(FAMILY),
            "denominator": {"n_eval_ticks": int(len(frame)), "n_informative_ticks": int(info["n_informative"]),
                            "n_informative_game_clusters": int(scored["game_id"].nunique()),
                            "primary_game_clusters": int(side_counts["primary"]),
                            "replication_game_clusters": int(side_counts["replication"])},
            "purge": {"embargo_days": EMBARGO_DAYS, "symmetric": True, "splits": purge}, "buckets": rows,
            "bh_survivors": [r["bucket"] for r in rows if r["bh_survivor"]],
            "not_verified": ["No calibration improvement is claimed; the measurement is a sealed, purged CPCV family score.", "No flags, FWER ledger, or serving artifact changed."]}


def _memo(summary: dict) -> str:
    d, p = summary["denominator"], summary["prereg"]
    lines = ["# S254 MLB phase recalibration FWER sealed: ATTEMPT 2 (2026-09-04)", "", "## Seal and inputs", "",
             "Preregistration: `%s`; seal SHA-256 `%s`; LF header lines `%d`; sealed at `%s`." % (p["path"], p["sha256"], p["header_lines"], p["sealed_at_utc"]),
             "First score started at `%s` (after seal: true)." % summary["first_score_at_utc"],
             "Input store: `%s` (%d JSONL files, %d bytes; non-media input, so no resolution applies)." % (summary["source"]["path"], summary["source"]["file_count"], summary["source"]["bytes"]),
             "Code SHA-256: `%s`." % summary["code_sha256"], "", "## Denominator and purge", "",
             "Evaluated ticks %d; informative ticks %d; informative game clusters %d; whole-game replication clusters %d." % (d["n_eval_ticks"], d["n_informative_ticks"], d["n_informative_game_clusters"], d["replication_game_clusters"]),
             "CPCV used a symmetric %d-day embargo. The hash split is %d primary and %d replication game clusters. Exact excluded game-cluster reasons and evaluated n_train assertions for every split are in `S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary_attempt2.json` under `purge.splits`." % (summary["purge"]["embargo_days"], d["primary_game_clusters"], d["replication_game_clusters"]),
             "", "## ATTEMPT 2 corrections", "", "| finding | attempt 1 | attempt 2 |", "|---|---|---|",
             "| MLB identity | 53 of 158 IDs became game-unique | all 158 resolve through `parse_mlb_ticker` |",
             "| purge audit ordering | unsorted | sorted exactly as `cpcv_evaluate` |",
             "| audit route count | four logged/scored mismatches | eight asserted audit/evaluated n_train pairs |",
             "| hash replication partition | reported 158 | primary 83; replication 75 |",
             "", "## BH q=0.05 across all 15 buckets", "", "| bucket | delta | raw p | BH p | raw label | after BH | replication CI95 | replication |", "|---|---:|---:|---:|---|---|---|---|"]
    for row in summary["buckets"]:
        rep = row["replication"]
        lines.append("| %s | %+.6f | %.6f | %.6f | %s | %s | [%+.6f, %+.6f] | %s |" % (row["bucket"].replace("|", "\\|"), row["delta"], row["raw_p"], row["bh_p"], row["raw_label"], row["label_after_bh"], rep["ci95"][0], rep["ci95"][1], row["replication_label"]))
    lines += ["", "BH survivors: %s." % (", ".join(summary["bh_survivors"]) or "none"), "", "## NOT VERIFIED", ""] + ["- %s" % x for x in summary["not_verified"]]
    return "\n".join(lines) + "\n"


def run(cache_root: Path = ROOT / "data/cache") -> dict:
    prereg = prereg_identity()
    store = discover_store(cache_root)
    if store is None:
        raise ValueError("no parseable MLB store")
    files = list(store.rglob("*.jsonl"))
    assert sum(p.stat().st_size for p in files) <= 300 * 1024 * 1024, "store rail exceeded"
    ticks, features = arms.load_corpus(store, "mlb")
    records = s88.build_records(ticks, features)
    assert (len(records), len({r["game_id"] for r in records})) == (47104, 158), "S06 denominator drift"
    source_states, first_score = states(records), datetime.now(timezone.utc).isoformat()
    predictions, evaluated = callback_predictions(source_states)
    purge = purge_log(source_states, evaluated)
    frame = pd.DataFrame([dict(row, recal_prob=predictions[i]) for i, row in enumerate(records)])
    frame["incumbent_loss"] = (frame["model_prob"] - frame["outcome"]) ** 2
    frame["candidate_loss"] = (frame["recal_prob"] - frame["outcome"]) ** 2
    summary = summarize(frame, prereg, purge, first_score, store)
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(PAIR_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    MEMO_PATH.write_text(_memo(summary), encoding="ascii")
    return summary


def main() -> int:
    summary = run()
    print("S254 eval=%d informative=%d clusters=%d bh_survivors=%d" % (summary["denominator"]["n_eval_ticks"], summary["denominator"]["n_informative_ticks"], summary["denominator"]["n_informative_game_clusters"], len(summary["bh_survivors"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
