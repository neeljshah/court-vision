"""Generate/update RECEIPTS.md from existing on-disk result artifacts.

Reads JSON/CSV artifacts under scripts/platformkit/benchmarks/crps_market/ and
results/, and appends a dated, hash-keyed section to RECEIPTS.md at the repo
root. Pure read-and-format -- no compute, no network.

Usage:
    python -m scripts.platformkit.receipts.build_receipts
    python -m scripts.platformkit.receipts.build_receipts --check
    python -m scripts.platformkit.receipts.build_receipts --json
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RECEIPTS_PATH = REPO_ROOT / "RECEIPTS.md"
CRPS_DIR = REPO_ROOT / "scripts" / "platformkit" / "benchmarks" / "crps_market"
RESULTS_DIR = REPO_ROOT / "results"
RECEIPTS_JSON_PATH = REPO_ROOT / "webapp" / "public" / "receipts.json"
REJECT_LEDGER_PATH = REPO_ROOT / "data" / "frontend" / "reject_ledger.jsonl"

# A row's source artifact decides its registration label. Prospective-scoreboard
# snapshots (once E1c wires them in) are the only genuinely pre-registered rows;
# everything else here reads a historical benchmark artifact captured after the
# fact -- label it Retrospective so the header claim matches what is on disk.
def _registration_label(src: str) -> str:
    return "Pre-registered (forward)" if "prospective" in src else "Retrospective (recorded)"


def _honest_rejects() -> dict:
    """Dynamic reject-ledger count, read directly off the jsonl (no import of
    reject_ledger.py -- avoids its module side effects; this is a straight
    line-count + distinct-key scan, source of truth: data/frontend/reject_ledger.jsonl).
    total = every verdict row ever appended (append-only ledger); distinct =
    unique (sport, signal) pairs currently represented -- do not conflate the two.
    """
    total = 0
    distinct = set()
    if REJECT_LEDGER_PATH.exists():
        with REJECT_LEDGER_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                distinct.add((rec.get("sport"), rec.get("signal")))
    return {
        "total_verdict_rows": total,
        "distinct_signals": len(distinct),
        "as_of": date.today().isoformat(),
        "source": "data/frontend/reject_ledger.jsonl",
    }


HONEST_REJECTS = _honest_rejects()

# ponytail: exact retracted-number tokens from .claude/rules/no-edge-claims.md;
# extend this list if the rule file grows, no need to auto-sync it.
BANNED_TOKENS = ["+18.38%", "18.38", "0.119", "+54%", "54%", "78.11", "8.94", "54.57"]

# Excluded on review: results/holdout_metrics.csv (stale May-17 n=480 measurement
# that conflicts with the canonical 2026-07-20 verify_production_mae holdout) and
# last_run_ingame_nba_winprob.json (n=5 pilot superseded by ALLGAMES_v3).
ARTIFACT_FILES = [
    CRPS_DIR / "last_run_mlb.json",
    CRPS_DIR / "last_run_ingame_mlb.json",
    CRPS_DIR / "last_run_ingame_nba_winprob_ALLGAMES_v3.json",
    CRPS_DIR / "last_run_ingame_soccer.json",
    RESULTS_DIR / "winprob_walk_forward_results.json",
]

HEADER = """# RECEIPTS.md

Honesty-gated receipts ledger. Every row below is read verbatim from a
machine-readable artifact on disk (path cited per row) -- no number here is
hand-typed. Each row carries its own Registration label: "Retrospective
(recorded)" means the source artifact was captured before this ledger read
it (a historical benchmark run); "Pre-registered (forward)" means the
checkpoint and verdict rule were declared before the outcome was known (the
prospective scoreboard). Do not read "ledger" as "every row pre-registered"
-- check the column. This file claims calibration/sharpness only, never a
dollar edge, ROI, or bankroll result; verdicts include losses
(MARKET_SHARPER, UNDERPOWERED) exactly as measured. Immutable git history is
the provenance trail: each dated section below is append-only and keyed to a
content hash of the source artifacts, so re-running the generator never
duplicates a section.

**Navigate:** [Full doc map](docs/INDEX.md) - [Home](README.md) - [Evidence pages](docs/evidence/) - [Glossary](docs/GLOSSARY.md)
"""


def _fmt(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _ci(ci):
    if not ci:
        return "n/a"
    return f"[{_fmt(ci[0])}, {_fmt(ci[1])}]"


def rows_from_crps_pregame_mlb(art: dict, src: str) -> list[dict]:
    return [{
        "sport_market": f"{art.get('sport')}/{art.get('market')}",
        "checkpoint": "pregame",
        "model": _fmt(art.get("model_crps_mean")) + " (CRPS)",
        "market": _fmt(art.get("market_crps_mean")) + " (CRPS)",
        "delta_ci": f"{_fmt(art.get('paired_delta_mean'))} {_ci(art.get('paired_delta_95ci'))}",
        "n": art.get("n_scored"),
        "verdict": art.get("verdict", "n/a"),
        "src": src,
    }]


def rows_from_checkpoints_artifact(art: dict, src: str, metric_label: str) -> list[dict]:
    sport_market = art.get("sport", "?")
    if "metric" in art:
        sport_market += f"/{art['metric']}"
    out = []
    for cp, d in (art.get("checkpoints") or {}).items():
        model_v = d.get("model_crps_mean", d.get("model_brier_mean"))
        market_v = d.get("market_crps_mean", d.get("market_brier_mean"))
        out.append({
            "sport_market": sport_market,
            "checkpoint": cp,
            "model": f"{_fmt(model_v)} ({metric_label})",
            "market": f"{_fmt(market_v)} ({metric_label})" if market_v is not None else "no market baseline in artifact",
            "delta_ci": f"{_fmt(d.get('paired_delta_mean'))} {_ci(d.get('paired_delta_95ci'))}",
            "n": d.get("n"),
            "verdict": d.get("verdict", "n/a"),
            "src": src,
        })
    return out


def rows_from_walk_forward(art: dict, src: str) -> list[dict]:
    return [{
        "sport_market": "nba/pregame_winprob",
        "checkpoint": f"{art.get('n_folds')}-fold walk-forward (mean)",
        "model": f"{_fmt(art.get('brier_mean'))} (Brier, std {_fmt(art.get('brier_std'))})",
        "market": "no market baseline in artifact",
        "delta_ci": "n/a",
        "n": sum(f.get("n_val", 0) for f in art.get("folds", [])),
        "verdict": "NO_MARKET_COMPARISON_IN_ARTIFACT",
        "src": src,
    }]


def rows_from_holdout_csv(path: Path, src: str) -> list[dict]:
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append({
                "sport_market": f"nba/{row['model']}",
                "checkpoint": "holdout",
                "model": f"MAE {row['holdout_mae']} (R2 {row['holdout_r2']}, n={row['holdout_n']})",
                "market": "no market baseline in artifact",
                "delta_ci": "n/a",
                "n": row["holdout_n"],
                "verdict": "NO_MARKET_COMPARISON_IN_ARTIFACT",
                "src": src,
            })
    return out


def collect_rows() -> tuple[list[dict], list[str], list[str]]:
    rows: list[dict] = []
    skipped: list[str] = []
    used_paths: list[str] = []
    for path in ARTIFACT_FILES:
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        if not path.exists():
            skipped.append(f"{rel} -- file not found")
            continue
        try:
            if path.suffix == ".csv":
                rows.extend(rows_from_holdout_csv(path, rel))
            else:
                art = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "last_run_mlb.json":
                    rows.extend(rows_from_crps_pregame_mlb(art, rel))
                elif path.name == "winprob_walk_forward_results.json":
                    rows.extend(rows_from_walk_forward(art, rel))
                elif "soccer" in path.name:
                    rows.extend(rows_from_checkpoints_artifact(art, rel, "Brier"))
                elif "winprob" in path.name:
                    rows.extend(rows_from_checkpoints_artifact(art, rel, "Brier"))
                else:
                    rows.extend(rows_from_checkpoints_artifact(art, rel, "CRPS"))
            used_paths.append(rel)
        except Exception as e:  # pragma: no cover - defensive, artifact shape drift
            skipped.append(f"{rel} -- {type(e).__name__}: {e}")
    return rows, skipped, used_paths


def content_hash(used_paths: list[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(used_paths):
        h.update((REPO_ROOT / rel).read_bytes())
    return h.hexdigest()[:12]


def render_table(rows: list[dict]) -> str:
    lines = [
        "| Sport/Market | Checkpoint | Model | Market | Delta (95% CI) | n | Verdict | Registration | Source artifact |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['sport_market']} | {r['checkpoint']} | {r['model']} | {r['market']} | "
            f"{r['delta_ci']} | {r['n']} | {r['verdict']} | {_registration_label(r['src'])} | `{r['src']}` |"
        )
    return "\n".join(lines)


def build(check_only: bool = False) -> int:
    rows, skipped, used_paths = collect_rows()
    batch_hash = content_hash(used_paths)
    marker = f"<!-- receipts-batch: {batch_hash} -->"

    existing = RECEIPTS_PATH.read_text(encoding="utf-8") if RECEIPTS_PATH.exists() else ""

    if marker in existing:
        print(f"RECEIPTS.md already up to date for batch {batch_hash} (no-op).")
        return validate(existing) if check_only else 0

    today = date.today().isoformat()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    section = [
        marker,
        f"## {today} -- batch {batch_hash}",
        f"_generated {now} UTC by scripts/platformkit/receipts/build_receipts.py_",
        "",
        render_table(rows),
    ]
    if skipped:
        section.append("")
        section.append("Skipped inputs (not found or unreadable, no row emitted):")
        section.extend(f"- {s}" for s in skipped)
    section_text = "\n".join(section) + "\n"

    if not existing:
        new_content = HEADER + "\n" + section_text
    else:
        new_content = existing.rstrip("\n") + "\n\n" + section_text

    RECEIPTS_PATH.write_text(new_content, encoding="utf-8")
    print(f"Wrote {RECEIPTS_PATH} ({len(rows)} rows, batch {batch_hash}).")
    if skipped:
        print("Skipped:", *skipped, sep="\n  ")
    return validate(new_content) if check_only else 0


def validate(text: str) -> int:
    violations = [tok for tok in BANNED_TOKENS if tok in text]
    if violations:
        print(f"CHECK FAILED: banned tokens present in RECEIPTS.md: {violations}", file=sys.stderr)
        return 1
    print("CHECK OK: no banned tokens in RECEIPTS.md.")
    return 0


def build_json() -> int:
    """Emit webapp/public/receipts.json -- same rows RECEIPTS.md renders, for
    the static /receipts page (webapp is a static export, no live backend)."""
    rows, skipped, used_paths = collect_rows()
    batch_hash = content_hash(used_paths)
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": now,
        "batch_date": today,
        "batch_hash": batch_hash,
        "rows": rows,
        "skipped": skipped,
        "honest_rejects": HONEST_REJECTS,
    }
    text = json.dumps(payload, indent=2)
    violations = [tok for tok in BANNED_TOKENS if tok in text]
    if violations:
        print(f"ABORT: banned tokens present in receipts.json: {violations}", file=sys.stderr)
        return 1
    RECEIPTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPTS_JSON_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {RECEIPTS_JSON_PATH} ({len(rows)} rows, batch {batch_hash}).")
    return 0


def main() -> int:
    check_only = "--check" in sys.argv
    if "--json" in sys.argv:
        return build_json()
    if check_only and RECEIPTS_PATH.exists():
        return validate(RECEIPTS_PATH.read_text(encoding="utf-8"))
    if check_only:
        print("CHECK FAILED: RECEIPTS.md does not exist yet.", file=sys.stderr)
        return 1
    return build(check_only=False)


if __name__ == "__main__":
    raise SystemExit(main())
