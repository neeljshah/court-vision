"""scripts.platformkit.calibration_record -- the PUBLIC calibration-record generator.

Assembles a calibration-record page from the committed, offline fixtures: (1) the eval-gate
golden anchor (reliability table + Brier-vs-close), (2) the track-record ledger fixture
(per-sport Brier/ECE vs the Shin-devigged close), and (3) the in-game static->conditional
Brier win (the one measured calibration win, real-corpus OOS, scoped honestly). It ADDS a
>=10-bin reliability table (n per bin, SPARSE flag at n<30) and a per-source BADGE on every row.

'MARKET-EFFICIENT HERE' is a FIRST-CLASS verdict -- a feature, not a failure. DECISION-SUPPORT,
not a picks/ROI product: edge_claimed is always False, no $ number is produced, the retracted
artifacts are never printed. Offline + deterministic on the committed fixtures, < 60s.

Usage:
  python -m scripts.platformkit.calibration_record           # ASCII/markdown to stdout
  python -m scripts.platformkit.calibration_record --write   # -> docs/CALIBRATION_RECORD.md
  python -m scripts.platformkit.calibration_record --png      # guarded matplotlib PNGs

INVARIANTS: never edit src/ or kernel/; reuse the eval_gate + ledger modules; <=300 LOC;
ASCII only; no secrets; never prints a retracted number.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for _p in (str(_HERE / "eval_gate"), str(_HERE / "ledger")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.platformkit.eval_gate import run_gate as _gate  # noqa: E402
from scripts.platformkit.eval_gate.walkforward import walk_forward  # noqa: E402
from scripts.platformkit.eval_gate.offline_predict import offline_predict_fn  # noqa: E402
from scripts.platformkit.ledger import metrics as _metrics  # noqa: E402
from scripts.platformkit.ledger.replay_proof import replay_proof  # noqa: E402

# source badges -- every numeric row is tagged with exactly one of these
BADGE_MODEL = "[model-in-corpus]"      # our calibrated forecaster, in its own corpus
BADGE_MARKET = "[devigged-market]"     # the Shin-devigged closing line
BADGE_ANCHOR = "[score-only-anchor]"   # synthetic golden anchor, not a real claim
BADGE_INGAME = "[model in-corpus, real-corpus]"   # real-PRIVATE-corpus OOS, not a fixture number

# In-game static->conditional Brier gains -- the ONE measured calibration win. real-corpus OOS
# numbers (data/domains/<sport>), reproduced by proof_<sport>/ingame_accuracy.py; the synthetic
# fixture prints NO-IMPROVEMENT for NBA (synthetic-anchor artifact, NOT a refutation). FORECASTER
# QUALITY, NOT a $ edge -- a live book sees the score, so no DM-vs-close applies, edge_claimed=False.
# (sport, checkpoint, static_brier, conditional_brier, corpus scope)
_INGAME_ROWS = [
    ("NBA", "end Q1/Q2/Q3", "0.209", "0.159",
     "real-corpus OOS = the win; committed fixture prints no-improvement (synthetic-anchor)"),
    ("MLB", "after inning 3/5/7", "0.241", "0.126",
     "real-corpus OOS; reproduces on the committed fixture"),
]

SPARSE_N = 30          # bins with fewer than this are flagged UNRELIABLE
N_BINS = 10            # >=10 equal-width reliability bins
_DOCS = _REPO / "docs"
_PNG_DIR = _REPO / "docs" / "_calibration_png"   # gitignored output dir

DISCLAIMER = (
    "DECISION-SUPPORT, NOT a picks / profit / +EV / ROI product. Every number is a "
    "CALIBRATION measurement (predicted vs observed), badged by SOURCE. 'MARKET-EFFICIENT "
    "HERE' -- matching the devigged close within noise -- is the HONEST, expected result "
    "and a first-class feature, not a failure. edge_claimed=False everywhere; no $ figure "
    "is produced. Real-corpus OOS-vs-close is VALIDATION_PENDING (human-run)."
)


def reliability_bins(p: Sequence[float], y: Sequence[float],
                     n_bins: int = N_BINS) -> List[dict]:
    """Equal-WIDTH reliability bins. Returns one dict per NON-EMPTY bin with the bin
    range, n, mean predicted, observed frequency, and a sparse flag (n < SPARSE_N).
    The per-bin n values sum to len(p) (every prediction lands in exactly one bin)."""
    pa = np.asarray(p, float)
    ya = np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.digitize(pa, edges[1:-1])   # 0..n_bins-1, last edge inclusive via clip below
    idx = np.clip(idx, 0, n_bins - 1)
    rows: List[dict] = []
    for b in range(n_bins):
        m = idx == b
        nk = int(m.sum())
        if not nk:
            continue
        rows.append({
            "lo": float(edges[b]), "hi": float(edges[b + 1]), "n": nk,
            "pred": float(pa[m].mean()), "obs": float(ya[m].mean()),
            "sparse": nk < SPARSE_N,
        })
    return rows


def _gate_records() -> Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Raw per-row (p_model, p_close, y) per golden corpus, via the SAME walk_forward
    the gate uses. Offline; never touches real data/."""
    out: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for name in _gate.CORPORA:
        states = _gate._load_states(name, None, None)
        res = walk_forward(states, offline_predict_fn, select_inside=True)
        recs = res.records
        pm = np.array([r["p_model"] for r in recs], float)
        pc = np.array([r["p_close"] for r in recs], float)
        y = np.array([r["y"] for r in recs], float)
        out[name] = (pm, pc, y)
    return out


def _fmt_bin_table(rows: List[dict], badge: str) -> List[str]:
    out = [f"| bin | n | predicted | observed | flag | source |",
           f"|-----|---|-----------|----------|------|--------|"]
    for r in rows:
        flag = "SPARSE (n<30, unreliable)" if r["sparse"] else "ok"
        out.append(f"| {r['lo']:.1f}-{r['hi']:.1f} | {r['n']} | {r['pred']:.3f} "
                   f"| {r['obs']:.3f} | {flag} | {badge} |")
    return out


def _gate_verdict(rows: List[dict], name: str) -> Tuple[str, str]:
    """Honest one-line verdict for a gate corpus row (from the gate's own scoreboard)."""
    row = next((r for r in rows if r.get("corpus") == name and "verdict" in r), None)
    if row is None:
        return ("CORPUS_ABSENT", "")
    v = row["verdict"]
    # brier_model is OUR forecaster's score (model-in-corpus); the synthetic-anchor caveat lives
    # in the section header. The bin tables carry the score-only-anchor badge (synthetic outcomes).
    detail = (f"brier_model={row['brier_model']:.4f} {BADGE_MODEL}  vs  "
              f"brier_close={row['brier_close']:.4f} {BADGE_MARKET}  "
              f"bss={row['bss']:.4f}  dm_p={row['dm_p']:.4f}  "
              f"(golden anchor {BADGE_ANCHOR}: synthetic, not a real claim)")
    # MATCHES_CLOSE -> the first-class "market-efficient" state; BEHIND is stated honestly.
    if v == "MATCHES_CLOSE":
        v = "MARKET-EFFICIENT HERE (MATCHES_CLOSE)"
    elif v == "BEHIND":
        v = "BEHIND (model trails close here -- stated honestly)"
    return (v, detail)


def _ingame_section() -> List[str]:
    """In-game static->conditional Brier gain -- the ONE measured CALIBRATION win. Badged
    [model in-corpus, real-corpus]; honest caveat + synthetic-fixture/real-corpus scoping."""
    out = ["## 3. In-game conditioning -- the one measured CALIBRATION win " + BADGE_INGAME, "",
           "Conditioning the SAME pregame intelligence prior on the realized mid-game state "
           "sharpens the win-prob forecaster (lower Brier = sharper). FORECASTER QUALITY / "
           "calibration, NOT a $ edge -- a live book also sees the score, so no DM-vs-close "
           "applies and edge_claimed stays False. SCOPING: real-PRIVATE-corpus OOS numbers; "
           "on the committed SYNTHETIC fixture the NBA row prints no-improvement (a synthetic-"
           "anchor artifact, not a refutation). Reproduced by "
           "scripts/platformkit/proof_<sport>/ingame_accuracy.py, rolled up in "
           "scripts/platformkit/ingame_scoreboard.py.", "",
           "| sport | checkpoint | static Brier | conditional Brier | gain | source | corpus scope |",
           "|-------|-----------|--------------|-------------------|------|--------|--------------|"]
    for sport, ckpt, static, cond, scope in _INGAME_ROWS:
        gain = float(static) - float(cond)
        out.append(f"| {sport} | {ckpt} | {static} | {cond} | -{gain:.3f} | {BADGE_INGAME} "
                   f"| {scope} |")
    out += ["", "MLB/Soccer/Tennis in-game wins reproduce on the committed fixture; the NBA win "
            "is real-corpus-only (VALIDATION_PENDING on a fresh clone). The sharpest forecaster "
            "FUSES the pregame rating prior with the realized state -- not either alone. No $ "
            "edge; edge_claimed = False.", ""]
    return out


def build_sections() -> List[str]:
    """Assemble the full ASCII/markdown CALIBRATION_RECORD body."""
    lines: List[str] = [
        "# Calibration Record", "", "> " + DISCLAIMER, "",
        "Source badges: " + BADGE_MODEL + " our calibrated forecaster in its own corpus; "
        + BADGE_MARKET + " the Shin-devigged closing line; " + BADGE_ANCHOR + " the synthetic "
        "golden regression anchor (not a real calibration claim).", "",
        "## Headline state", "",
        "**MARKET-EFFICIENT HERE** on team-strength markets: where we have power, the "
        "calibrated forecast MATCHES the devigged close within noise -- the expected, honest "
        "success state for a calibrated predictor, never an edge. Where a slice trails the "
        "close it is stated as BEHIND; where rows are thin it ABSTAINS. The decisive "
        "measured/calibrated value is in-game state conditioning (see section 3 and the "
        "predictor's `--state` path), not a pregame $ edge.", "",
        "## 1. Eval-gate golden anchor (reliability)", "",
        "Synthetic regression anchor scored leak-free / walk-forward. BSS<=0 / MATCHES is "
        "the HONEST result vs a near-oracle close.", ""]
    gate_rows = _gate.run_gate_in_process(offline_predict_fn)
    recs = _gate_records()
    for name in _gate.CORPORA:
        verdict, detail = _gate_verdict(gate_rows, name)
        lines.append(f"### {name}  --  {verdict}")
        if detail:
            lines.append("")
            lines.append(detail)
        pm, _pc, y = recs[name]
        lines.append("")
        lines.extend(_fmt_bin_table(reliability_bins(pm, y), BADGE_ANCHOR))
        lines.append("")

    # ---- Section 2: track-record ledger fixture ----
    lines += ["## 2. Track-record ledger (Brier / ECE vs devigged close)", "",
              "Committed fixture ledger; per-sport calibration vs the Shin-devigged close. "
              "Each slice has n=30 < the n>=50 report threshold, so the honest verdict is "
              "ABSTAIN (too few rows to claim a result) -- surfaced, never buried. On a "
              "powered real corpus a non-significant DM would read MARKET-EFFICIENT HERE; "
              "that measurement is VALIDATION_PENDING.", ""]
    led = replay_proof()
    lines.append(f"Fixture rows (graded): {led['n_rows']} {BADGE_MODEL}")
    lines.append("")
    lines.append("| sport | market | n | brier (model) | ece | brier (close) | dm_p | verdict |")
    lines.append("|-------|--------|---|---------------|-----|---------------|------|---------|")
    for sport, e in sorted(led["by_sport"].items()):
        mb = e.get("market_brier")
        dmp = e.get("dm_p_value")
        # matches_close -> market-efficient; insufficient_data -> honest ABSTAIN; lower-Brier
        # slice stays OOS-PENDING, never an edge claim.
        verdict = e.get("verdict", "reported")
        if verdict == "matches_close":
            verdict = "MARKET-EFFICIENT HERE (matches_close)"
        elif verdict == "insufficient_data":
            verdict = "ABSTAIN (insufficient_data, n<50)"
        elif verdict == "reported":
            verdict = "reported (n>=50; see dm_p)"
        elif verdict == "beats_close_oos_pending":
            verdict = "lower Brier (OOS-PENDING, not an edge claim)"
        mb_s = f"{mb:.4f} {BADGE_MARKET}" if mb is not None else "n/a"
        dmp_s = f"{dmp:.4f}" if dmp is not None else "n/a"
        lines.append(f"| {sport} | {e['market']} | {e['n']} | {e['brier']:.4f} {BADGE_MODEL} "
                     f"| {e['ece']:.4f} | {mb_s} | {dmp_s} | {verdict} |")
    lines.append("")

    # ---- Section 3: in-game conditioning (the one measured calibration win) ----
    lines.extend(_ingame_section())

    # ---- Section 4: reproduce + pending ----
    lines += ["## 4. Reproduce (offline, < 60s each)", "", "```",
              "python -m scripts.platformkit.eval_gate.run_gate --golden",
              "python -m scripts.platformkit.ledger.replay_proof",
              "python -m scripts.platformkit.calibration_record --write",
              "python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof",
              "```", "", "## 5. VALIDATION_PENDING (human-run)", "",
              "The numbers above reproduce the COMMITTED FIXTURES only. A real-corpus "
              "OOS-vs-close calibration result is a human-run step on local/gitignored corpora; "
              "no real-data win is claimed here. The in-game section 3 numbers are real-corpus "
              "OOS (NBA VALIDATION_PENDING on a fresh clone). See docs/SELL-READINESS.md and "
              "docs/JOB_EVIDENCE_PACKET.md."]
    return lines


def _maybe_png(recs: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]]) -> Optional[str]:
    """Guarded reliability-diagram PNGs. No-raise when matplotlib is absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001 - matplotlib optional
        return f"png skipped (matplotlib unavailable: {type(e).__name__})"
    _PNG_DIR.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    for name, (pm, _pc, y) in recs.items():
        rows = reliability_bins(pm, y)
        if not rows:
            continue
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.plot([0, 1], [0, 1], "k--", linewidth=1)
        ax.plot([r["pred"] for r in rows], [r["obs"] for r in rows], "o-")
        ax.set_xlabel("predicted")
        ax.set_ylabel("observed")
        ax.set_title(f"reliability: {name} (anchor)")
        out = _PNG_DIR / f"reliability_{name}.png"
        fig.savefig(out, dpi=80)
        plt.close(fig)
        written.append(str(out))
    return "png written: " + ", ".join(written) if written else "png: no non-empty bins"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="calibration_record",
        description="Generate the public calibration-record page (offline, deterministic).")
    ap.add_argument("--write", action="store_true",
                    help="write docs/CALIBRATION_RECORD.md (else print to stdout)")
    ap.add_argument("--png", action="store_true",
                    help="also emit guarded matplotlib reliability PNGs (gitignored dir)")
    args = ap.parse_args(argv)
    t0 = time.time()
    body = "\n".join(build_sections()) + "\n"
    if args.write:
        _DOCS.mkdir(parents=True, exist_ok=True)
        (_DOCS / "CALIBRATION_RECORD.md").write_text(body, encoding="ascii")
        print(f"wrote {_DOCS / 'CALIBRATION_RECORD.md'} ({len(body)} bytes)")
    else:
        print(body)
    if args.png:
        print(_maybe_png(_gate_records()))
    print(f"# generated in {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
