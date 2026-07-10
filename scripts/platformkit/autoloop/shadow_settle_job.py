"""scripts.platformkit.autoloop.shadow_settle_job -- forward self-shadowing of
provisional ledger verdicts (autoloop job #9, M09). Every PROVISIONAL /
PREREGISTERED / WAIT-marked row (latest row per hypothesis/candidate_id) in the
prereg + interaction-factory ledgers auto-accrues forward evidence: its
preregistered metric is recomputed on the joined in-game grade corpus
(data/cache/ingame_grade_joined/<sport>/) using ONLY rows strictly AFTER the
ledger row's own as-of date (computed_at) -- leak-free by construction.

A row is shadow-evaluable iff it carries a machine-readable eval spec:
    row["shadow_spec"] = {"metric": "brier_model_minus_market",
                          "corpus": "ingame_grade_joined/<sport>",
                          "bar": {"op": "<=" | ">=", "value": <float>},
                          "min_n": <powered game count>}
plus a parseable computed_at. Rows WITHOUT a usable spec get exactly ONE honest
SHADOW_UNSPECIFIED row naming what is missing -- never a guessed spec.

Outputs are APPEND-ONLY rows in data/cache/intel_claims/shadow/
shadow_settle_ledger.jsonl (kinds: SHADOW_TICK / PROMOTE_CANDIDATE / DEMOTED /
SHADOW_UNSPECIFIED). Deliberately NOT the source ledgers: latest-verdict
readers (e.g. replication_watch) pick the newest row per hypothesis, so a tick
there would shadow out a real verdict; the shadow/ subdir also keeps
validate_new_stores' non-recursive *.jsonl glob away. PROMOTE_CANDIDATE /
DEMOTED are candidate rows only -- promotion/retirement itself stays human.
BLOCKED rows (missing columns/corpora) are excluded: forward accrual of the
same corpus cannot unblock them.

First WIRED shadow: the rung-8 WAIT-FOR-DATA power recheck -- calls
domains.mlb.ingame.rung8_state.rung8_power's own join + required_n at that
module's mid-of-range assumption (never reimplements the math).

Dedup: SHADOW_UNSPECIFIED once per (ledger, key, as_of); SHADOW_TICK only when
the forward n changed; PROMOTE_CANDIDATE/DEMOTED are terminal for that
(ledger, key, as_of) -- a NEW provisional row (new as-of) re-arms shadowing.

WATERMARK (M07 convention): newest mtime across the two ledger files + all
grade-joined jsonl; no watermark yet -> due iff anything exists.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_shadow_settle_job.py -q
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[3]
_INTEL_DIR = _REPO / "data" / "cache" / "intel_claims"
GRADE_ROOT = _REPO / "data" / "cache" / "ingame_grade_joined"
SHADOW_LEDGER_PATH = _INTEL_DIR / "shadow" / "shadow_settle_ledger.jsonl"
LEDGERS: Dict[str, Tuple[Path, str]] = {
    "prereg_hypothesis_ledger": (_INTEL_DIR / "prereg_hypothesis_ledger.jsonl", "hypothesis"),
    "interaction_factory_ledger": (_INTEL_DIR / "interaction_factory_ledger.jsonl", "candidate_id"),
}
_PROVISIONAL_TOKENS = ("PROVISIONAL", "PREREGISTERED", "WAIT")
_SUPPORTED_METRICS = ("brier_model_minus_market",)
_BAR_OPS = ("<=", ">=")
_RUNG8_KEY = ("wired_shadow", "rung8_bullpen_pitchcount_conditioning", "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _latest_provisional_rows(ledger_path: Path, key_field: str) -> Dict[str, Dict[str, Any]]:
    """Latest row per key (computed_at string order, same convention as
    replication_watch); kept iff that LATEST verdict is still provisional."""
    latest: Dict[str, Dict[str, Any]] = {}
    for row in _iter_jsonl(ledger_path):
        key = str(row.get(key_field) or "")
        if not key:
            continue
        if key not in latest or str(row.get("computed_at", "")) > str(latest[key].get("computed_at", "")):
            latest[key] = row
    return {k: r for k, r in latest.items()
            if any(tok in str(r.get("verdict", "")).upper() for tok in _PROVISIONAL_TOKENS)}


def parse_spec(row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """(spec, missing): spec usable iff missing == []. Names EXACTLY what is
    absent/invalid -- never invents a default."""
    missing: List[str] = []
    spec = row.get("shadow_spec")
    if not isinstance(spec, dict):
        return None, ["shadow_spec (machine-readable eval spec: metric/corpus/bar/min_n)"]
    if spec.get("metric") not in _SUPPORTED_METRICS:
        missing.append("shadow_spec.metric (supported: %s)" % ", ".join(_SUPPORTED_METRICS))
    corpus = spec.get("corpus")
    if not (isinstance(corpus, str) and corpus.startswith("ingame_grade_joined/") and corpus.count("/") == 1):
        missing.append("shadow_spec.corpus (form: ingame_grade_joined/<sport>)")
    bar = spec.get("bar")
    if not (isinstance(bar, dict) and bar.get("op") in _BAR_OPS and isinstance(bar.get("value"), (int, float))):
        missing.append("shadow_spec.bar (dict: op in <=/>= plus numeric value)")
    if not isinstance(spec.get("min_n"), (int, float)):
        missing.append("shadow_spec.min_n (powered game-count threshold)")
    if _parse_ts(row.get("computed_at")) is None:
        missing.append("computed_at (as-of date for the leak-free forward cut)")
    return (None, missing) if missing else (spec, [])


def _forward_metric(spec: Dict[str, Any], as_of: datetime, grade_root: Path) -> Dict[str, Any]:
    """Game-clustered paired Brier diff (model minus market) on grade rows
    STRICTLY after as_of -- nothing at/before the as-of is ever read into the
    stat. n = games (ticks within a game are correlated, per rung8 discipline)."""
    sport_dir = grade_root / spec["corpus"].split("/", 1)[1]
    per_game: Dict[str, List[float]] = {}
    if sport_dir.is_dir():
        for f in sorted(sport_dir.glob("*.jsonl")):
            for row in _iter_jsonl(f):
                ts = _parse_ts(row.get("ts"))
                if ts is None or ts <= as_of:
                    continue  # leak-free forward cut
                try:
                    m, mk, y = float(row["model_prob"]), float(row["market_prob"]), float(row["outcome"])
                except (KeyError, TypeError, ValueError):
                    continue
                per_game.setdefault(str(row.get("game_id", f.stem)), []).append((m - y) ** 2 - (mk - y) ** 2)
    vals = [sum(v) / len(v) for v in per_game.values()]
    n = len(vals)
    if n == 0:
        return {"n_forward": 0, "value": None, "ci95": None}
    mean = sum(vals) / n
    if n < 2:
        return {"n_forward": n, "value": round(mean, 6), "ci95": None}
    half = 1.96 * math.sqrt(sum((x - mean) ** 2 for x in vals) / (n - 1) / n)
    return {"n_forward": n, "value": round(mean, 6), "ci95": [round(mean - half, 6), round(mean + half, 6)]}


def _bar_met(bar: Dict[str, Any], value: float) -> bool:
    return value <= bar["value"] if bar["op"] == "<=" else value >= bar["value"]


def _load_shadow_state(path: Path) -> Dict[str, Any]:
    st: Dict[str, Any] = {"unspecified": set(), "terminal": set(), "last_n": {}}
    for row in _iter_jsonl(path):
        k = (row.get("source_ledger"), row.get("key"), row.get("as_of"))
        kind = row.get("kind")
        if kind == "SHADOW_UNSPECIFIED":
            st["unspecified"].add(k)
        elif kind in ("PROMOTE_CANDIDATE", "DEMOTED"):
            st["terminal"].add(k)
        elif kind == "SHADOW_TICK":
            st["last_n"][k] = row.get("n_forward")
    return st


def _append(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _shadow_rung8(state: Dict[str, Any], rec: Callable[[Dict[str, Any]], None], *,
                  join_fn: Optional[Callable[[], Tuple[int, int, List[int]]]] = None) -> Dict[str, Any]:
    """First wired shadow: rung8_power's WAIT-FOR-DATA recheck, via the module
    itself (its join + required_n at its own mid-of-range assumption)."""
    from domains.mlb.ingame.rung8_state import rung8_power as RP
    if _RUNG8_KEY in state["terminal"]:
        return {"status": "terminal"}
    n_total, n_joined, _unmatched = (join_fn or RP.join_to_grade_corpus)()
    delta, sigma = RP._DELTA_GRID[1], RP._SIGMA_GRID[1]  # noqa: SLF001 -- the module's own mid-of-range assumption
    n_req = RP.required_n(delta, sigma)
    powered = n_joined >= n_req
    if state["last_n"].get(_RUNG8_KEY) == n_joined:
        return {"status": "unchanged", "n_joined": n_joined, "powered": powered}
    base = {"source_ledger": _RUNG8_KEY[0], "key": _RUNG8_KEY[1], "sport": "mlb",
            "as_of": _RUNG8_KEY[2], "ts": _now_iso(), "metric": "rung8_joined_games_vs_required_n",
            "edge_claimed": False}
    rec(dict(base, kind="SHADOW_TICK", n_forward=int(n_joined), value=float(n_joined), ci95=None,
             powered=bool(powered), min_n=round(n_req, 1),
             note="rung8_power recheck: %d/%d gumbo games joined; mid-of-range (delta=%s, sigma=%s) needs ~%.0f"
                  % (n_joined, n_total, delta, sigma, n_req)))
    if powered:
        rec(dict(base, kind="PROMOTE_CANDIDATE", n_forward=int(n_joined), powered=True,
                 note="powered at rung8_power's mid-of-range assumption -- measurement unblocked; "
                      "running it + any promotion stays human"))
    return {"status": "ticked", "n_joined": n_joined, "powered": powered}


def _watermark_mtime(ledgers: Dict[str, Tuple[Path, str]], grade_root: Path) -> Optional[float]:
    paths = [p for p, _k in ledgers.values() if p.is_file()]
    if grade_root.is_dir():
        paths += list(grade_root.rglob("*.jsonl"))
    mtimes = [p.stat().st_mtime for p in paths]
    return max(mtimes) if mtimes else None


def run_shadow_settle(watermarks: Dict[str, Any], *,
                      ledgers: Optional[Dict[str, Tuple[Path, str]]] = None,
                      shadow_path: Optional[Path] = None,
                      grade_root: Optional[Path] = None,
                      rung8_join_fn: Optional[Callable[[], Tuple[int, int, List[int]]]] = None
                      ) -> Dict[str, Any]:
    """One shadow-settle pass: watermark-gated, shadow-ledger-append ONLY.
    Never flips a flag, never edits the source ledgers, never claims an edge."""
    led = ledgers if ledgers is not None else LEDGERS
    spath = Path(shadow_path) if shadow_path is not None else SHADOW_LEDGER_PATH
    groot = Path(grade_root) if grade_root is not None else GRADE_ROOT
    wm_key = "M09_shadow_settle"
    mtime = _watermark_mtime(led, groot)
    prior = float((watermarks.get(wm_key) or {}).get("corpus_mtime", -1.0))
    if mtime is None or mtime <= prior:
        return {"status": "skipped", "corpus_mtime": mtime, "watermark": prior}
    state = _load_shadow_state(spath)
    appended = {"SHADOW_TICK": 0, "PROMOTE_CANDIDATE": 0, "DEMOTED": 0, "SHADOW_UNSPECIFIED": 0}

    def _rec(row: Dict[str, Any]) -> None:
        _append(spath, row)
        appended[row["kind"]] += 1

    out: Dict[str, Any] = {}
    try:
        out["rung8"] = _shadow_rung8(state, _rec, join_fn=rung8_join_fn)
    except Exception as exc:  # noqa: BLE001 -- wired shadow failing must not block the ledger scan
        out["rung8"] = {"status": "error", "error": str(exc)[:200]}
    scanned = 0
    errors: List[Dict[str, str]] = []
    for lname, (lpath, kfield) in led.items():
        for key, row in sorted(_latest_provisional_rows(lpath, kfield).items()):
            scanned += 1
            try:
                as_of = str(row.get("computed_at", ""))
                sk = (lname, key, as_of)
                if sk in state["terminal"]:
                    continue
                spec, missing = parse_spec(row)
                if spec is None:
                    if sk not in state["unspecified"]:
                        _rec({"kind": "SHADOW_UNSPECIFIED", "source_ledger": lname, "key": key,
                              "sport": row.get("sport"), "as_of": as_of, "ts": _now_iso(),
                              "edge_claimed": False,
                              "note": "no machine-readable eval spec -- missing: " + "; ".join(missing)})
                    continue
                m = _forward_metric(spec, _parse_ts(as_of), groot)
                if state["last_n"].get(sk) == m["n_forward"]:
                    continue
                powered = m["n_forward"] >= float(spec["min_n"])
                tick = {"kind": "SHADOW_TICK", "source_ledger": lname, "key": key,
                        "sport": row.get("sport"), "as_of": as_of, "ts": _now_iso(),
                        "metric": spec["metric"], "n_forward": int(m["n_forward"]),
                        "value": m["value"], "ci95": m["ci95"], "powered": bool(powered),
                        "min_n": spec["min_n"], "bar": spec["bar"], "edge_claimed": False,
                        "note": "forward corpus strictly after as-of only (leak-free by construction)"}
                _rec(tick)
                if powered and m["value"] is not None:
                    kind = "PROMOTE_CANDIDATE" if _bar_met(spec["bar"], m["value"]) else "DEMOTED"
                    _rec(dict(tick, kind=kind,
                              note="preregistered bar %s %s %s at powered forward n=%d -- candidate row only; "
                                   "promotion/retirement stays human"
                                   % (spec["bar"]["op"], spec["bar"]["value"],
                                      "MET" if kind == "PROMOTE_CANDIDATE" else "NOT met", m["n_forward"])))
            except Exception as exc:  # noqa: BLE001 -- one malformed row must not block the scan
                errors.append({"key": key, "error": str(exc)[:160]})
    watermarks[wm_key] = {"corpus_mtime": mtime, "last_run_ts": _now_iso()}
    out.update({"status": "ran", "provisional_scanned": scanned, "appended": appended,
                "row_errors": errors, "shadow_ledger": str(spath)})
    return out


__all__ = ["run_shadow_settle", "parse_spec", "LEDGERS", "SHADOW_LEDGER_PATH", "GRADE_ROOT"]
