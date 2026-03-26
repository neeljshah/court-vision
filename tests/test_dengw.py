import sys, warnings, pandas as pd
sys.path.insert(0,'C:/Users/neelj/nba-ai-system')
import os; os.chdir('C:/Users/neelj/nba-ai-system')
warnings.filterwarnings('ignore')
from src.pipeline.unified_pipeline import UnifiedPipeline

p = UnifiedPipeline('data/videos/den_gsw_playoffs.mp4', max_frames=300, show=False, start_frame=1000)
p.run()

td = pd.read_csv('data/tracking_data.csv')
tpf = td.groupby('frame').size()
print('AVG_TPF:', round(tpf.mean(),2))
print('MAX_TPF:', tpf.max())
print('TEAMS:', dict(td['team'].value_counts()))
print('EVENTS:', dict(td['event'].value_counts()))
bd = pd.read_csv('data/ball_tracking.csv')
print('BALL_DET:', round(bd['detected'].mean(),3))
poss = pd.read_csv('data/possessions.csv')
print('POSSESSIONS:', len(poss))
