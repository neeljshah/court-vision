"""seqmodel package. The bootstrap below puts this directory on sys.path so the
modules here can keep their bare sibling imports (`import nba_gru_dataset`) and
still import as `scripts.platformkit.seqmodel.*`. Kept here, not in each module,
so nba_gru_winprob.py stays inside the 300 LOC/file rail."""
import sys
from pathlib import Path

_DIR = str(Path(__file__).resolve().parent)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
