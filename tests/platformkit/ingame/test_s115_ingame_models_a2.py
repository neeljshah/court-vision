from pathlib import Path
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
P = Path(__file__).resolve().parents[3] / "data/cache/eval_gate/s115_ingame_models_2026-09-03.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f=pd.read_csv(P); y=f.y
    for c,v in (("market",.078611),("p_null",.078974),("p_hgb",.080022),("p_mlp",.079160),("p_hgb_mono",.080066)): assert ((f[c]-y)**2).mean()==pytest.approx(v,abs=1e-6)
    d=(f.market-y)**2-(f.p_mlp-y)**2; assert d.mean()==pytest.approx(-.000549,abs=1e-6); assert diebold_mariano(d.tolist(),f.cluster_id.tolist()).ci95==pytest.approx((-.001476,.000378),abs=1e-5)
    q=flag_ticks(f,game_col="game",ts_col="ts",market_col="market",model_col="model")[1]; assert (q["n"],q["n_informative"]) == (192635,78761)
