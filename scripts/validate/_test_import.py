import sys
sys.path.insert(0, '.')
print('importing _ALL_FEATS...')
from src.prediction.player_props import _ALL_FEATS, _PROP_STATS
print(f'_ALL_FEATS: {len(_ALL_FEATS)} features')
print(f'_PROP_STATS: {_PROP_STATS}')
