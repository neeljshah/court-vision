"""scripts.platformkit.edge_hunt_scoreboard -- the market-efficiency / self-audit roll-up.

The consolidated answer to "did ANY candidate pregame edge survive?" -- one REJECT
scoreboard across every schedule/fatigue/totals/CLV signal hunted across >=2 independent
corpora. The honest, recorded headline is: NOTHING survived; the market is efficient on
every pregame slice; positive full-sample lifts SIGN-FLIP on the held-out calendar half
(the overfit signature we CATCH). "Market efficient / no edge" is the FIRST-CLASS verdict
here, not a failure -- the self-audit IS the credential. No $ / ROI / +EV is produced.

This mirrors beat_the_close_scoreboard.py / ingame_scoreboard.py: it rolls up the two real
leak-free harnesses (edge_hunt_schedule, hunt_line_movement) into one canonical table and
points docs/MARKET_EFFICIENCY_PROOF.md at a single reproduce command.

FIXTURE vs REAL-CORPUS convention (same as the other scoreboards):
  * --recorded (default): print the CANONICAL recorded table (the live harness numbers
    measured on the real NBA/MLB/soccer/tennis corpora; the buyer-facing methodology proof
    on a fresh clone, where the private corpora are absent = VALIDATION_PENDING).
  * --live: actually re-run edge_hunt_schedule on the present real corpus (data/domains/
    basketball_nba). On a fresh clone with no corpus this prints a VALIDATION_PENDING banner
    and falls back to the recorded table -- never fabricates a number.

INVARIANTS: never edit src/ or kernel/ / eval_gate; <=300 LOC; ASCII only; calibration/
self-audit only, no $ edge; edge_claimed = False. Run:
  python -m scripts.platformkit.edge_hunt_scoreboard
  python -m scripts.platformkit.edge_hunt_scoreboard --live
"""
from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_NBA_GAMES = _REPO / "data/domains/basketball_nba/games.parquet"
_NBA_ODDS = _REPO / "data/domains/basketball_nba/odds.parquet"

# The CANONICAL recorded table -- the live edge_hunt_schedule / hunt_line_movement output
# measured on the real local corpora (docs/research/organization-sprint/EDGE-HUNT-RESULTS.md).
# Every row REJECTS. overfit = the held-out-half sign-flip signature where applicable.
# (candidate, corpora, bss_vs_close, dm_p, n, verdict, overfit_flag)
_RECORDED: List[Dict] = [
    {"candidate": "NBA b2b_diff", "corpora": "2026 H1/H2", "bss": "+0.0006",
     "dm_p": "0.657", "n": "1103", "verdict": "REJECT", "overfit": "sign flips H1<->H2"},
    {"candidate": "NBA three_in_four_diff", "corpora": "2026 H1/H2", "bss": "+0.0003",
     "dm_p": "0.795", "n": "1156", "verdict": "REJECT", "overfit": "sign flips H1<->H2"},
    {"candidate": "NBA rest_diff", "corpora": "2026 H1/H2", "bss": "+0.0007",
     "dm_p": "0.508", "n": "1103", "verdict": "REJECT", "overfit": "sign flips H1<->H2"},
    {"candidate": "NBA home_court (HCA probe)", "corpora": "2026 H1/H2", "bss": "0.0000",
     "dm_p": "0.173", "n": "1156", "verdict": "REJECT", "overfit": "HCA fully in devig"},
    {"candidate": "NBA altitude_home", "corpora": "2026 H1/H2", "bss": "-0.0014",
     "dm_p": "0.162", "n": "1156", "verdict": "REJECT", "overfit": "consistently worse"},
    {"candidate": "NBA travel_diff", "corpora": "2026 H1/H2", "bss": "+0.0011",
     "dm_p": "0.759", "n": "1103", "verdict": "REJECT", "overfit": "sign flips H1<->H2"},
    {"candidate": "MLB rest/streak/h2h x3", "corpora": "NL + AL", "bss": "<=0",
     "dm_p": "n/s", "n": "14k ea", "verdict": "REJECT", "overfit": "reject on BOTH leagues"},
    {"candidate": "Soccer rest/totals/h2h x3", "corpora": "by div", "bss": "<=0",
     "dm_p": "n/s", "n": "7.5k", "verdict": "REJECT", "overfit": "fail null-shuffle/BH-FDR"},
    {"candidate": "Tennis fatigue/surface/h2h x3", "corpora": "2 corpora", "bss": "<=0",
     "dm_p": "n/s", "n": "7.4k", "verdict": "REJECT", "overfit": "fail null-shuffle/BH-FDR"},
    {"candidate": "MLB totals slice (NL ALL)", "corpora": "NL", "bss": "-0.0141",
     "dm_p": "0.0092", "n": "1594", "verdict": "REJECT", "overfit": "close BEATS us"},
    {"candidate": "MLB totals slice (AL ALL)", "corpora": "AL", "bss": "-0.0185",
     "dm_p": "0.0002", "n": "1610", "verdict": "REJECT", "overfit": "close BEATS us"},
    {"candidate": "MLB open->close CLV capture", "corpora": "NL + AL", "bss": "n/a",
     "dm_p": "CI~0", "n": "25.5k", "verdict": "REJECT", "overfit": "NL/AL sign disagree"},
]

_CLV_NOTE = (
    "CLV finding: the close IS sharper than the open (MLB DM on log-loss p=0.0010, "
    "N=27,975) -- CLV exists as a MARKET phenomenon. But a leak-free open-time model has "
    "~0 corr with the open->close move (corr=+0.0038, CI[-0.046,+0.055]); CLV-capture mean "
    "NL +0.108pp / AL -0.017pp straddles zero and DISAGREES in sign. Not ours to harvest -- "
    "it is the market's own sharpening, a same-day-info/speed edge a retrospective model "
    "cannot capture. REJECT."
)


def _live_nba_present() -> bool:
    return _NBA_GAMES.exists() and _NBA_ODDS.exists()


def _run_live_schedule() -> str:
    """Re-run the REAL edge_hunt_schedule harness on the present NBA corpus, capturing its
    SHIP/REJECT + BSS + DM-p + sign-flip output verbatim. Never fabricates; on any failure
    returns an honest error string so the caller falls back to the recorded table."""
    try:
        from scripts.platformkit import edge_hunt_schedule as _eh  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        return f"(live edge_hunt_schedule not importable: {exc})"
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            _eh.run()
    except Exception as exc:  # noqa: BLE001
        return f"(live edge_hunt_schedule run failed: {exc})"
    return buf.getvalue()


def render_markdown(live_block: str = "") -> str:
    L: List[str] = [
        "# Edge-Hunt Scoreboard -- every candidate pregame edge, REJECTED",
        "",
        "> Honest, consolidated self-audit: every schedule / fatigue / totals / CLV signal "
        "hunted through the REAL leak-free gate across >=2 independent corpora. Each row is a "
        "REJECT. **NONE survived** -- the market is efficient on every pregame slice measured. "
        "Positive full-sample lifts SIGN-FLIP on the held-out calendar half (the overfit "
        "signature we CATCH). 'Market efficient / no edge' is the FIRST-CLASS verdict here, "
        "not a failure; the self-audit is the credential. Calibration / honesty only -- NOT a "
        "$ edge; edge_claimed = False.",
        "",
        "| Candidate | Corpora | BSS vs close | DM p | N | Verdict | Overfit signature |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in _RECORDED:
        L.append(f"| {r['candidate']} | {r['corpora']} | {r['bss']} | {r['dm_p']} | "
                 f"{r['n']} | {r['verdict']} | {r['overfit']} |")
    L += [
        "",
        _CLV_NOTE,
        "",
        "**HONEST BOTTOM LINE:** nothing survived >=2 corpora + DM p<0.05 + N>=200 as a "
        "market-beating edge. Every schedule / fatigue / form / h2h / totals candidate "
        "REJECTED across independent corpora; every positive full-sample BSS reversed sign on "
        "the held-out half. The market is efficient on every pregame slice -- the correct, "
        "expected result, recorded as a SUCCESS, not a failure.",
        "",
        "Companion docs: docs/MARKET_EFFICIENCY_PROOF.md (the writeup), "
        "vault/_Edge_Maps/_Beat_The_Close.md (the pregame MATCH baselines).",
    ]
    if live_block:
        L += [
            "",
            "---",
            "",
            "## Live re-run (real corpus, --live)",
            "",
            "```",
            live_block.rstrip(),
            "```",
        ]
    return "\n".join(L)


def _main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="edge_hunt_scoreboard",
        description="Consolidated market-efficiency / self-audit REJECT scoreboard.")
    ap.add_argument("--live", action="store_true",
                    help="re-run the REAL edge_hunt_schedule harness on the present NBA "
                         "corpus and append its verbatim output (VALIDATION_PENDING + "
                         "recorded fallback when no corpus is present).")
    args = ap.parse_args(argv)

    live_block = ""
    if args.live:
        if _live_nba_present():
            live_block = _run_live_schedule()
        else:
            live_block = ("VALIDATION_PENDING: no real NBA corpus present "
                          "(data/domains/basketball_nba absent on this clone). The recorded "
                          "table above is the canonical measured result; re-run --live with "
                          "the private corpus to reproduce the harness output end-to-end.")
    print(render_markdown(live_block))
    print("\n# market efficient on every pregame slice = the recorded SUCCESS; "
          "edge_claimed = False")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
