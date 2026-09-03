from pathlib import Path
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
P = Path(__file__).resolve().parents[3] / "data/cache/eval_gate/s96_nba_overreaction_2026-09-03.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f=pd.read_csv(P); f=f[(f.threshold==3)&(f.k==5)]; y=f.y
    for c,v in (("market",.156677),("p_recal",.157370),("p_arm",.156815)): assert ((f[c]-y)**2).mean()==pytest.approx(v,abs=1e-6)
    d=(f.market-y)**2-(f.p_arm-y)**2; assert d.mean()==pytest.approx(-.000138,abs=1e-6); assert diebold_mariano(d.tolist(),f.cluster_id.tolist()).ci95==pytest.approx((-.000301,.000025),abs=1e-5)
    q=flag_ticks(f,game_col="game",ts_col="ts",market_col="market",model_col="model")[1]; assert (q["n"],q["n_informative"]) == (39168,33231)
