"""Descriptive local effect of a declared soccer/tennis mechanism trigger.

Each declared trigger column is measured against the DEVIGGED CLOSE carried by
``eval_gate.close_join.gate_corpus_states``: the close residual
(``outcome - devig_close_prob``) is compared between the high and low halves of
the trigger, per ``corpus_unit`` (tennis ATP and WTA are NEVER pooled). A row
whose declared column is absent from the scored corpus is NOT_TESTABLE with the
column named -- never dropped.

Verdict vocabulary, exactly as the NBA/MLB wiring uses it:
``CONFIRMED_LOCAL`` / ``NULL_LOCAL`` / ``NOT_TESTABLE``.

CONFIRMED_LOCAL is a DESCRIPTIVE LOCAL EFFECT on a frozen corpus whose close
carries a SYNTHETIC vintage (S34). It is NOT a scored claim, NOT walk-forward,
and NOT charged to any ledger -- a scored verdict would require a charged trial.
DESCRIPTIVE_ONLY; no dollar or ROI claim anywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy import stats

from scripts.platformkit.analytics_showcase import mechanism_wiring_soccer, mechanism_wiring_tennis
from scripts.platformkit.combo.corpus_cache import load_gate_corpus
from scripts.platformkit.eval_gate import close_join

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).parent / "out"
# Declared bars, copied from the soccer/tennis mechanism ledgers' own house
# convention (|effect| >= 0.02 AND p < 0.01). They are never lowered here.
ALPHA = 0.01
MIN_EFFECT = 0.02
# A trigger covering less of the scored corpus than this is a base-rate split
# wearing the column's name, so the row stays NOT_TESTABLE.
MIN_COVERAGE = 0.25
MIN_UNIT_ROWS = 30
WINDOW = {"soccer": ("2015-01-01", "2026-12-31"), "tennis": ("2014-01-01", "2026-12-31")}
WIRING = {"soccer": mechanism_wiring_soccer.WIRING, "tennis": mechanism_wiring_tennis.WIRING}
CORPUS = {"soccer": mechanism_wiring_soccer.CORPUS, "tennis": mechanism_wiring_tennis.CORPUS}
_BANNED = ("home_win", "outcome", "y", "devig_close_prob", "truth_wp")


def corpus_frame(sport: str) -> pd.DataFrame:
    """States carrying the devigged close, joined to the gate corpus features."""
    states = close_join.gate_corpus_states(sport, *WINDOW[sport])
    base = pd.DataFrame([{"event_id": row["game_id"], "game_date": row["game_date"],
                          "outcome": row["outcome"], "devig_close_prob": row["devig_close_prob"],
                          "vintage": row["vintage"]} for row in states])
    corpus = load_gate_corpus(sport).copy()
    corpus["event_id"] = corpus["event_id"].astype(str)
    frame = base.merge(corpus.drop(columns=["y"]), on="event_id", how="left", validate="one_to_one")
    frame["residual"] = frame["outcome"].astype(float) - frame["devig_close_prob"].astype(float)
    return frame


def trigger_values(frame: pd.DataFrame, spec: dict) -> tuple[pd.Series | None, list[str]]:
    """Evaluate one declared trigger; return (values, missing declared columns)."""
    missing = [name for name in spec["columns"] if name not in frame.columns]
    if missing:
        return None, missing
    # ponytail: the guard, not the ceremony -- an outcome column inside a
    # trigger expression is the one way this table could stop being descriptive.
    for banned in _BANNED:
        assert banned not in spec["expr"].split(), "trigger expression reads an outcome"
    values = pd.to_numeric(frame.eval(spec["expr"], engine="python"), errors="coerce")
    if spec.get("mask"):
        values = values.where(frame.eval(spec["mask"], engine="python").astype(bool))
    return values, []


def unit_effect(values: pd.Series, residual: pd.Series,
                dates: pd.Series | None = None) -> dict:
    """High-vs-low-half close-residual difference for ONE corpus_unit.

    S50: the concatenated gate frame is not globally chronological (tennis ATP
    rows precede WTA and the date jumps backwards at the boundary), so every
    measurement here is taken inside a single corpus_unit and the unit's own
    date range is reported alongside it. Nothing is ever scored across units.
    """
    keep = values.notna() & residual.notna()
    vals, resid = values[keep], residual[keep]
    row: dict = {"n": int(len(vals))}
    if dates is not None and keep.any():
        span = sorted(dates[keep].astype(str))
        row["date_range"] = [span[0], span[-1]]
    if not len(vals):
        return {**row, "verdict": "NOT_TESTABLE",
                "reason": "the declared trigger column is entirely null in this corpus_unit"}
    if len(vals) < 2 * MIN_UNIT_ROWS:
        return {**row, "verdict": "NOT_TESTABLE", "reason": "fewer than %d scored rows in this "
                "corpus_unit" % (2 * MIN_UNIT_ROWS)}
    high = vals > vals.median()
    if min(int(high.sum()), int((~high).sum())) < MIN_UNIT_ROWS:
        high = vals >= vals.median()  # ties pile on the median; inclusive fallback
    if min(int(high.sum()), int((~high).sum())) < MIN_UNIT_ROWS:
        return {**row, "verdict": "NOT_TESTABLE",
                "reason": "trigger is degenerate here: no split of at least %d rows a side"
                          % MIN_UNIT_ROWS}
    top, bottom = resid[high].to_numpy(float), resid[~high].to_numpy(float)
    effect = float(top.mean() - bottom.mean())
    p_value = float(stats.ttest_ind(top, bottom, equal_var=False).pvalue)
    confirmed = abs(effect) >= MIN_EFFECT and p_value < ALPHA
    return {**row, "n_high": int(high.sum()), "n_low": int((~high).sum()),
            "effect": round(effect, 6), "p_value": p_value,
            "verdict": "CONFIRMED_LOCAL" if confirmed else "NULL_LOCAL"}


def measure(slug: str, spec: dict, frame: pd.DataFrame) -> dict:
    """One declared mechanism -> one verdict, with its per-corpus_unit detail."""
    row = {"mechanism_id": slug, "trigger": spec["expr"], "mask": spec.get("mask"),
           "source_artifact": spec["source"] or "(none)", "corpus_units": {}}
    if not spec["expr"]:
        return {**row, "verdict": "NOT_TESTABLE", "n": 0, "reason": spec["reason"]}
    values, missing = trigger_values(frame, spec)
    if missing:
        return {**row, "verdict": "NOT_TESTABLE", "n": 0,
                "reason": "declared column(s) absent from the scored corpus: " + ", ".join(missing)}
    covered = int(values.notna().sum())
    share = round(covered / len(frame), 4) if len(frame) else 0.0
    row.update({"n": covered, "coverage_share": share, "note": spec.get("note")})
    if share < MIN_COVERAGE:
        return {**row, "verdict": "NOT_TESTABLE",
                "reason": "trigger covers %d of %d scored rows (%.2f), below the declared %.2f bar"
                          % (covered, len(frame), share, MIN_COVERAGE)}
    units = {str(unit): unit_effect(values[mask], frame.loc[mask, "residual"],
                                    frame.loc[mask, "game_date"])
             for unit, mask in ((unit, frame["corpus_unit"].eq(unit))
                                for unit in sorted(frame["corpus_unit"].dropna().unique()))}
    row["corpus_units"] = units
    scored = [unit for unit in units.values() if unit["verdict"] != "NOT_TESTABLE"]
    if not scored:
        return {**row, "verdict": "NOT_TESTABLE",
                "reason": "no corpus_unit carries enough scored rows for this trigger"}
    signs = {unit["effect"] > 0 for unit in scored}
    every = all(unit["verdict"] == "CONFIRMED_LOCAL" for unit in scored) and len(signs) == 1
    return {**row, "verdict": "CONFIRMED_LOCAL" if every else "NULL_LOCAL",
            "n": sum(unit["n"] for unit in scored), "corpus_units_scored": len(scored),
            # Honest label when only one corpus_unit could carry the trigger.
            "single_corpus_unit": len(scored) < len(units),
            "n_by_corpus_unit": {unit: cell["n"] for unit, cell in units.items()}}


def prereg_rows(sport: str) -> list[dict]:
    """Declare every mechanism and its trigger BEFORE any effect is computed."""
    return [{"mechanism_id": slug, "trigger": spec["expr"], "mask": spec.get("mask"),
             "columns": list(spec.get("columns", ())), "source_artifact": spec["source"] or "(none)",
             "planned": "descriptive_effect" if spec["expr"] else "NOT_TESTABLE",
             "alpha": ALPHA, "min_effect": MIN_EFFECT, "min_coverage": MIN_COVERAGE}
            for slug, spec in WIRING[sport].items()]


def build(sport: str, frame: pd.DataFrame | None = None) -> dict:
    """Every declared row reaches a verdict; nothing is charged to any ledger."""
    declared = prereg_rows(sport)
    seal = hashlib.sha256(json.dumps(declared, sort_keys=True).encode("ascii")).hexdigest()
    frame = corpus_frame(sport) if frame is None else frame
    rows = [measure(slug, spec, frame) for slug, spec in WIRING[sport].items()]
    verdicts: dict[str, int] = {}
    for row in rows:
        verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
    vintage = sorted(set(frame["vintage"])) if len(frame) else ["SYNTHETIC"]
    return {"label": "DESCRIPTIVE_ONLY", "edge_claimed": False,
            "not_a_claim": "CONFIRMED_LOCAL is a descriptive local effect on a frozen corpus with "
                           "a SYNTHETIC-vintage close (S34); it is uncharged and not walk-forward, "
                           "so it is not a scored claim.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": str(frame["game_date"].max()) if len(frame) else None,
            "vintage": vintage, "prereg_sha256": seal,
            "corpus": {"sport": sport, "description": CORPUS[sport],
                       "start": WINDOW[sport][0], "end": WINDOW[sport][1],
                       "n_scored_rows": int(len(frame))},
            "bars": {"alpha": ALPHA, "min_effect": MIN_EFFECT, "min_coverage": MIN_COVERAGE,
                     "min_unit_rows": MIN_UNIT_ROWS},
            "counts": {"mechanisms": len(rows), "wired": len(rows),
                       "with_trigger": sum(1 for row in rows if row["trigger"]),
                       "not_testable": sum(1 for row in rows if row["verdict"] == "NOT_TESTABLE"),
                       "by_verdict": verdicts},
            "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="descriptive mechanism effects vs the close")
    parser.add_argument("--sport", default="tennis", choices=sorted(WIRING))
    args = parser.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prereg = OUT_DIR / ("mechanism_wiring_prereg_%s.json" % args.sport)
    prereg.write_text(json.dumps(prereg_rows(args.sport), indent=2, ensure_ascii=True),
                      encoding="ascii")
    print("prereg written before any effect:", prereg)
    result = build(args.sport)
    out = OUT_DIR / ("mechanism_wiring_%s.json" % args.sport)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    for row in result["rows"]:
        detail = " ".join("%s n=%d eff=%s p=%s" % (unit, cell["n"], cell.get("effect"),
                                                   cell.get("p_value"))
                          for unit, cell in row["corpus_units"].items())
        print("%-52s %-15s n=%-6d %s" % (row["mechanism_id"][:52], row["verdict"], row["n"],
                                         detail or (row.get("reason") or "")[:70]))
    print("counts", json.dumps(result["counts"]))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
