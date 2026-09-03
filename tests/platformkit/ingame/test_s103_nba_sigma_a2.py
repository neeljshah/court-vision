from pathlib import Path
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
P = Path(__file__).resolve().parents[3] / "data/cache/eval_gate/s103_nba_sigma_2026-09-03.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f=pd.read_csv(P); y=f.y
    for c,v in (("market",.074457),("p_cell98",.076835),("p_wide",.076574),("p_param",.078206),("p_blend",.074587),("p_recal",.074544)): assert ((f[c]-y)**2).mean()==pytest.approx(v,abs=1e-6)
    d=(f.market-y)**2-(f.p_wide-y)**2; assert d.mean()==pytest.approx(-.002117,abs=1e-6); assert diebold_mariano(d.tolist(),f.cluster_id.tolist()).ci95==pytest.approx((-.004670,.000436),abs=1e-5)
    q=flag_ticks(f,game_col="game",ts_col="ts",market_col="market",model_col="p_param")[1]; assert (q["n"],q["n_informative"]) == (162171,67214)
