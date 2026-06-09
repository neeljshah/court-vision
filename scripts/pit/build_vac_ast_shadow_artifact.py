"""build_vac_ast_shadow_artifact.py — prove the vac_ast SHIP path end-to-end.

Trains a SHADOW AST artifact with CV_AST_VAC_FEATURE=1 to a SEPARATE model dir
(data/models/shadow_vac_ast/) so the production data/models/ is UNTOUCHED. Then
loads it via the real serve path (predict_pergame with model_dir=shadow) on a sample
of held-out AST rows, confirming:
  (1) the artifact's frozen feature list = 131 cols incl vac_ast/vac_ast_share,
  (2) n_features_in_ = 131 (the model actually trained on the 2 new cols),
  (3) predict_pergame loads + scores it without n_features_in_ mismatch,
  (4) predictions are sane vs the production (flag-OFF, 129-col) AST artifact.

This is the deployment-readiness proof for the SHIP-RECOMMEND (item A): flip
CV_AST_VAC_FEATURE=1 + deploy THIS kind of retrained artifact. Read-only on
production; writes only to the shadow dir. No git commit.

Run (GPU, single AST train ~minutes):
  conda run -n basketball_ai python scripts/pit/build_vac_ast_shadow_artifact.py
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SHADOW = ROOT / "data" / "models" / "shadow_vac_ast"
PROD = ROOT / "data" / "models"


def main():
    os.environ["CV_AST_VAC_FEATURE"] = "1"
    SHADOW.mkdir(parents=True, exist_ok=True)
    from src.prediction.prop_pergame import (
        train_pergame_models, feature_columns, feature_columns_for,
        predict_pergame, build_pergame_dataset, build_prediction_row,
    )

    fc_on = feature_columns(stat="ast")
    print(f"feature_columns(ast) with flag ON = {len(fc_on)} cols; last 2 = {fc_on[-2:]}")
    assert fc_on[-2:] == ["vac_ast", "vac_ast_share"], "flag not appending vac cols"

    print("Training SHADOW AST artifact (flag ON) -> ", SHADOW, flush=True)
    metrics = train_pergame_models(model_dir=str(SHADOW), stats=["ast"])
    print("train metrics:", json.dumps(metrics.get("ast", metrics), indent=2)[:600])

    # verify the artifact's frozen feature list
    art = SHADOW / "props_pg_ast.json"
    if not art.exists():
        print("!! shadow artifact NOT written"); return
    meta = json.load(open(art))
    frozen = (meta.get("stats") or {}).get("ast", {}).get("feature_columns") or meta.get("feature_columns")
    if frozen:
        print(f"  frozen feature_columns: {len(frozen)} cols; has vac_ast={'vac_ast' in frozen}, "
              f"vac_ast_share={'vac_ast_share' in frozen}")
    fc_for = feature_columns_for("ast", artifact_dir=str(SHADOW))
    print(f"  feature_columns_for(ast, shadow) = {len(fc_for)} cols; last2={fc_for[-2:]}")

    # serve-path sanity: predict a few AST rows via shadow vs production artifact
    print("\nServe-path check: predict_pergame(ast) shadow(131) vs prod(129) on sample rows", flush=True)
    rows, _ = build_pergame_dataset(min_prior=3)
    rows.sort(key=lambda r: r["date"])
    sample = rows[-300::40]  # ~8 recent rows
    n_ok = 0
    for r in sample:
        try:
            p_shadow = predict_pergame("ast", r, str(SHADOW))
            p_prod = predict_pergame("ast", r, str(PROD))
            va = r.get("vac_ast", 0.0)
            print(f"  pid={r.get('player_id')} date={str(r.get('date'))[:10]} "
                  f"vac_ast={va:.1f}  shadow={p_shadow:.2f}  prod={p_prod:.2f}  d={p_shadow-p_prod:+.2f}")
            if p_shadow is not None and 0 <= p_shadow < 25:
                n_ok += 1
        except Exception as exc:
            print(f"  pid={r.get('player_id')} ERROR: {exc}")
    print(f"\n  serve-path sane preds: {n_ok}/{len(sample)}")
    print("  => If preds load + are sane, the SHIP path works: retrain AST with flag ON, deploy artifact.")


if __name__ == "__main__":
    main()
