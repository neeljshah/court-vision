'''Retrain PTS pergame + FG3M quantile models after R10_M14 wire-in.

Run after switching to prior-season playtype join. Reports holdout MAE
for PTS (via train_pergame_models -> props_pg_lgb_pts.pkl) and FG3M
(via train_quantile_models -> quantile_pergame_lgb_fg3m_q50.pkl,
quantile_pergame_fg3m_q50.json).
'''
import json
import time
import os
import sys

sys.path.insert(0, '/workspace/nba-ai-system')

from src.prediction.prop_pergame import train_pergame_models
from src.prediction.prop_quantiles import train_quantile_models

print('=' * 60)
print('R10_M14 retrain — PTS + FG3M with prior-season playtype features')
print('=' * 60)

t0 = time.time()
print('[1] Training PTS via train_pergame_models(stats=["pts"]) ...', flush=True)
pts_metrics = train_pergame_models(stats=['pts'])
print('PTS metrics:', json.dumps(pts_metrics, default=str)[:800])
print(f'  elapsed: {time.time()-t0:.1f}s', flush=True)

t1 = time.time()
print('\n[2] Training FG3M quantile (q10/q50/q90) via train_quantile_models(stats=["fg3m"]) ...', flush=True)
fg3m_metrics = train_quantile_models(stats=['fg3m'])
print('FG3M metrics:', json.dumps(fg3m_metrics, default=str)[:1200])
print(f'  elapsed: {time.time()-t1:.1f}s', flush=True)

print('\n=' * 30 + ' DONE ' + '=' * 30)
print(f'Total elapsed: {time.time()-t0:.1f}s')
