from pathlib import Path
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
P = Path(__file__).resolve().parents[3] / "data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_rated.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f = pd.read_csv(P); y = f.outcome_home_win
    for c, v in {"market_prob":.144101,"p_null":.146843,"p_incumbent":.153324,"p_fatigue_min":.152849,"p_fatigue_share":.153149,"p_unit_onoff":.154385}.items(): assert ((f[c]-y)**2).mean() == pytest.approx(v,abs=1e-6)
    for c, imp, ci, inf in (("p_fatigue_min",.000475,(-.000579,.001530),31036),("p_fatigue_share",.000175,(-.001472,.001822),31062),("p_unit_onoff",-.001061,(-.002577,.000454),31035)):
        d=(f.p_incumbent-y)**2-(f[c]-y)**2; assert d.mean()==pytest.approx(imp,abs=1e-6); assert diebold_mariano(d.tolist(),f.cluster_id.tolist()).ci95==pytest.approx(ci,abs=1e-5)
        assert (flag_ticks(f,game_col="game",ts_col="ts",market_col="market_prob",model_col=c)[1]["n"],flag_ticks(f,game_col="game",ts_col="ts",market_col="market_prob",model_col=c)[1]["n_informative"]) == (33713,inf)
