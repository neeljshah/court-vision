from pathlib import Path
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
P=Path(__file__).resolve().parents[3]/"data/cache/eval_gate/s117_soccer_ingame_screen_2026-09-03_series.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f=pd.read_csv(P); cases=(("minute_x_score_diff",.191586,.025071,(-.337858,.388001),129),("score_diff_decayed",.192626,.024032,(-.007170,.055233),129),("minute",.205568,.011090,(-.296076,.318255),129),("score_diff",.216584,.000074,(-.823119,.823267),127),("minutes_since_last_goal",.235776,-.019118,(-.386594,.348358),129),("goals_total",.241848,-.025190,(-1.438071,1.387690),127),("prior_vs_line_gap",.274890,-.058232,(-1.283687,1.167223),127))
    for feature,brier,imp,ci,inf in cases:
        r=f[f.feature==feature]; y=r.y; assert ((r.p_candidate-y)**2).mean()==pytest.approx(brier,abs=1e-6)
        d=(r.p_null-y)**2-(r.p_candidate-y)**2; assert d.mean()==pytest.approx(imp,abs=1e-6); assert diebold_mariano(d.tolist(),r.game.tolist()).ci95==pytest.approx(ci,abs=1e-5)
        q=flag_ticks(r,game_col="game",ts_col="timestamp",market_col="market",model_col="p_candidate")[1]; assert (q["n"],q["n_informative"]) == (163,inf)
