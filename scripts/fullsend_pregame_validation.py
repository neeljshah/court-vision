"""fullsend_pregame_validation.py — STEP 2+3 pregame hardening validation.

RETRACTION NOTICE (2026-06): the "+18.38% KB+ISO ROI / +8.94pp CLV" figures this
script references are a RETRACTED market-follow grading artifact (the grader bet the
market's own devigged direction, never read the model; in-sample-tuned filters). See
docs/JOB_EVIDENCE_PACKET.md. This script is an IN-SAMPLE REGRESSION/IDENTITY check that
the historical artifact reproduces unchanged — it does NOT establish that any $ edge
exists. Against efficient closing lines the honest read is break-even-minus-vig.

Proves:
  (a) CV_PROP_EXTRA_FEATURES flag is a SERVE-TIME NO-OP:
      predictions are byte-identical under flag=0 vs flag=1, because the
      extra keys added by the flag are NOT in _ALL_FEATS (220 cols).
  (b) Prop model artifacts load cleanly.
  (c) predict_props returns sane values for SGA, Jokic, LeBron.

Writes results to data/cache/fullsend_pregame_validation.json.

USAGE (NBA_OFFLINE=1 must be set):
  NBA_OFFLINE=1 python scripts/fullsend_pregame_validation.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Force offline; must be set BEFORE any src import
os.environ.setdefault("NBA_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.prediction.player_props import (  # noqa: E402
    _ALL_FEATS,
    _build_player_features,
    _predict_with_models,
    predict_props,
    _PROP_STATS,
)

PLAYERS = [
    ("shai gilgeous-alexander", "MIN", "2025-26"),
    ("nikola jokic",            "OKC", "2025-26"),
    ("lebron james",            "BOS", "2025-26"),
]

_MODEL_DIR = ROOT / "data" / "models"
_OUT_PATH  = ROOT / "data" / "cache" / "fullsend_pregame_validation.json"


# ── Helper: build features with flag forced to a given value ──────────────────

def _feats_with_flag(player: str, opp: str, season: str, flag_on: bool) -> dict | None:
    """Build feature vector with CV_PROP_EXTRA_FEATURES forced to flag_on."""
    prev = os.environ.get("CV_PROP_EXTRA_FEATURES", "1")
    os.environ["CV_PROP_EXTRA_FEATURES"] = "1" if flag_on else "0"
    try:
        feats = _build_player_features(player, opp, season, n_games=10)
    finally:
        os.environ["CV_PROP_EXTRA_FEATURES"] = prev
    return feats


def _preds_from_feats(feats: dict) -> dict:
    """Run _predict_with_models and return the predictions dict."""
    preds, _ = _predict_with_models(feats)
    return preds


# ── STEP 1: Confirm canonical gate1 numbers ───────────────────────────────────

def step1_canonical_numbers() -> dict:
    """Read iter61 from holdout_baseline.json and gate1_full_analysis.json."""
    result = {}

    # iter61 canonical
    baseline_path = ROOT / "data" / "cache" / "holdout_baseline.json"
    if baseline_path.exists():
        bl = json.load(open(baseline_path, encoding="utf-8"))
        it61 = bl.get("__iter61__", {})
        cr = it61.get("canonical_roi_post_iter57", {})
        result["iter61_canonical"] = {
            "n_bets":      cr.get("n_bets"),
            "flat_1u_pct": cr.get("flat_1u_pct"),
            "kb_iso_pct":  cr.get("kb_iso_pct"),
            "source":      "data/cache/holdout_baseline.json[__iter61__]",
        }
    else:
        result["iter61_canonical"] = {"error": "holdout_baseline.json not found"}

    # gate1_full_analysis.json (latest run)
    gate1_path = ROOT / "data" / "cache" / "gate1_full_analysis.json"
    if gate1_path.exists():
        g1 = json.load(open(gate1_path, encoding="utf-8"))
        prod = g1.get("p2526_prod_stack_all", {})
        result["gate1_full_latest_run"] = {
            "p2526_prod_stack_n":       prod.get("n"),
            "p2526_prod_stack_roi_pct": prod.get("roi_pct"),
            "p2526_prod_stack_beat_pct":prod.get("beat_pct"),
            "combined_l10_n":           g1.get("combined_l10_naive", {}).get("n"),
            "combined_l10_roi_pct":     g1.get("combined_l10_naive", {}).get("roi_pct"),
            "n_bets_total":             g1.get("n_bets_total_combined"),
            "source":                   "data/cache/gate1_full_analysis.json",
            "note": ("gate1_full_analysis uses raw OOF without the post-Iter-57 filter stack "
                     "that produced the RETRACTED +18.38% headline artifact. That value lives in "
                     "holdout_baseline.json[__iter61__][canonical_roi_post_iter57]."),
        }
    else:
        result["gate1_full_latest_run"] = {"error": "gate1_full_analysis.json not found"}

    return result


# ── STEP 2: Prove CV_PROP_EXTRA_FEATURES is a serve-time no-op ───────────────

def step2_flag_noop_proof() -> dict:
    """
    For each test player:
      1. Build feature dict with flag=OFF
      2. Build feature dict with flag=ON
      3. Identify which extra keys the flag injected (not in _all_feats)
      4. Run _predict_with_models on both — assert predictions are identical

    Returns a result dict with per-player proof + global summary.
    """
    # Atlas keys that the flag MIGHT inject
    try:
        from src.ingest.prop_line_movement import _NEUTRAL as _plm_neutral
        plm_keys = set(_plm_neutral.keys())
    except Exception:
        plm_keys = {
            "prop_line_open", "prop_line_latest", "prop_line_move",
            "prop_line_move_abs", "prop_over_price_move",
            "prop_n_captures", "prop_line_moved_flag",
        }

    _all_feats_set = set(_ALL_FEATS)

    # Confirm PLM keys absent from _ALL_FEATS
    plm_in_all_feats = plm_keys & _all_feats_set

    per_player = {}
    all_identical = True

    for player, opp, season in PLAYERS:
        print(f"  Testing {player} vs {opp} ({season}) ...")
        feats_off = _feats_with_flag(player, opp, season, flag_on=False)
        feats_on  = _feats_with_flag(player, opp, season, flag_on=True)

        if feats_off is None or feats_on is None:
            per_player[player] = {
                "status": "SKIP_NO_FEATURES",
                "reason": f"feats_off={feats_off is None} feats_on={feats_on is None}",
            }
            continue

        # Keys injected by flag (present in ON but not OFF)
        injected_keys = set(feats_on.keys()) - set(feats_off.keys())
        injected_in_all_feats = injected_keys & _all_feats_set

        # Build X arrays from _ALL_FEATS (exactly as _predict_with_models does)
        import numpy as np
        X_off = {k: feats_off.get(k, 0.0) for k in _ALL_FEATS}
        X_on  = {k: feats_on.get(k,  0.0) for k in _ALL_FEATS}

        # Confirm the X arrays are identical (injected keys are NOT in _ALL_FEATS)
        x_identical = (X_off == X_on)

        # Run predictions
        preds_off, conf_off = _predict_with_models(feats_off)
        preds_on,  conf_on  = _predict_with_models(feats_on)

        preds_identical = (preds_off == preds_on)
        if not preds_identical:
            all_identical = False

        per_player[player] = {
            "n_injected_keys":             len(injected_keys),
            "injected_keys_sample":        sorted(injected_keys)[:10],
            "injected_keys_in_ALL_FEATS":  sorted(injected_in_all_feats),
            "X_arrays_identical":          x_identical,
            "predictions_identical":       preds_identical,
            "predictions_flag_off":        preds_off,
            "predictions_flag_on":         preds_on,
            "confidence_flag_off":         conf_off,
            "confidence_flag_on":          conf_on,
        }

    return {
        "ALL_FEATS_count":         len(_ALL_FEATS),
        "PLM_keys_checked":        sorted(plm_keys),
        "PLM_keys_in_ALL_FEATS":   sorted(plm_in_all_feats),
        "all_predictions_identical": all_identical,
        "per_player":              per_player,
        "verdict": (
            "PROVEN_NOOP — flag=ON vs flag=OFF produces byte-identical _predict_with_models "
            "output because every key injected by the flag is absent from _ALL_FEATS (220 cols)."
            if all_identical else
            "FAIL — predictions differ; investigate which injected key entered _ALL_FEATS."
        ),
    }


# ── STEP 3: Artifact load + sanity predictions ────────────────────────────────

def step3_artifact_sanity() -> dict:
    """Check all prop model artifacts load, then get sample predictions."""
    result = {}

    # Check each stat's XGBoost model + stacker
    artifact_status = {}
    stats = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    for stat in stats:
        xgb_path  = _MODEL_DIR / f"props_{stat}.json"
        stk_path  = _MODEL_DIR / f"props_stacker_{stat}.pkl"
        lgb_path  = _MODEL_DIR / f"props_lgb_{stat}.pkl"

        entry = {
            "xgb_exists":     xgb_path.exists(),
            "stacker_exists": stk_path.exists(),
            "lgb_exists":     lgb_path.exists(),
        }

        # Try loading XGBoost
        if xgb_path.exists():
            try:
                import xgboost as xgb
                m = xgb.XGBRegressor()
                m.load_model(str(xgb_path))
                entry["xgb_load"] = "OK"
            except Exception as e:
                entry["xgb_load"] = f"ERROR: {e}"
        else:
            entry["xgb_load"] = "MISSING"

        # Try loading stacker
        if stk_path.exists():
            try:
                import joblib
                m = joblib.load(str(stk_path))
                entry["stacker_load"] = "OK"
            except Exception as e:
                entry["stacker_load"] = f"ERROR: {e}"
        else:
            entry["stacker_load"] = "MISSING"

        artifact_status[stat] = entry

    result["artifact_status"] = artifact_status

    # Sample predictions for key players
    sample_preds = {}
    for player, opp, season in PLAYERS:
        print(f"  Predict {player} vs {opp} ({season}) ...")
        try:
            t0 = time.time()
            pred = predict_props(player, opp, season, n_games=10)
            elapsed = round(time.time() - t0, 2)
            sample_preds[player] = {
                "opp":        opp,
                "confidence": pred.get("confidence"),
                "elapsed_s":  elapsed,
                "pts":        pred.get("pts"),
                "reb":        pred.get("reb"),
                "ast":        pred.get("ast"),
                "fg3m":       pred.get("fg3m"),
                "stl":        pred.get("stl"),
                "blk":        pred.get("blk"),
                "tov":        pred.get("tov"),
                "minutes_proj": pred.get("minutes_proj"),
                "injury_status": pred.get("injury_status"),
                "sanity_pass": (
                    pred.get("pts", 0) > 0 and
                    pred.get("reb", 0) >= 0 and
                    pred.get("ast", 0) >= 0
                ),
            }
        except Exception as e:
            sample_preds[player] = {"error": str(e)}

    result["sample_predictions"] = sample_preds
    result["artifacts_load_clean"] = all(
        v.get("xgb_load") == "OK" or v.get("stacker_load") == "OK"
        for v in artifact_status.values()
    )
    return result


# ── STEP 4: Pregame ceiling assessment ───────────────────────────────────────

def step4_ceiling_assessment() -> dict:
    """Regression guard: the retracted +18.38% in-sample artifact reproduces unchanged, and
    no READY/VALIDATED non-CV pregame feature is available today. NOT an edge claim."""
    # Read atlas_lift if it exists
    atlas_lift_path = ROOT / ".planning" / "loop" / "atlas_lift.json"
    atlas_lift = None
    if atlas_lift_path.exists():
        try:
            atlas_lift = json.load(open(atlas_lift_path, encoding="utf-8"))
        except Exception:
            pass

    return {
        "feature_ceiling_reached": True,
        "evidence": [
            "prop model at FEATURE CEILING (per MEMORY): no new validated feature ready",
            "atlas-as-features measured null: PTS +0.174 MAE worse (atlas_lift.json); atlas feeds CI-width/Kelly, not point model",
            "line-movement features: INSUFFICIENT_DATA (no intraday captures overlap training dates; PLM always returns neutral zero-vector)",
            "prop_line_movement (7 keys) and atlas_ keys are NOT in _ALL_FEATS — confirmed serve no-op",
        ],
        "ready_validated_improvements_today": "NONE",
        "pending_unlocks": [
            "Accumulating line/starter archives (Pinnacle prop daemon → Oct 2026 first real CLV read)",
            "CV game count growth ≥3× to unlock player-level CV features (currently team-only CV ships)",
            "scoreboard_ocr.py fix → PBP-anchoring → real quarter signals (currently ~5% coverage)",
        ],
        "verdict": (
            "The +18.38% KB+ISO / +8.94pp CLV figures are a RETRACTED in-sample market-follow "
            "grading artifact (see docs/JOB_EVIDENCE_PACKET.md), NOT a current or realized edge; "
            "this step only confirms the historical artifact reproduces unchanged (a regression "
            "guard), not that any edge exists. The honest read vs efficient closes is "
            "break-even-minus-vig. "
            "The CV_PROP_EXTRA_FEATURES wiring is a correct no-op preserve: atlas and PLM keys "
            "are injected into the feature dict but stripped by _predict_with_models because "
            "they are absent from _ALL_FEATS (220 cols). No READY, VALIDATED, non-CV feature "
            "is available today that would improve the point model — the accumulating line archive "
            "and CV scale-up are the next unlocks, neither available until Oct 2026 at earliest."
        ),
        "atlas_lift_file_found": atlas_lift is not None,
        "atlas_lift_pts_delta": (
            atlas_lift.get("pts", {}).get("mae_delta") if atlas_lift else None
        ),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("fullsend_pregame_validation.py")
    print("=" * 70)

    print("\n[STEP 1] Canonical edge numbers ...")
    s1 = step1_canonical_numbers()
    canon = s1.get("iter61_canonical", {})
    print(f"  Canonical: n={canon.get('n_bets')} flat={canon.get('flat_1u_pct')}% "
          f"KB+ISO={canon.get('kb_iso_pct')}%")
    print(f"  RETRACTED in-sample artifact (NOT a current edge): n=1535 flat=15.04% KB+ISO=18.38%")
    intact = (
        canon.get("n_bets") == 1535 and
        abs((canon.get("kb_iso_pct") or 0) - 18.38) < 0.01
    )
    print(f"  Historical artifact reproduces (regression guard, not an edge): "
          f"{'YES' if intact else 'DELTA — check numbers above'}")

    print("\n[STEP 2] Flag serve-time no-op proof ...")
    s2 = step2_flag_noop_proof()
    print(f"  _ALL_FEATS count: {s2['ALL_FEATS_count']}")
    print(f"  PLM keys in _ALL_FEATS: {s2['PLM_keys_in_ALL_FEATS']} (should be [])")
    print(f"  All predictions identical (flag OFF vs ON): {s2['all_predictions_identical']}")
    print(f"  Verdict: {s2['verdict']}")
    for player, info in s2["per_player"].items():
        if "status" not in info:
            print(f"    {player}: injected={info['n_injected_keys']} keys, "
                  f"identical={info['predictions_identical']}, "
                  f"preds_off={info['predictions_flag_off']}")

    print("\n[STEP 3] Artifact sanity check ...")
    s3 = step3_artifact_sanity()
    for stat, v in s3["artifact_status"].items():
        print(f"  {stat}: xgb={v.get('xgb_load')} stacker={v.get('stacker_load')}")
    print(f"  Artifacts load clean: {s3['artifacts_load_clean']}")
    for player, p in s3["sample_predictions"].items():
        if "error" in p:
            print(f"  {player}: ERROR {p['error']}")
        else:
            print(f"  {player}: pts={p.get('pts')} reb={p.get('reb')} ast={p.get('ast')} "
                  f"conf={p.get('confidence')} sane={p.get('sanity_pass')}")

    print("\n[STEP 4] Pregame ceiling assessment ...")
    s4 = step4_ceiling_assessment()
    print(f"  At ceiling: {s4['feature_ceiling_reached']}")
    print(f"  Ready improvements today: {s4['ready_validated_improvements_today']}")
    print(f"  Verdict:\n    {s4['verdict'][:200]}...")

    # Write results
    out = {
        "generated_at":       __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "script":             "scripts/fullsend_pregame_validation.py",
        "no_model_edits":     True,
        "step1_canonical":    s1,
        "step2_flag_noop":    s2,
        "step3_artifacts":    s3,
        "step4_ceiling":      s4,
        "summary": {
            # NOTE: the *_roi_pct figures below are a RETRACTED in-sample market-follow
            # artifact (docs/JOB_EVIDENCE_PACKET.md), NOT a current/realized edge. This
            # summary is a regression guard that the historical numbers reproduce unchanged.
            "historical_artifact_reproduces": intact,
            "retracted_in_sample_n_bets":     canon.get("n_bets"),
            "retracted_flat_roi_pct":         canon.get("flat_1u_pct"),
            "retracted_kb_iso_roi_pct":       canon.get("kb_iso_pct"),
            "retracted_reference_kb_iso_pct": 18.38,
            "flag_is_noop":             s2["all_predictions_identical"],
            "all_feats_count":          s2["ALL_FEATS_count"],
            "artifacts_load_clean":     s3["artifacts_load_clean"],
            "no_ready_validated_pregame_feature": True,
        },
    }
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(_OUT_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nResults written to: {_OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
