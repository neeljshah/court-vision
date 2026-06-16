"""run_capture -- the "START THE CLOCK" headless forward-capture runner.

ONE tick does two forward, vintage-stamped things and NOTHING else:

  (1) ARCHIVE the tape   -- feed.poll() -> archive.append_snapshots(): the real
      timestamped odds-movement corpus accrues forward to data/forward_capture/
      (gitignored). The close snapshot will later supply captured_at (the line-move
      time) + the home/away decimal prices that ledger/grade_outcomes devigs.

  (2) LOG predictions    -- any pregame prediction handed to the tick is written to
      the EXISTING X3 ledger via ledger.append_prediction / append_from_result, each
      stamped pred_ts = utc_now_iso() AT LOG TIME (forward), strictly BEFORE any
      captured line move. pred_ts is THE vintage clock. calibrated_prob is copied
      VERBATIM from the quant pipeline -- the LLM (this runner) authors no number.

forward_capture adds ZERO new ledger code: it only CALLS append_prediction /
append_from_result here. Grading (devig the captured CLOSE via eval_gate/shin) and the
strict pred_ts < line-move CLV guard live in ledger/grade_outcomes + clv.py, run LATER
when outcomes land -- this runner only LOGS + ARCHIVES forward.

THE CLOCK SWITCH: if a real odds-feed key is present in the environment
(FORWARD_CAPTURE_ODDS_API_KEY) the runner uses RealFeed (whose poll() raises until a
human wires it -- the real clock). Otherwise it runs the deterministic MockFeed and
prints a clear DRY RUN banner: nothing is claimed, the real clock has not started.

NO live API call, NO secret in code (real feed = env-gated stub). NO $ / ROI / edge is
ever computed or printed. This RECORDS the data that will one day prove or reject an
edge; it claims nothing.

Headless / cron-able:
  python -m scripts.platformkit.forward_capture.run_capture --once
  python -m scripts.platformkit.forward_capture.run_capture --interval 60 --max-ticks 0

Stdlib + pandas (via the ledger/archive). ASCII only. <=300 LOC.
Per-file test: tests/test_run_capture.py.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from typing import Callable, List, Optional, Sequence

# --- import the sibling forward_capture modules + the EXISTING ledger READ-ONLY -------------
_PKIT = pathlib.Path(__file__).resolve().parents[1]            # scripts/platformkit
for _p in (_PKIT / "ledger", pathlib.Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:  # package import (`python -m scripts.platformkit.forward_capture.run_capture`)
    from scripts.platformkit.forward_capture import archive as _archive       # type: ignore
    from scripts.platformkit.forward_capture import capture as _capture       # type: ignore
except ImportError:  # direct-script / per-file-test fallback (sibling modules)
    import archive as _archive       # type: ignore
    import capture as _capture       # type: ignore

# the EXISTING X3 ledger -- forward_capture only CALLS these, never edits ledger/.
from ledger import append_prediction, append_from_result  # type: ignore  # noqa: E402

REAL_FEED_ENV = _capture.REAL_FEED_ENV
utc_now_iso = _capture.utc_now_iso

_DRY_RUN_BANNER = (
    "=" * 72 + "\n"
    "DRY RUN -- no real odds feed wired; running the deterministic MockFeed.\n"
    "  The forward-capture CLOCK has NOT started: snapshots + predictions below\n"
    "  are a self-test, not a real movement corpus.\n"
    "  WIRE A REAL FEED TO START THE REAL CLOCK:\n"
    "    set %s=<the_odds_api key>, implement RealFeed.poll() (HUMAN-RUN),\n"
    "    then re-run. See forward_capture/README.md.\n"
    "  No edge is claimed; this only RECORDS what will one day prove or reject one.\n"
    + "=" * 72
) % REAL_FEED_ENV


def _git_short_sha() -> str:
    """git short-sha of HEAD for ledger provenance (model_version). 'unknown' if unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_PKIT.parents[1]), capture_output=True, text=True, timeout=10)
        sha = (out.stdout or "").strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


# -- deterministic DRY-RUN fixtures (a tiny self-test tape + one pregame prediction) --------
_DRY_QUOTES: List[dict] = [
    {"book": "mock", "market": "ml", "sport": "nba", "game_id": "DRYRUN_G1",
     "side": "home", "price": 1.91, "captured_at": "2026-01-15T17:00:00+00:00"},
    {"book": "mock", "market": "ml", "sport": "nba", "game_id": "DRYRUN_G1",
     "side": "away", "price": 1.95, "captured_at": "2026-01-15T17:00:00+00:00"},
]
# A pregame prediction the DRY RUN logs. calibrated_prob is a FIXTURE constant here (this
# runner authors no number); in production it is copied verbatim from predict_matchup.
_DRY_PREDICTIONS: List[dict] = [
    {"sport": "nba", "layer": "pregame", "market": "ml", "home": "DRY_HOME",
     "away": "DRY_AWAY", "calibrated_prob": 0.55, "game_id": "DRYRUN_G1",
     "game_date": "2026-01-16", "inputs": {"dry_run": True}},
]


def _archive_snapshots(snaps: Sequence, base_dir: Optional[str]) -> int:
    """Append polled snapshots to the forward archive. Returns the count archived."""
    if not snaps:
        return 0
    _archive.append_snapshots(list(snaps), base_dir=base_dir)
    return len(snaps)


def _log_prediction(pred: dict, pred_ts: str, model_version: str,
                    ledger_dir: Optional[str]) -> List[str]:
    """Log ONE pregame prediction to the EXISTING ledger with pred_ts (forward).

    Two shapes are accepted, mirroring the ledger API:
      - a predict_matchup result dict (has a "pregame"/"ingame" block) -> append_from_result
        with layer_filter='pregame';
      - an explicit kwargs dict (sport/layer/market/home/away/calibrated_prob/inputs/...) ->
        append_prediction.
    calibrated_prob is copied VERBATIM from the quant pipeline; this runner authors no number.
    Returns the pred_id(s) written.
    """
    if "pregame" in pred or "ingame" in pred:  # predict_matchup result dict
        return list(append_from_result(
            pred, pred_ts=pred_ts, model_version=model_version,
            layer_filter="pregame", base_dir=ledger_dir))
    pid = append_prediction(
        sport=pred["sport"], layer=pred.get("layer", "pregame"), market=pred["market"],
        home=pred["home"], away=pred["away"],
        calibrated_prob=float(pred["calibrated_prob"]), inputs=pred.get("inputs", {}),
        pred_ts=pred_ts, model_version=model_version,
        point_proj=pred.get("point_proj"), game_date=pred.get("game_date"),
        game_id=pred.get("game_id"), base_dir=ledger_dir)
    return [pid]


def run_tick(predictions: Optional[Sequence[dict]] = None,
             quotes: Optional[Sequence[dict]] = None,
             feed=None, archive_dir: Optional[str] = None,
             ledger_dir: Optional[str] = None,
             model_version: Optional[str] = None) -> dict:
    """ONE forward-capture tick: poll -> archive the tape, then log each pregame prediction.

    Both steps happen in the SAME tick so pred_ts is stamped forward, before the captured
    close. Returns a summary dict (no $ / edge field). `feed` is injectable for tests; by
    default build_feed picks RealFeed (env key present) or a deterministic MockFeed.
    """
    mv = model_version or _git_short_sha()
    feed = feed if feed is not None else _capture.build_feed(quotes=quotes or [])
    snaps = feed.poll()                                   # RealFeed.poll() raises until wired
    n_arch = _archive_snapshots(snaps, archive_dir)

    pred_ids: List[str] = []
    pred_ts = utc_now_iso()                               # THE vintage clock, stamped forward
    for pred in (predictions or []):
        pred_ids.extend(_log_prediction(pred, pred_ts, mv, ledger_dir))

    return {"pred_ts": pred_ts, "feed": getattr(feed, "name", "feed"),
            "snapshots_archived": int(n_arch), "predictions_logged": len(pred_ids),
            "pred_ids": pred_ids, "model_version": mv}


def _load_json(path: Optional[str], key: str) -> Optional[List[dict]]:
    """Load a JSON fixture list (a bare list or {key: [...]}). None when path is None."""
    if not path:
        return None
    obj = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rows = obj[key] if isinstance(obj, dict) and key in obj else obj
    assert isinstance(rows, list), f"{path}: expected a list or {{'{key}': [...]}}"
    return rows


def run_loop(predictions: Optional[Sequence[dict]], quotes: Optional[Sequence[dict]],
             interval: float, max_ticks: int, archive_dir: Optional[str],
             ledger_dir: Optional[str], dry_run: bool, sleep=time.sleep,
             out=print) -> List[dict]:
    """Poll/archive/log on a fixed interval. max_ticks<=0 -> run forever (cron/headless).

    Prints the DRY RUN banner once up front when no real feed is wired. Each tick prints a
    one-line ASCII summary (counts + pred_ts only -- never a $ / edge figure). `sleep`/`out`
    are injectable so the per-file test drives a finite, deterministic loop with no real wait.
    """
    if dry_run:
        out(_DRY_RUN_BANNER)
    summaries: List[dict] = []
    tick = 0
    while True:
        s = run_tick(predictions=predictions, quotes=quotes,
                     archive_dir=archive_dir, ledger_dir=ledger_dir)
        summaries.append(s)
        out("tick=%d feed=%s archived=%d logged=%d pred_ts=%s"
            % (tick, s["feed"], s["snapshots_archived"], s["predictions_logged"],
               s["pred_ts"]))
        tick += 1
        if max_ticks > 0 and tick >= max_ticks:
            break
        sleep(interval)
    return summaries


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Forward-capture clock: poll -> archive the odds tape + log pregame "
                    "predictions to the X3 ledger with pred_ts. No live call / no secret "
                    "in code; a real feed is env-gated. Claims no edge.")
    ap.add_argument("--predictions", help="JSON file of pregame predictions to log "
                                          "(list or {'predictions': [...]}).")
    ap.add_argument("--quotes", help="JSON file of raw odds quotes for the DRY-RUN feed "
                                     "(list or {'quotes': [...]}). Ignored when a real "
                                     "feed key is set.")
    ap.add_argument("--interval", type=float, default=60.0,
                    help="seconds between ticks (default 60).")
    ap.add_argument("--max-ticks", type=int, default=1,
                    help="number of ticks; <=0 = run forever (headless/cron). Default 1.")
    ap.add_argument("--once", action="store_true", help="single tick then exit (= --max-ticks 1).")
    ap.add_argument("--archive-dir", help="override the odds-archive base dir (tests).")
    ap.add_argument("--ledger-dir", help="override the ledger base dir (tests).")
    args = ap.parse_args(list(argv) if argv is not None else None)

    real = _capture.has_real_feed()
    predictions = _load_json(args.predictions, "predictions")
    quotes = _load_json(args.quotes, "quotes")
    if not real:                                # DRY RUN -> deterministic self-test fixtures
        predictions = predictions if predictions is not None else _DRY_PREDICTIONS
        quotes = quotes if quotes is not None else _DRY_QUOTES

    max_ticks = 1 if args.once else args.max_ticks
    run_loop(predictions=predictions, quotes=quotes, interval=args.interval,
             max_ticks=max_ticks, archive_dir=args.archive_dir,
             ledger_dir=args.ledger_dir, dry_run=not real)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
