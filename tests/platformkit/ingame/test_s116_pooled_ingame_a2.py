from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
ROOT=Path(__file__).resolve().parents[3]; P=ROOT/"data/cache/eval_gate/s116_pooled_ingame_2026-09-03.csv"
def test_a2():
    if not P.exists(): pytest.skip("archive absent: %s" % P)
    f=pd.read_csv(P); cases={"mlb":(("p_line",.215528),("p_null",.210827),("p_pooled",.211336),("p_persport",.203722),("p_partial",.202690),.012837,(-.002273,.027948),9669,2622),"nba":(("p_line",.078611),("p_null",.078931),("p_persport",.078953),("p_pooled",.078953),("p_partial",.078953),-.000343,(-.001124,.000438),192635,78761)}
    if not {"model_raw","market_raw"}.issubset(f.columns): pytest.skip("archive predates raw source columns")
    for sport, case in cases.items():
        r=f[f.sport==sport]; *arms,imp,ci,n,inf=case; y=r.y
        for c,v in arms: assert ((r[c]-y)**2).mean()==pytest.approx(v,abs=1e-6)
        d=(r.p_line-y)**2-(r.p_partial-y)**2; assert d.mean()==pytest.approx(imp,abs=1e-6); assert diebold_mariano(d.tolist(),r.cluster.tolist()).ci95==pytest.approx(ci,abs=1e-5)
        if sport=="mlb":
            line=r.p_line.clip(1e-6,1-1e-6); r=r.assign(source_model=1/(1+np.exp(-(np.log(line/(1-line))+r.gap)))); q=flag_ticks(r,game_col="cluster",ts_col="ts_utc",market_col="p_line",model_col="source_model")[1]
        else: q=flag_ticks(r,game_col="cluster",ts_col="ts_utc",market_col="market_raw",model_col="model_raw")[1]
        assert (q["n"],q["n_informative"]) == (n,inf)
