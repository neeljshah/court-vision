"""scripts.platformkit.live_edge.autoloop.validate_job -- AUTO-VALIDATE: a
Claude-free, idempotent job that keeps running EVERY ledger claim through the
existing hardened validator as new claims/data accrue, so survivors accumulate
without a human/agent driving each run.

GATING (two independent, cheap checks -- no expensive rescoring unless one
fires):
  1. NEW claims: any claim_id in data/omni/claims/claims.parquet not yet
     present in data/omni/live_edge/replay/full_ledger_results.parquet with a
     RESOLVED verdict (verdict != INSUFFICIENT_DATA). A claim only ever needs
     to be tested once it resolves to something other than INSUFFICIENT_DATA
     -- that verdict is final (data doesn't change retroactively).
  2. GAINED POWER: an INSUFFICIENT_DATA verdict may flip once its source
     corpus grows. Gated on corpus mtime (situation_grid.POSSESSIONS_PATH for
     the NBA team/player-grid path; the MLB GUMBO tick dir's newest file for
     the MLB path) vs this job's own watermark -- so an unchanged corpus is a
     true no-op (no corpus rebuild, no rescoring), not a wasted full rescan.

Reuses run_full_ledger's NBA classify/score functions verbatim (team + player
grain) -- IMPORT ONLY, never edited. MLB claims (scope.sport=="mlb", topic
"mlb_ingame.*") carry a DIFFERENT scope/effect shape (no stored baseline_rate)
that run_full_ledger's classifier was never built for, so this module adds its
own thin MLB scorer that reuses harden.validate_one_corpus (the same DM-
clustered-by-game test, imported not reimplemented) with a baseline computed
as the reserve corpus's own complement-of-cell mean (comp_mean isn't persisted
on the MLB claim row, only delta/ci/n -- so this is the honest OOS-time
equivalent of the discovery-time complement mean the claim's delta was
computed against).
# ponytail: single-corpus MLB scoring (6-day/122-game corpus is too thin to
# split trailing-date-in-half without gutting cell N further) -- honestly
# grain-labeled "mlb_<entity_type>", not silently merged into the NBA
# 2-corpora IMPROVES_BOTH_CORPORA bucket. Upgrade to a 2nd MLB corpus once a
# second dated GUMBO window accrues.

Output: appends/dedupes into data/omni/live_edge/replay/full_ledger_results.parquet
(same schema run_full_ledger.py writes -- claim_id is the merge key, latest
verdict wins), a cycle_log.jsonl row per run, and an atomically-written
watermark.json.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic
from scripts.platformkit.live_edge.replay import harden as hd
from scripts.platformkit.live_edge.replay import run_full_ledger as rfl
from scripts.platformkit.live_edge.situation_grid import POSSESSIONS_PATH

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CLAIMS_PATH = REPO_ROOT / "data" / "omni" / "claims" / "claims.parquet"
RESULTS_PATH = rfl.OUT_DIR / "full_ledger_results.parquet"
AUTOLOOP_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "autoloop"
WATERMARK_PATH = AUTOLOOP_DIR / "watermark.json"
CYCLE_LOG_PATH = AUTOLOOP_DIR / "cycle_log.jsonl"
GUMBO_DIR = REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"

MAX_CLAIMS_PER_CYCLE = 3000
_RESULT_COLS = ["claim_id", "topic", "grain", "lifecycle", "discovered_delta",
                "n_active_a", "n_games_a", "p_value_a", "verdict_a",
                "n_active_b", "n_games_b", "p_value_b", "verdict_b", "verdict"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_watermark() -> dict:
    if WATERMARK_PATH.exists():
        return json.loads(WATERMARK_PATH.read_text(encoding="ascii", errors="replace"))
    return {"last_run_ts": None, "nba_corpus_mtime": 0.0, "mlb_corpus_mtime": 0.0}


def _mlb_corpus_mtime() -> float:
    if not GUMBO_DIR.is_dir():
        return 0.0
    files = list(GUMBO_DIR.glob("*.jsonl"))
    return max((p.stat().st_mtime for p in files), default=0.0)


def _existing_results() -> pd.DataFrame:
    if RESULTS_PATH.exists():
        return pd.read_parquet(RESULTS_PATH)
    return pd.DataFrame(columns=_RESULT_COLS)


def _resolved_claim_ids(existing: pd.DataFrame) -> set:
    if not len(existing):
        return set()
    return set(existing.loc[existing["verdict"] != "INSUFFICIENT_DATA", "claim_id"])


# --- MLB scorer (thin; imports harden's DM test, never reimplements it) -----
def _mlb_reserve_corpus() -> pd.DataFrame:
    from scripts.platformkit.live_edge.mlb_ingame import mlb_grid as mg
    from scripts.platformkit.live_edge.mlb_ingame import mlb_mine as mm
    raw = mg.load_ticks()
    deduped = mg.dedupe_transitions(raw)
    with_targets = mm.add_targets(deduped)
    _discovery, reserve = mg.split_discovery_reserve(with_targets)
    tagged = mg.tag_situations(reserve)
    tagged["pitcher_bucket"] = mm._pitcher_bucket(tagged)  # noqa: SLF001 -- same-package reuse, read-only
    tagged["game_id"] = tagged["game_pk"]
    return tagged


def _classify_mlb(row) -> dict | None:
    try:
        scope = json.loads(row["scope_json"])
        effect = json.loads(row["effect_json"])
    except (TypeError, ValueError):
        return None
    ctx = scope.get("context")
    if not isinstance(ctx, dict) or "cell" not in ctx:
        return None
    if effect.get("verdict") != "TESTED" or "delta" not in effect or "stat" not in effect:
        return None
    return {"cell": ctx["cell"], "stat": effect["stat"], "delta": float(effect["delta"]),
            "entity_type": scope.get("entity_type", "league"), "entity_ids": scope.get("entity_ids", [])}


def _mlb_mask(df: pd.DataFrame, parsed: dict) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for k, v in parsed["cell"].items():
        if k in df.columns:
            mask &= df[k] == v
    if parsed["entity_type"] == "pitcher" and parsed["entity_ids"]:
        mask &= df["pitcher_bucket"].astype(str) == str(parsed["entity_ids"][0])
    mask &= df[parsed["stat"]].notna()
    return mask


def _score_mlb_claim(parsed: dict, corpus: pd.DataFrame) -> dict:
    mask = _mlb_mask(corpus, parsed)
    stat = parsed["stat"]
    complement = corpus.loc[~mask, stat]
    baseline = float(complement.mean()) if len(complement) else float(corpus[stat].mean())
    return hd.validate_one_corpus(corpus, mask, stat, baseline, parsed["delta"])


def run_validate_cycle(max_claims: int = MAX_CLAIMS_PER_CYCLE) -> dict:
    """One Claude-free validation cycle. Idempotent: re-running with no new
    claims and no corpus growth is a true no-op (verdict-identical parquet,
    same watermark values re-stamped)."""
    AUTOLOOP_DIR.mkdir(parents=True, exist_ok=True)
    watermark = _load_watermark()
    claims_df = pd.read_parquet(CLAIMS_PATH)
    existing = _existing_results()
    resolved = _resolved_claim_ids(existing)
    ever_tested = set(existing["claim_id"]) if len(existing) else set()
    candidates = claims_df[~claims_df["claim_id"].isin(resolved)]

    nba_mtime = POSSESSIONS_PATH.stat().st_mtime if POSSESSIONS_PATH.exists() else 0.0
    mlb_mtime = _mlb_corpus_mtime()
    nba_gated = nba_mtime > float(watermark.get("nba_corpus_mtime", 0.0))
    mlb_gated = mlb_mtime > float(watermark.get("mlb_corpus_mtime", 0.0))

    # A NEVER-tested claim is always due (new claims must not stall waiting on
    # corpus growth); an INSUFFICIENT_DATA RE-test is due only once its source
    # corpus grew (nothing can flip on unchanged data).
    mlb_parsed, nba_parsed = [], []
    for idx, row in candidates.iterrows():
        is_retest = row["claim_id"] in ever_tested
        if row.get("sport") == "mlb":
            if not is_retest or mlb_gated:
                parsed = _classify_mlb(row)
                if parsed is not None:
                    mlb_parsed.append((row["claim_id"], row["topic"], row["lifecycle"], parsed))
        elif not is_retest or nba_gated:
            parsed = rfl.classify_claim(row)
            if parsed.get("grain"):
                nba_parsed.append((row["claim_id"], row["topic"], row["lifecycle"], parsed))

    testable_total = len(mlb_parsed) + len(nba_parsed)
    capped = testable_total > max_claims
    if capped:
        mlb_parsed = mlb_parsed[:max_claims]
        nba_parsed = nba_parsed[:max(max_claims - len(mlb_parsed), 0)]

    new_rows: list[dict] = []
    if mlb_parsed:
        mlb_corpus = _mlb_reserve_corpus()
        for claim_id, topic, lifecycle, parsed in mlb_parsed:
            r = _score_mlb_claim(parsed, mlb_corpus)
            new_rows.append({
                "claim_id": claim_id, "topic": topic, "grain": f"mlb_{parsed['entity_type']}",
                "lifecycle": lifecycle, "discovered_delta": parsed["delta"],
                "n_active_a": r["n_active"], "n_games_a": r["n_games"], "p_value_a": r["p_value"],
                "verdict_a": r["verdict"], "n_active_b": None, "n_games_b": None, "p_value_b": None,
                "verdict_b": None, "verdict": r["verdict"],
            })

    if nba_parsed:
        corpora = rfl.build_corpora()
        for claim_id, topic, lifecycle, parsed in nba_parsed:
            if parsed["grain"] == "team":
                ra, rb = rfl.score_team_claim(parsed, corpora)
            else:
                ra, rb = rfl.score_player_claim(parsed, corpora)
            verdict = hd.combine_two_corpora(ra, rb)
            new_rows.append({
                "claim_id": claim_id, "topic": topic, "grain": parsed["grain"], "lifecycle": lifecycle,
                "discovered_delta": parsed.get("delta"),
                "n_active_a": ra["n_active"], "n_games_a": ra["n_games"], "p_value_a": ra["p_value"],
                "verdict_a": ra["verdict"],
                "n_active_b": rb["n_active"], "n_games_b": rb["n_games"], "p_value_b": rb["p_value"],
                "verdict_b": rb["verdict"], "verdict": verdict,
            })

    new_df = pd.DataFrame(new_rows, columns=_RESULT_COLS)
    merged = pd.concat([existing, new_df], ignore_index=True)
    if len(merged):
        merged = merged.drop_duplicates(subset="claim_id", keep="last")
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(RESULTS_PATH, index=False)

    verdict_counts = new_df["verdict"].value_counts().to_dict() if len(new_df) else {}
    summary = {
        "ts": _now_iso(), "picked_up": int(len(candidates)),
        "mlb_testable": len(mlb_parsed), "nba_testable": len(nba_parsed),
        "tested": len(new_rows), "cap": max_claims, "capped": capped,
        "nba_gated": nba_gated, "mlb_gated": mlb_gated,
        "verdict_counts": verdict_counts, "results_rows_total": int(len(merged)),
    }
    append_jsonl_atomic(CYCLE_LOG_PATH, summary)

    watermark["last_run_ts"] = summary["ts"]
    if nba_gated:
        watermark["nba_corpus_mtime"] = nba_mtime
    if mlb_gated:
        watermark["mlb_corpus_mtime"] = mlb_mtime
    write_json_atomic(WATERMARK_PATH, watermark)
    return summary


def main() -> int:
    summary = run_validate_cycle()
    for k, v in summary.items():
        print(f"[validate_job] {k}: {v}")
    return 0


__all__ = ["run_validate_cycle", "RESULTS_PATH", "WATERMARK_PATH", "CYCLE_LOG_PATH"]

if __name__ == "__main__":
    import sys
    sys.exit(main())
