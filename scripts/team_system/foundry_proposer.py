"""FOUNDRY PROPOSER -- the V3 self-improvement engine that proposes candidate compositional signals,
validates each cross-season via cluster_lab, applies batch FDR + family anti-re-roll, registers the
REPLICATES survivors, and appends EVERY result (survivor or reject) to a coverage scoreboard.

This is the loop's SELF-IMPROVEMENT machinery. It is deliberately RESULT-AGNOSTIC: the deliverable is the
machinery + an honest coverage map, NOT a manufactured survivor. The possession-STATE grain is SATURATED
(scout report 2026-06-08); the only true >=2-season corpus is legacy_possessions (possession grain). So
the EXPECTED outcome is that most/all candidates REJECT -- that is a correct result, recorded as such.

  --- THE NON-NEGOTIABLE DISCIPLINE (encoded here, not just documented) ---
  VALIDATION IS SACRED  cross-season via cluster_lab.validate_cluster only. A cluster REPLICATES iff its
                        relative OOS RMSE delta < -NOISE_FLOOR (-0.002) in >= 2 INDEPENDENT seasons. A
                        single-season "lift" is the artifact trap (feedback_single_fold_lifts_are_artifacts)
                        -> recorded as verdict 'single-season' / coverage 'N-A-no-substrate', NEVER registered.
  FDR OVER THE BATCH    every candidate's cross-season evidence is mapped to a one-sided p-value and the whole
                        batch goes through gates.gate_a_batch (Benjamini-Yekutieli, dependency-robust) so you
                        cannot free-roll combos into significance.
  FAMILY ANTI-RE-ROLL   gate_a_batch carries a previously-tested family's prior p forward (no fresh test) and
                        the test log is append-only -- a rejected family cannot be re-proposed until it passes.
  NO SINGLE-WINDOW      a candidate is only a SURVIVOR if it is BOTH cluster-REPLICATES AND clears batch FDR.
  PSEUDO-REPL GUARD     inherited from cluster_lab: a corpus without >=2 of the requested seasons returns
                        verdict 'insufficient-seasons' and can never register.

This module IMPORTS cluster_lab + the registry read-only; it never edits them. It only WRITES its own
coverage scoreboard (data/registry/foundry_scoreboard/) and the shared append-only test log via gates.

  from foundry_proposer import run_candidates, CANDIDATES
  report = run_candidates(CANDIDATES)        # validate the V3 batch, FDR, register survivors, scoreboard
  python scripts/team_system/foundry_proposer.py            # run the V3 batch + print the coverage map
"""
from __future__ import annotations

import math
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "signals"))

from registry.ids import family_key  # noqa: E402
from registry.store import REGISTRY_DIR, registry_lock  # noqa: E402
from signals import cluster_lab  # noqa: E402  (read-only import; never edited)
from signals.gates import gate_a_batch  # noqa: E402

LEGACY_POSSESSIONS = os.path.join(
    REGISTRY_DIR, os.pardir, "cache", "team_system", "legacy_possessions.parquet")
SCOREBOARD_DIR = os.path.join(REGISTRY_DIR, "foundry_scoreboard")
ALPHA = 0.05
NOISE_FLOOR = cluster_lab.NOISE_FLOOR  # -0.002 relative-RMSE bar, single source of truth


# ===========================================================================
# CANDIDATE SCHEMA
# ===========================================================================
# A candidate is a plain dict. run_candidates() consumes a list of these. Required + optional keys:
#
#   name          str   human-readable id for the candidate (unique within the batch, e.g.
#                       "possession.seq.prev_scored_x_dead_ball").
#   corpus        str   absolute or repo-relative path to a >=2-season parquet with `gid`, `season`,
#                       the `base`/`signals` feature columns, and the `target`. The ONLY validated
#                       2-season possession corpus is legacy_possessions; pass others at your own risk.
#   base          list  baseline feature columns (the control model). Must already exist in the corpus
#                       OR be produced by `derive` (below). The cluster lift is measured vs THIS baseline.
#   signals       list  the signal feature columns to test AS A CLUSTER on top of base. These are the
#                       new variables; they may be raw columns or derived (see `derive`).
#   domain        str   the domain_tag the survivor would register under (e.g. "possession_sequence").
#                       Pick a NEW domain for un-mined families; do not reuse a saturated state-5 domain.
#   scope         str   entity_scope ("possession" for legacy_possessions). Part of the model identity.
#   hypothesis    str   ONE-LINE causal hypothesis (why this could carry signal). Recorded for the map.
#   --- optional ---
#   derive        callable(df)->df  pure transform run on the corpus BEFORE validation, to MATERIALIZE
#                       interaction / sequence columns the corpus doesn't store (e.g. df["dur_x_to"] =
#                       df.poss_dur * df.after_to). MUST add exactly the columns named in base+signals
#                       that aren't already present, and MUST NOT use the target. Default: identity.
#   engine_node   str   where a survivor plugs into an engine (recorded on the registered model). Default "".
#   target        str   regression target column. Default "pts" (cluster_lab applies its pts<=4 filter).
#   seasons       tuple  the >=2 independent seasons to require/score. Default ("2022-23","2023-24")
#                       (the only two FULL legacy_possessions seasons; 2024-25/2025-26 are <10k stubs).
#   min_games     int   min distinct games per season to score that season. Default 50.
#   transform_chain list  the transform-family shape (numeric params stripped) used to compute the
#                       family_key anti-re-roll key. Default: derived from `signals` names. Two candidates
#                       in the SAME family share a key and cannot both get a fresh test.
#   source        str   provenance tag for the family_key (default "pbp_possession").
#
# A candidate is a SURVIVOR iff: cluster_lab verdict == "REPLICATES"  AND  it clears batch FDR.
# Anything else is an honest reject, recorded with a coverage class (below).


# ===========================================================================
# p-value from cross-season replication evidence
# ===========================================================================
def _replication_pvalue(per_season: Dict[str, dict], seasons: Sequence[str]) -> float:
    """Map a candidate's per-season cluster evidence to ONE one-sided p-value for batch FDR.

    The cluster_rels are relative OOS-RMSE deltas (negative == the cluster HELPS). We want small p exactly
    when the cluster reliably helps across INDEPENDENT seasons. We model each season's relative delta as a
    draw whose 'null' (no real signal) is centered at 0 with a conservative spread set by the noise floor,
    and combine the per-season one-sided tail probabilities by Fisher's method. This is intentionally
    CONSERVATIVE: a single negative season cannot drive a small p (it is one of >=2 required tails), and a
    near-floor wobble stays insignificant. It does NOT replace cluster_lab's REPLICATES gate -- it is the
    SECOND, batch-level filter so that across a multi-candidate batch you cannot free-roll into significance.
    """
    rels = [per_season[s]["cluster_rel"] for s in seasons
            if s in per_season and "cluster_rel" in per_season[s]]
    if len(rels) < 2:
        return 1.0  # cannot certify cross-season -> maximally non-significant
    # one-sided per-season p: how surprising is a delta this negative under a null centered at 0 with
    # scale = NOISE_FLOOR (so a delta exactly at the floor sits ~1 sd into the helping tail).
    scale = NOISE_FLOOR
    from scipy import stats
    per = []
    for r in rels:
        z = -r / scale  # positive z when the cluster helps (r negative)
        per.append(float(stats.norm.sf(z)))  # one-sided tail toward "helps"
    per = np.clip(np.asarray(per, float), 1e-12, 1.0)
    chi = -2.0 * float(np.sum(np.log(per)))  # Fisher combine
    p = float(stats.chi2.sf(chi, df=2 * len(per)))
    return float(np.clip(p, 0.0, 1.0))


def _candidate_family_key(c: Dict[str, Any]) -> str:
    """Anti-re-roll family key for a candidate (grain+entity+transform-family, numeric params stripped)."""
    chain = c.get("transform_chain")
    if not chain:
        # default transform family = the sorted signal column names (param-stripped by family_key's regex)
        chain = sorted(str(s) for s in c["signals"])
    return family_key(dict(
        grain="possession",
        entity_scope=c.get("scope", "possession"),
        domain_tags=[c["domain"]],
        transform_chain=chain,
        source=c.get("source", "pbp_possession"),
    ))


# ===========================================================================
# scoreboard (append-only; our OWN artifact, never edits the registries)
# ===========================================================================
def _scoreboard_parts() -> List[str]:
    if not os.path.isdir(SCOREBOARD_DIR):
        return []
    return sorted(f for f in os.listdir(SCOREBOARD_DIR)
                  if f.startswith("part-") and f.endswith(".parquet"))


def scoreboard() -> pd.DataFrame:
    """The full coverage scoreboard (every candidate ever run through the foundry, survivor OR reject)."""
    parts = _scoreboard_parts()
    cols = ["name", "domain", "scope", "signals", "hypothesis", "family_key", "coverage_class",
            "verdict", "n_replicate", "cluster_rels", "best_single", "p", "fdr_survivor",
            "registered_model_id", "batch_id", "asof", "detail"]
    if not parts:
        return pd.DataFrame(columns=cols)
    return pd.concat([pd.read_parquet(os.path.join(SCOREBOARD_DIR, p)) for p in parts],
                     ignore_index=True)


def _append_scoreboard(rows: List[dict]) -> None:
    if not rows:
        return
    os.makedirs(SCOREBOARD_DIR, exist_ok=True)
    with registry_lock():
        seq = len(_scoreboard_parts())
        part = os.path.join(SCOREBOARD_DIR, f"part-{seq:06d}-{int(time.time()*1000)%1000000:06d}.parquet")
        tmp = part + ".tmp"
        # stringify list-valued cols so the parquet schema is stable across batches
        df = pd.DataFrame(rows)
        for col in ("signals", "cluster_rels"):
            if col in df.columns:
                df[col] = df[col].apply(lambda v: ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else v)
        df.to_parquet(tmp, index=False)
        os.replace(tmp, part)


# ===========================================================================
# coverage classification (the honest map)
# ===========================================================================
def _coverage_class(cluster_res: dict, fdr_survivor: bool) -> str:
    """Map a (cluster verdict, FDR) pair to a single coverage label for the map. Honest by construction:
    only a cluster-REPLICATES candidate that ALSO clears batch FDR is a 'SURVIVOR'."""
    v = cluster_res.get("verdict")
    if v == "insufficient-seasons" or cluster_res.get("pseudo_replication_blocked"):
        return "data-blocked"                 # corpus lacks >=2 independent seasons
    if "skip-fewgames" in str(cluster_res.get("per_season")):
        return "data-blocked"
    if v == "REPLICATES":
        return "SURVIVOR" if fdr_survivor else "replicates-but-FDR-culled"
    if v == "single-season":
        return "N-A-no-substrate"             # the artifact trap: 1 season is NOT a survivor
    return "mined-reject"                      # does-NOT-replicate: tested, honestly rejected


# ===========================================================================
# the engine
# ===========================================================================
def run_candidates(candidates: List[Dict[str, Any]], alpha: float = ALPHA,
                   procedure: str = "by", batch_id: str = "",
                   register: bool = True, corpus_default: str = LEGACY_POSSESSIONS,
                   verbose: bool = True) -> Dict[str, Any]:
    """Validate a BATCH of candidate compositional signals cross-season, apply batch FDR + family
    anti-re-roll, register the REPLICATES survivors, and append every result to the coverage scoreboard.

    For each candidate {corpus, base, signals, domain, scope, ...}:
      1. (optional) run `derive(df)` to materialize interaction/sequence columns,
      2. call cluster_lab.validate_cluster(... register=False) cross-season (REPLICATES needs rel<-0.002
         in >=2 independent seasons; the pseudo-replication guard blocks single-season corpora),
      3. map the per-season evidence to a one-sided p-value (Fisher-combined).
    Then the WHOLE batch goes through gates.gate_a_batch (Benjamini-Yekutieli FDR + family anti-re-roll +
    append-only test log). A candidate is a SURVIVOR iff cluster=REPLICATES AND it clears batch FDR; only
    survivors are registered (via the SAME registry path validate_cluster uses, register=True). Every
    candidate -- survivor or reject -- is appended to the foundry scoreboard with its coverage class.

    Returns a report dict: {batch_id, n, n_replicates, n_fdr_survivors, n_registered, survivors,
    coverage_counts, results:[per-candidate dicts]}.
    """
    batch_id = batch_id or f"foundry_{int(time.time())}"
    asof = time.strftime("%Y-%m-%dT%H:%M:%S")
    per_candidate: List[dict] = []

    # ---- pass 1: cross-season validate each candidate, collect cluster verdict + p-value ----
    fdr_inputs: List[dict] = []
    for c in candidates:
        name = c["name"]
        corpus = c.get("corpus", corpus_default)
        fk = _candidate_family_key(c)
        cl_res: Dict[str, Any]
        p_val: float
        try:
            if "derive" in c and c["derive"] is not None:
                # materialize derived columns into a STAGING copy on disk so cluster_lab reads them by path
                # (cluster_lab takes a corpus_path, not a frame). Pure transform; target untouched.
                df = pd.read_parquet(corpus)
                df = c["derive"](df)
                staging = os.path.join(SCOREBOARD_DIR, f".derived_{batch_id}_{abs(hash(name)) % 10**8}.parquet")
                os.makedirs(SCOREBOARD_DIR, exist_ok=True)
                df.to_parquet(staging, index=False)
                read_path = staging
            else:
                read_path = corpus
            cl_res = cluster_lab.validate_cluster(
                read_path, base=list(c["base"]), signals=list(c["signals"]),
                domain=c["domain"], scope=c.get("scope", "possession"),
                engine_node=c.get("engine_node", ""), target=c.get("target", "pts"),
                seasons=tuple(c.get("seasons", ("2022-23", "2023-24"))),
                min_games=c.get("min_games", 50),
                register=False,  # NEVER register in pass 1 -- only AFTER FDR
                method=c.get("method", "cluster_hgb_oos"))
            p_val = _replication_pvalue(cl_res.get("per_season", {}),
                                        tuple(c.get("seasons", ("2022-23", "2023-24"))))
        except Exception as exc:  # a malformed candidate must not crash the batch
            cl_res = dict(verdict="error", per_season={}, cluster_rels=[], best_single=0.0,
                          n_replicate=0, signals=list(c["signals"]),
                          detail=f"{type(exc).__name__}: {str(exc)[:200]}")
            p_val = 1.0
        finally:
            stg = os.path.join(SCOREBOARD_DIR, f".derived_{batch_id}_{abs(hash(name)) % 10**8}.parquet")
            if os.path.exists(stg):
                try:
                    os.remove(stg)
                except OSError:
                    pass

        per_candidate.append(dict(c=c, name=name, family_key=fk, cluster=cl_res, p=p_val))
        fdr_inputs.append(dict(hash=name, family_key=fk,
                               definition=f"{c['domain']}/{c.get('scope','possession')}:{sorted(c['signals'])}",
                               p=p_val))
        if verbose:
            cluster_lab._print(cl_res) if cl_res.get("verdict") != "error" else \
                print(f"=== CLUSTER LAB: {name} ERROR: {cl_res.get('detail')} ===")

    # ---- pass 2: batch FDR over the candidate p-values (BY default; family anti-re-roll inside) ----
    fdr = gate_a_batch(fdr_inputs, alpha=alpha, procedure=procedure, batch_id=batch_id)
    survived_names = {s["hash"] for s in fdr["survivors"]}

    # ---- pass 3: register survivors (cluster REPLICATES AND cleared FDR), build scoreboard rows ----
    survivors, sb_rows, registered = [], [], 0
    coverage_counts: Dict[str, int] = {}
    for pc in per_candidate:
        c, cl_res = pc["c"], pc["cluster"]
        fdr_survivor = pc["name"] in survived_names
        cov = _coverage_class(cl_res, fdr_survivor)
        coverage_counts[cov] = coverage_counts.get(cov, 0) + 1
        reg_mid: Optional[str] = None
        is_survivor = (cl_res.get("verdict") == "REPLICATES") and fdr_survivor
        if is_survivor and register:
            # register via the SAME path validate_cluster uses (re-run with register=True is the cleanest
            # way to go through its identical model_id + Registry().register code; corpus already validated).
            corpus = c.get("corpus", corpus_default)
            read_path = corpus
            staging = None
            if c.get("derive") is not None:
                df = c["derive"](pd.read_parquet(corpus))
                staging = os.path.join(SCOREBOARD_DIR, f".reg_{batch_id}_{abs(hash(pc['name'])) % 10**8}.parquet")
                os.makedirs(SCOREBOARD_DIR, exist_ok=True)
                df.to_parquet(staging, index=False)
                read_path = staging
            try:
                reg_res = cluster_lab.validate_cluster(
                    read_path, base=list(c["base"]), signals=list(c["signals"]),
                    domain=c["domain"], scope=c.get("scope", "possession"),
                    engine_node=c.get("engine_node", ""), target=c.get("target", "pts"),
                    seasons=tuple(c.get("seasons", ("2022-23", "2023-24"))),
                    min_games=c.get("min_games", 50), register=True,
                    method=c.get("method", "cluster_hgb_oos"))
                reg_mid = reg_res.get("registered_model_id")
                if reg_mid:
                    registered += 1
            finally:
                if staging and os.path.exists(staging):
                    try:
                        os.remove(staging)
                    except OSError:
                        pass
        if is_survivor:
            survivors.append(dict(name=pc["name"], domain=c["domain"], model_id=reg_mid,
                                  cluster_rels=cl_res.get("cluster_rels")))
        sb_rows.append(dict(
            name=pc["name"], domain=c["domain"], scope=c.get("scope", "possession"),
            signals=list(c["signals"]), hypothesis=c.get("hypothesis", ""),
            family_key=pc["family_key"], coverage_class=cov, verdict=cl_res.get("verdict"),
            n_replicate=cl_res.get("n_replicate", 0), cluster_rels=cl_res.get("cluster_rels", []),
            best_single=cl_res.get("best_single"), p=round(pc["p"], 6), fdr_survivor=bool(fdr_survivor),
            registered_model_id=reg_mid, batch_id=batch_id, asof=asof,
            detail=cl_res.get("detail", "") or _coverage_class(cl_res, fdr_survivor)))
    _append_scoreboard(sb_rows)

    report = dict(batch_id=batch_id, n=len(candidates),
                  n_replicates=sum(1 for pc in per_candidate if pc["cluster"].get("verdict") == "REPLICATES"),
                  n_fdr_survivors=len(survived_names), n_registered=registered,
                  survivors=survivors, coverage_counts=coverage_counts,
                  procedure=procedure, alpha=alpha,
                  results=[dict(name=pc["name"], verdict=pc["cluster"].get("verdict"),
                                p=round(pc["p"], 6),
                                cluster_rels=pc["cluster"].get("cluster_rels"),
                                coverage_class=_coverage_class(pc["cluster"], pc["name"] in survived_names))
                           for pc in per_candidate])
    return report


# ===========================================================================
# THE V3 CANDIDATE BATCH (~8 un-mined compositional/interaction/sequence candidates)
# ===========================================================================
# HONEST EXPECTATION (stated up front): the possession-STATE grain is SATURATED -- all 14 single
# legacy_possessions columns reject alone and the 5-signal possession_origin/transition/shot_clock clusters
# already capture the saturated state. These candidates are deliberately INTERACTIONS and SEQUENCE features
# that have NOT been tested as their own cluster. We EXPECT most/all to reject; the point is to PROVE the
# machinery + map coverage and to catch any genuine cross-season survivor without manufacturing one.
#
# NONE of these is the saturated state-5 set {poss_dur, after_to, dead_ball, abs_margin, had_oreb}.
#
# THIN-BASELINE FIX (2026-06-08): an EARLIER version of this batch put the raw component columns in
# `signals` alongside the interaction term, with base=[period,grem]. That CREDITED THE RAW MAINS (which are
# the already-mined saturated state vars) to the candidate -- 7/8 "REPLICATED" and 4 registered, then ALL 4
# collapsed to ~0.00% lift when re-measured against base+raw_mains (the raw mains, not the interaction,
# carried the lift -> retired as thin-baseline artifacts). THE FIX: the raw component columns belong in
# `base` (the control already has them); `signals` holds ONLY the genuinely-NEW derived term. So the cluster
# now isolates exactly the interaction/ratio's incremental cross-season information. This is the discipline:
# a candidate must beat a baseline that ALREADY contains everything except the new idea.

def _x(col_a: str, col_b: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Build a pure derive() that adds an interaction column named '<a>_x_<b>' = df[a]*df[b]."""
    name = f"{col_a}_x_{col_b}"

    def derive(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[name] = df[col_a].astype(float) * df[col_b].astype(float)
        return df
    return derive


def _ratio(num: str, den: str, eps: float = 1.0) -> Callable[[pd.DataFrame], pd.DataFrame]:
    name = f"{num}_per_{den}"

    def derive(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[name] = df[num].astype(float) / (df[den].astype(float) + eps)
        return df
    return derive


def _multi(*derivers: Callable[[pd.DataFrame], pd.DataFrame]) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def derive(df: pd.DataFrame) -> pd.DataFrame:
        for d in derivers:
            df = d(df)
        return df
    return derive


# Each candidate's `base` includes [period, grem] AND the raw component columns of its interaction, so the
# `signals` (the new derived term ONLY) is the one thing on trial -- the cluster lift is the interaction's
# OWN incremental cross-season information, not credit for the saturated raw mains.
CANDIDATES: List[Dict[str, Any]] = [
    # 1. SEQUENCE: a transition possession that ALSO follows a make -- "scored-on-them, now they run".
    dict(name="possession.seq.prev_scored_x_dead_ball",
         base=["period", "grem", "prev_scored", "dead_ball"], signals=["prev_scored_x_dead_ball"],
         derive=_x("prev_scored", "dead_ball"),
         domain="possession_sequence", scope="possession", engine_node="sequence_state_ppp",
         transform_chain=["interaction_seq"], source="pbp_possession",
         hypothesis="A dead-ball possession right after the opponent scored (made FG -> inbound) yields "
                    "fewer points than a live rebound, because the defense is set and the clock is full."),

    # 2. INTERACTION: long possessions that came off a turnover -- "scramble that DIDN'T convert fast".
    dict(name="possession.intx.poss_dur_x_after_to",
         base=["period", "grem", "poss_dur", "after_to"], signals=["poss_dur_x_after_to"],
         derive=_x("poss_dur", "after_to"),
         domain="possession_tempo_origin", scope="possession", engine_node="tempo_origin_ppp",
         transform_chain=["interaction_tempo"], source="pbp_possession",
         hypothesis="An after-turnover possession that BURNS clock (long dur) has squandered the transition "
                    "edge, so its scoring rate should regress toward a half-court possession's."),

    # 3. INTERACTION: fast-break in a blowout -- garbage-time transition is hollow scoring.
    dict(name="possession.intx.fastbreak_x_garbage",
         base=["period", "grem", "fastbreak", "garbage"], signals=["fastbreak_x_garbage"],
         derive=_x("fastbreak", "garbage"),
         domain="possession_context_tempo", scope="possession", engine_node="context_tempo_ppp",
         transform_chain=["interaction_context"], source="pbp_possession",
         hypothesis="Fast-break value depends on game state: in garbage time defenses concede, inflating "
                    "transition PPP relative to a contested fast break -- a state-dependent tempo effect."),

    # 4. INTERACTION: clutch + late-clock -- end-of-game, end-of-shot-clock heaves.
    dict(name="possession.intx.is_clutch_x_late_clock",
         base=["period", "grem", "is_clutch", "late_clock"], signals=["is_clutch_x_late_clock"],
         derive=_x("is_clutch", "late_clock"),
         domain="possession_pressure", scope="possession", engine_node="pressure_state_ppp",
         transform_chain=["interaction_pressure"], source="pbp_possession",
         hypothesis="A clutch possession that ALSO reaches a late shot clock is a maximally-defended, "
                    "low-quality look -- the two pressures compound to suppress PPP beyond either alone."),

    # 5. SEQUENCE: an offensive rebound that extends a possession into early clock -- 2nd-chance freshness.
    dict(name="possession.seq.had_oreb_x_early_clock",
         base=["period", "grem", "had_oreb", "early_clock"], signals=["had_oreb_x_early_clock"],
         derive=_x("had_oreb", "early_clock"),
         domain="possession_second_chance", scope="possession", engine_node="second_chance_ppp",
         transform_chain=["interaction_secondchance"], source="pbp_possession",
         hypothesis="An offensive rebound that resets to an early shot clock (kick-out, reset) is a higher-"
                    "quality second chance than a putback at a late clock -- a freshness x oreb interaction."),

    # 6. POSITIONAL: possession index within a game -- early-game vs late-game scoring drift.
    dict(name="possession.intx.poss_idx_x_abs_margin",
         base=["period", "grem", "poss_idx", "abs_margin"], signals=["poss_idx_x_abs_margin"],
         derive=_x("poss_idx", "abs_margin"),
         domain="possession_game_arc", scope="possession", engine_node="game_arc_ppp",
         transform_chain=["interaction_arc"], source="pbp_possession",
         hypothesis="As a game progresses (high poss_idx) AND the margin widens, scoring decays (fatigue + "
                    "lead-protection) -- a within-game arc effect that single state vars miss."),

    # 7. RATIO: time-remaining per second-of-possession -- urgency density (nonlinearity of base feats).
    dict(name="possession.ratio.grem_per_poss_dur",
         base=["period", "grem", "poss_dur"], signals=["grem_per_poss_dur"],
         derive=_ratio("grem", "poss_dur"),
         domain="possession_clock_pressure", scope="possession", engine_node="clock_pressure_ppp",
         transform_chain=["ratio_clock"], source="pbp_possession",
         hypothesis="Time-remaining PER second-of-possession captures urgency density: a long possession with "
                    "little period time left is a different scoring regime than the same dur early."),

    # 8. SEQUENCE/INTERACTION TRIAD: transition off a turnover / extended by an OREB -- compound origin.
    dict(name="possession.seq.fastbreak_x_after_to_x_had_oreb",
         base=["period", "grem", "fastbreak", "after_to", "had_oreb"],
         signals=["fastbreak_x_after_to", "fastbreak_x_had_oreb"],
         derive=_multi(_x("fastbreak", "after_to"), _x("fastbreak", "had_oreb")),
         domain="possession_origin_compound", scope="possession", engine_node="compound_origin_ppp",
         transform_chain=["interaction_compound_origin"], source="pbp_possession",
         hypothesis="The ORIGIN of a fast break matters: a turnover-sparked break and an oreb-sparked break "
                    "are different scoring regimes than a generic fastbreak flag -- a compound-origin cluster."),
]


def _print_report(rep: Dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print(f"FOUNDRY V3 BATCH {rep['batch_id']}  ({rep['n']} candidates, FDR={rep['procedure'].upper()} "
          f"alpha={rep['alpha']})")
    print("=" * 78)
    for r in rep["results"]:
        print(f"  [{r['coverage_class']:24s}] {r['name']:46s} verdict={r['verdict']:20s} "
              f"p={r['p']:.4f} rels={r['cluster_rels']}")
    print("-" * 78)
    print(f"  cluster-REPLICATES: {rep['n_replicates']}   FDR-survivors: {rep['n_fdr_survivors']}   "
          f"REGISTERED: {rep['n_registered']}")
    print(f"  coverage: {rep['coverage_counts']}")
    if rep["survivors"]:
        for s in rep["survivors"]:
            print(f"  SURVIVOR -> {s['name']} registered {s['model_id']} ({s['domain']}) rels={s['cluster_rels']}")
    else:
        print("  NO SURVIVORS -- expected under possession-STATE saturation. Coverage mapped; nothing "
              "manufactured. This is a CORRECT result, not a failure.")
    print("=" * 78)


def main() -> Dict[str, Any]:
    rep = run_candidates(CANDIDATES)
    _print_report(rep)
    return rep


if __name__ == "__main__":
    main()
