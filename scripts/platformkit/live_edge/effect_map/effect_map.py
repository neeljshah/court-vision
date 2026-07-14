"""scripts.platformkit.live_edge.effect_map.effect_map -- claim -> time-grain
EFFECT PROFILE index (Track EFFECT-MAP).

claim_impact.py (tier-1/2 only) and bet_map.py (every claim -> every market
family) answer WHICH markets a claim can move. Neither answers WHEN a claim's
condition is active, or HOW BIG its measured effect is. This module builds
that missing time-grain layer, empirically, from tagged possession/tick
stores already on disk (never re-derives them):

  data/omni/live_edge/grid/tagged_possessions.parquet                (NBA team)
  data/omni/live_edge/player_grid/tagged_player_possessions.parquet  (NBA player)
  data/omni/live_edge/mlb_ingame/tagged_ticks.parquet                (MLB)

All three carry a `period_band` column (NBA: "Q1_early".."OT"; MLB: half x
inning tercile) -- same name/semantics, one routine serves both sports.

Per claim in the P2 ledger (scripts.platformkit.omni.claims_ledger):
  - observable/market_family via bet_map (imported, never edited).
  - effect_size: B4's measured discovered_delta when tick-tested (most
    trustworthy number on disk), else evidence_json's own magnitude field
    (score diff/tail spread/archetype deviation), else honest None.
  - activation_time_profile: empirical dist of period_band among tagged-store
    rows matching scope.context.cell -- computed from data, never asserted.
    No `cell` (pregame/whole-game traits) -> {"whole_game": 1.0}, rate 1.0.
  - tested_verdict: B4 verdict, else not-testable reason, else ledger
    lifecycle (honest fallback, never invented).

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims -- structural + measured-magnitude only.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import tempfile

import pandas as pd

from scripts.platformkit.live_edge.bet_map import bet_map as bm
from scripts.platformkit.omni import claims_ledger as cl

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_OUT_DIR = pathlib.Path("data/omni/live_edge/effect_map")
_OUT_NAME = "effect_profiles.parquet"

_TAGGED_PATHS = {
    "team": REPO_ROOT / "data/omni/live_edge/grid/tagged_possessions.parquet",
    "player": REPO_ROOT / "data/omni/live_edge/player_grid/tagged_player_possessions.parquet",
    "mlb": REPO_ROOT / "data/omni/live_edge/mlb_ingame/tagged_ticks.parquet",
}
_B4_RESULTS = REPO_ROOT / "data/omni/live_edge/replay/full_ledger_results.parquet"
_B4_NOT_TESTABLE = REPO_ROOT / "data/omni/live_edge/replay/full_ledger_not_testable.parquet"

_TIME_COL = "period_band"

# topic-prefix -> which tagged store its scope.context.cell keys match against.
_STORE_FOR_TOPIC = [
    (r"^player_cell\.", "player"),
    (r"^mlb_ingame\.", "mlb"),
    (r"^situation\.", "team"),
]


def _store_key_for_topic(topic: str) -> str | None:
    t = topic or ""
    for pat, key in _STORE_FOR_TOPIC:
        if re.search(pat, t):
            return key
    return None


class _TaggedCache:
    """ponytail: lazy per-process cache -- these are 500k-1.3M row parquet
    files, never reload per-claim. Also caches one groupby PER DISTINCT cell
    key-signature (not per claim): claims share a tiny number of signatures,
    so this turns an O(n_claims x n_rows) scan into O(n_rows)-once + O(1)
    lookups per claim."""
    def __init__(self):
        self._df_cache: dict[str, pd.DataFrame] = {}
        self._group_cache: dict[tuple, tuple[pd.Series, int]] = {}

    def get(self, key: str) -> pd.DataFrame | None:
        if key not in self._df_cache:
            path = _TAGGED_PATHS[key]
            self._df_cache[key] = pd.read_parquet(path) if path.is_file() else pd.DataFrame()
        return self._df_cache[key] if not self._df_cache[key].empty else None

    def grouped(self, store_key: str, key_cols: tuple[str, ...]) -> tuple[pd.Series, int] | None:
        """(size-Series indexed by key_cols + _TIME_COL, total_rows), built
        once per (store, key-signature) and reused by every claim sharing it."""
        sig = (store_key, key_cols)
        if sig not in self._group_cache:
            tagged = self.get(store_key)
            if tagged is None:
                self._group_cache[sig] = None
                return None
            cols = list(key_cols) + ([] if _TIME_COL in key_cols else [_TIME_COL])
            cols = [c for c in cols if c in tagged.columns]
            if not cols:
                self._group_cache[sig] = None
                return None
            g = tagged.groupby(cols, observed=True).size()
            self._group_cache[sig] = (g, len(tagged))
        return self._group_cache[sig]


def activation_profile(cache: _TaggedCache, store_key: str | None, cell: dict) -> tuple[dict, float]:
    """Empirical (dist-of-period_band, activation_rate) for *cell*, backed by
    _TaggedCache's per-signature groupby (built once, shared by every claim
    with the same cell key-signature -- cheap even at 88k-claim ledger scale).
    No store / no matching keys -> honest ({}, 0.0), never guessed."""
    if not cell or store_key is None:
        return {}, 0.0
    key_cols = tuple(k for k in cell if k != _TIME_COL)
    grouped = cache.grouped(store_key, key_cols)
    if grouped is None:
        return {}, 0.0
    g, total = grouped
    if total == 0:
        return {}, 0.0
    key_vals = tuple(cell[k] for k in key_cols)
    if _TIME_COL in cell:
        full_key = key_vals + (cell[_TIME_COL],)
        # single-column groupby -> flat Index, not a 1-tuple MultiIndex
        lookup_key = full_key if len(full_key) > 1 else full_key[0]
        cnt = int(g.get(lookup_key, 0))
        return ({str(cell[_TIME_COL]): 1.0} if cnt else {}), cnt / total
    try:
        sub = g.xs(key_vals, level=list(key_cols)) if key_vals else g
    except KeyError:
        return {}, 0.0
    matched = int(sub.sum())
    if matched == 0:
        return {}, 0.0
    dist = (sub / matched).round(4)
    return {str(k): float(v) for k, v in dist.items()}, matched / total


def _to_float(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def extract_effect_size(evidence: dict) -> tuple[float | None, str]:
    """Best-effort numeric effect magnitude from a claim's own evidence_json.
    Priority: model-comparison score diff > ortho residual > tail spread >
    archetype deviation > honest None (p-value alone carries no size)."""
    scores = evidence.get("scores")
    if isinstance(scores, dict) and "base_err" in scores and "full_err" in scores:
        return float(scores["base_err"]) - float(scores["full_err"]), "base_err_minus_full_err"
    ortho = _to_float(evidence.get("ortho"))
    if ortho is not None:
        return ortho, "ortho"
    q = evidence.get("quantiles")
    if isinstance(q, dict) and "0.95" in q and "0.5" in q:
        return float(q["0.95"]) - float(q["0.5"]), "tail_spread_p95_p50"
    dev = _to_float(evidence.get("deviation_from_archetype"))
    if dev is not None:
        return dev, "deviation_from_archetype"
    return None, "no_size_field"


def _direction(effect_size: float | None) -> str:
    if effect_size is None:
        return "unknown"
    if effect_size > 0:
        return "positive"
    if effect_size < 0:
        return "negative"
    return "flat"


def _out_path(base_dir=None) -> pathlib.Path:
    return (pathlib.Path(base_dir) if base_dir is not None else _OUT_DIR) / _OUT_NAME


def _write_parquet_atomic(path: pathlib.Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".parquet")
    os.close(fd)
    tmp = pathlib.Path(tmp_name)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def _b4_lookup() -> tuple[dict, dict]:
    verdicts, reasons = {}, {}
    if _B4_RESULTS.is_file():
        r = pd.read_parquet(_B4_RESULTS, columns=["claim_id", "verdict"])
        verdicts = dict(zip(r["claim_id"], r["verdict"]))
    if _B4_NOT_TESTABLE.is_file():
        nt = pd.read_parquet(_B4_NOT_TESTABLE, columns=["claim_id", "reason"])
        reasons = dict(zip(nt["claim_id"], nt["reason"]))
    return verdicts, reasons


def build_profiles(sport: str | None = None, claims_base_dir=None, base_dir=None,
                    tagged_cache: _TaggedCache | None = None) -> pd.DataFrame:
    """One EFFECT PROFILE row per ledger claim. Rebuilds + atomic-writes
    data/omni/live_edge/effect_map/effect_profiles.parquet."""
    claims = cl.query(sport=sport, base_dir=claims_base_dir)
    verdicts, reasons = _b4_lookup()
    cache = tagged_cache or _TaggedCache()
    rows = []
    for _, r in claims.iterrows():
        scope = json.loads(r["scope_json"] or "{}")
        evidence = json.loads(r["evidence_json"] or "{}")
        context = scope.get("context")
        cell = context.get("cell", {}) if isinstance(context, dict) else {}
        store_key = _store_key_for_topic(r["topic"]) if cell else None
        if cell:
            time_dist, rate = activation_profile(cache, store_key, cell)
            if not time_dist:
                time_dist, rate = {"unknown": 1.0}, rate
        else:
            time_dist, rate = {"whole_game": 1.0}, 1.0
        effect_size, basis = extract_effect_size(evidence)
        claim_id = r["claim_id"]
        observable = bm.resolve_observable_full(r["topic"])
        families = bm.families_for_observable(observable)
        tested_verdict = verdicts.get(claim_id)
        if tested_verdict is None:
            reason = reasons.get(claim_id)
            tested_verdict = f"NOT_TESTABLE:{reason}" if reason else f"lifecycle:{r['lifecycle']}"
        rows.append({
            "claim_id": claim_id, "topic": r["topic"], "sport": r["sport"],
            "observable": observable, "direction": _direction(effect_size),
            "effect_size": effect_size, "effect_size_basis": basis,
            "activation_time_profile_json": json.dumps(time_dist, sort_keys=True),
            "activation_periods_flat": ";".join(sorted(time_dist.keys())),
            "activation_rate": rate,
            "entity_type": scope.get("entity_type", ""),
            "entity_ids": r["entity_ids_flat"],
            "market_families_flat": ";".join(families),
            "lifecycle": r["lifecycle"], "tested_verdict": tested_verdict,
        })
    cols = ["claim_id", "topic", "sport", "observable", "direction", "effect_size",
            "effect_size_basis", "activation_time_profile_json", "activation_periods_flat",
            "activation_rate", "entity_type", "entity_ids", "market_families_flat",
            "lifecycle", "tested_verdict"]
    df = pd.DataFrame(rows, columns=cols)
    _write_parquet_atomic(_out_path(base_dir), df)
    return df


def load_profiles(base_dir=None) -> pd.DataFrame:
    path = _out_path(base_dir)
    return pd.read_parquet(path) if path.is_file() else build_profiles(base_dir=base_dir)


def _flat_contains(df: pd.DataFrame, col: str, value: str) -> pd.Series:
    pat = rf"(?:^|;){re.escape(value)}(?:;|$)"
    return df[col].str.contains(pat, regex=True, na=False)


def query_by_period(period_band: str, sport: str | None = None,
                     market_family: str | None = None, base_dir=None) -> pd.DataFrame:
    """Which claims CAN bind right now: activation_time_profile includes
    *period_band* (or the claim is whole_game -- always active)."""
    df = load_profiles(base_dir)
    df = df[_flat_contains(df, "activation_periods_flat", period_band) |
            _flat_contains(df, "activation_periods_flat", "whole_game")]
    if sport is not None:
        df = df[df["sport"] == sport]
    if market_family is not None:
        df = df[_flat_contains(df, "market_families_flat", market_family)]
    return df.reset_index(drop=True)


def query_by_market(market_family: str, sport: str | None = None, base_dir=None) -> pd.DataFrame:
    """Which claims inform *market_family*."""
    df = load_profiles(base_dir)
    df = df[_flat_contains(df, "market_families_flat", market_family)]
    if sport is not None:
        df = df[df["sport"] == sport]
    return df.reset_index(drop=True)


def query_by_claim(claim_id: str, base_dir=None) -> dict | None:
    """Full profile for one claim, as a dict (or None if unknown)."""
    df = load_profiles(base_dir)
    hit = df[df["claim_id"] == claim_id]
    return hit.iloc[0].to_dict() if len(hit) else None

__all__ = [
    "activation_profile", "extract_effect_size", "build_profiles", "load_profiles",
    "query_by_period", "query_by_market", "query_by_claim", "_TaggedCache",
]
