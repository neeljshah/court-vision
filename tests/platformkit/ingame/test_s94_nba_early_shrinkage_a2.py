from pathlib import Path
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
P = Path(__file__).resolve().parents[3] / "data/cache/eval_gate/s94_nba_early_shrinkage_2026-09-03.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f=pd.read_csv(P); f=f[f.cell.isin(("P1|close_le5|rem_gt12","P2|close_le5|rem_gt12"))]; y=f.y
    for c,v in (("market",.220173),("p_recal",.221658),("p_cellrecal",.226244),("p_candidate",.222980)): assert ((f[c]-y)**2).mean()==pytest.approx(v,abs=1e-6)
    d=(f.market-y)**2-(f.p_candidate-y)**2; assert d.mean()==pytest.approx(-.002807,abs=1e-6); assert diebold_mariano(d.tolist(),f.cluster_id.tolist()).ci95==pytest.approx((-.006055,.000440),abs=1e-5)
    q=flag_ticks(f,game_col="game",ts_col="ts",market_col="market",model_col="model")[1]; assert (q["n"],q["n_informative"]) == (23561,19776)
