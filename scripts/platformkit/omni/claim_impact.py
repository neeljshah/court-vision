"""scripts.platformkit.omni.claim_impact -- claim -> observable -> market-family
impact index (P2 fan-out layer).

One claim affects MANY bets. A foul-trouble claim (minutes_dist observable)
fans out to every player prop, alt line, SGP leg and team total that minutes
can move. This module makes that fan-out explicit and queryable: it walks the
P2 claims ledger (scripts.platformkit.omni.claims_ledger), resolves each
tier-1/tier-2 claim's native observable, and explodes it over a STATIC
observable->market-family map into data/omni/impact/claim_impact_index.parquet
(a rebuildable view, same discipline as claims_ledger.rebuild_parquet -- never
hand-edited).

Extends the node/edge PATTERN already used by
scripts/platformkit/answers/effect_graph.py (structured columns where
available, a fixed keyword-vocabulary fallback for free-text scope/topic,
honest "unmapped" instead of a silent drop) rather than forking it --
effect_graph itself has no claims-ledger edge model to extend (see its own
`# ponytail` note and claims_ledger.flag_downstream's).

Tiered consumption policy (claim aec39d625b4290dc, ledgered 2026-07-14):
tier-1 = accepted, tier-2 = replicated/family_pass. Only these lifecycles are
indexed -- tier-3 (screened) and rejected/proposed/etc. are ledger-only and
excluded here, honestly.

INVARIANTS: pandas/pyarrow + stdlib only. <=300 LOC. ASCII stdout. Never
writes data/registry/. No $/edge claims -- this indexes WHICH markets a claim
can structurally move, not an effect size or a bet recommendation.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import tempfile

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl

_IMPACT_DIR = pathlib.Path("data/omni/impact")
_INDEX_NAME = "claim_impact_index.parquet"

_TIER_BY_LIFECYCLE = {"accepted": 1, "replicated": 2, "family_pass": 2}

# ponytail: OBSERVABLE->FAMILY weights are STRUCTURAL (which families CAN
# move if the observable moves), not effect sizes -- edit freely as new
# market families come online. "unmapped"/"" observables get no families
# (counted honestly below, never guessed).
FAMILIES_BY_OBSERVABLE = {
    "minutes_dist": ["props.pts", "props.reb", "props.ast", "props.threes",
                      "alt_lines.player", "sgp.player_legs", "ingame.player_surface"],
    "usage_share": ["props.pts", "props.shooting", "sgp.player_legs"],
    "shot_quality": ["props.pts", "props.shooting", "sgp.player_legs"],
    "possession_outcome": ["team_total", "spread", "ingame.team"],
    "pace": ["game_total", "team_total"],
    "to_rate": ["team_total", "ingame.team"],
    "game_total": ["game_total"],
    "game_winprob": ["spread", "ingame.team"],
    "availability": ["props.pts", "props.reb", "props.ast", "props.threes",
                      "props.shooting", "alt_lines.player", "sgp.player_legs",
                      "ingame.player_surface", "team_total", "spread"],
}

# Ordered (regex, observable) pairs -- first match against the claim's own
# topic (lowercased) wins. Same fixed-vocabulary-fallback shape as
# effect_graph._OUTCOME_VOCAB: this labels what the row's own topic already
# says, it asserts nothing new. Unmatched -> "unmapped" (honest, not dropped).
_TOPIC_VOCAB = [
    (r"high_foul|foul_vs_low_foul|b2b_vs_rest|home_vs_road|pf_per36|minutes_mediation", "minutes_dist"),
    (r"usage_absorption|^pts$|^a_pts$|age_curve|size_vs_role|conditioning_trend", "usage_share"),
    (r"zone_efg|zone_attempt|halfcourt|spacing_contribution|shot_zone|transition_attempt_share|opp_def_tercile|^shot_quality$", "shot_quality"),
    (r"with_without_teammate|star_sits|era_control|^ppp$|^possession_outcome$", "possession_outcome"),
    (r"injury|load_management|status_transition", "availability"),
]


def resolve_observable(topic: str) -> str:
    """Native observable for *topic* -- exact match against the P3 enum
    first, then the fallback vocabulary, else 'unmapped'."""
    from scripts.platformkit.omni.native_altitude import NATIVE_OBSERVABLES
    if topic in NATIVE_OBSERVABLES:
        return topic
    t = (topic or "").lower()
    for pat, obs in _TOPIC_VOCAB:
        if re.search(pat, t):
            return obs
    return "unmapped"


def _dir(base_dir) -> pathlib.Path:
    return pathlib.Path(base_dir) if base_dir is not None else _IMPACT_DIR


def _index_path(base_dir=None) -> pathlib.Path:
    return _dir(base_dir) / _INDEX_NAME


def _write_parquet_atomic(path: pathlib.Path, df: pd.DataFrame) -> None:
    """tmp-in-same-dir + os.replace -- mirrors claims_ledger._write_parquet_atomic
    (that helper is module-private there too; a third call site should promote
    both into one shared io_atomic parquet helper)."""
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


def impact_index(sport: str | None = None, claims_base_dir=None, base_dir=None) -> pd.DataFrame:
    """Build (or rebuild) the claim->observable->market-family fan-out index
    for every tier-1/tier-2 claim, atomic-write it, and return it."""
    claims = cl.query(sport=sport, base_dir=claims_base_dir)
    rows = []
    for _, r in claims.iterrows():
        tier = _TIER_BY_LIFECYCLE.get(r["lifecycle"])
        if tier is None:
            continue  # tier-3 (screened) / rejected / proposed / etc. -- ledger-only, excluded
        observable = resolve_observable(r["topic"])
        families = FAMILIES_BY_OBSERVABLE.get(observable, [])
        base_row = {
            "claim_id": r["claim_id"], "tier": tier, "sport": r["sport"],
            "entity_ids": r["entity_ids_flat"], "observable": observable,
        }
        if not families:
            rows.append({**base_row, "market_family": ""})
        else:
            for fam in families:
                rows.append({**base_row, "market_family": fam})
    df = pd.DataFrame(rows, columns=["claim_id", "tier", "sport", "entity_ids", "observable", "market_family"])
    _write_parquet_atomic(_index_path(base_dir), df)
    return df


def _read_index(base_dir=None) -> pd.DataFrame:
    path = _index_path(base_dir)
    return pd.read_parquet(path) if path.is_file() else impact_index(base_dir=base_dir)


def affected_bets(entity_id=None, claim_id: str | None = None, base_dir=None) -> pd.DataFrame:
    """The fan-out list: every (observable, market_family) a given entity or
    claim can move. One of entity_id/claim_id must be given."""
    df = _read_index(base_dir)
    if claim_id is not None:
        df = df[df["claim_id"] == claim_id]
    elif entity_id is not None:
        eid = str(entity_id)
        df = df[df["entity_ids"].str.contains(rf"(?:^|;){re.escape(eid)}(?:;|$)", regex=True, na=False)]
    else:
        raise ValueError("affected_bets requires entity_id or claim_id")
    return df.reset_index(drop=True)


def families_for_slate(sport: str, base_dir=None) -> pd.DataFrame:
    """Coverage-of-the-bet-surface view: per market family, the count of
    distinct tier-1/tier-2 claims that can move it, for *sport*."""
    df = _read_index(base_dir)
    df = df[(df["sport"] == sport) & (df["market_family"] != "")]
    if df.empty:
        return pd.DataFrame(columns=["market_family", "n_claims"])
    out = (df.groupby("market_family")["claim_id"].nunique()
           .reset_index(name="n_claims").sort_values("n_claims", ascending=False)
           .reset_index(drop=True))
    return out


__all__ = ["resolve_observable", "impact_index", "affected_bets", "families_for_slate",
           "FAMILIES_BY_OBSERVABLE"]
