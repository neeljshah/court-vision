"""S77: the six sibling producers that enumerate data/tracking are guarded.

S69 guarded three loaders against the sport-blind `tracking_schema` shape
(`frame,track_id,cls,x,y[,coordinate_space,observation,calibration]`) that the
multi-sport tracking harness writes into the SAME `data/tracking/` tree the NBA
intelligence builders enumerate. These six were named as still unguarded. Each
must SKIP such a directory by name -- never alias `track_id` onto `player_id` --
and must still process a real NBA directory.
"""
import pandas as pd
import pytest

from scripts import build_clutch_cv as clutch
from scripts import build_possession_type_intel as poss_type
from scripts import build_sequential_possession as seq
from scripts import build_shot_clock_buckets as shotclock
from scripts import build_trade_intel as trade
from scripts import eval_live_shot_quality as evallive

SPORT_BLIND_COLS = ["frame", "track_id", "cls", "x", "y",
                    "coordinate_space", "observation", "calibration"]


def _sport_blind(n_rows):
    """The exact 8-column MLB shape S69 measured in data/tracking/mlb_2iosUkpL0Bc."""
    return pd.DataFrame({
        "frame": range(n_rows),
        "track_id": [i % 9 + 1 for i in range(n_rows)],
        "cls": ["person"] * n_rows,
        "x": [100.0 + i % 50 for i in range(n_rows)],
        "y": [200.0 + i % 50 for i in range(n_rows)],
        "coordinate_space": ["image_px"] * n_rows,
        "observation": ["obs"] * n_rows,
        "calibration": ["none"] * n_rows,
    })


def _nba(n_rows):
    return pd.DataFrame({
        "frame": range(n_rows),
        "player_id": [i % 10 + 1 for i in range(n_rows)],
        "player_name": ["Player {0}".format(i % 10 + 1) for i in range(n_rows)],
        "team": ["LAL", "BOS"] * (n_rows // 2),
        "team_abbrev": ["LAL", "BOS"] * (n_rows // 2),
        "jersey_number": [str(i % 10 + 1) for i in range(n_rows)],
        "possession_id": [i // 100 for i in range(n_rows)],
        "ball_possession": [0] * n_rows,
        "velocity": [3.0] * n_rows,
        "dribble_count": [0] * n_rows,
        "paint_touches": [0] * n_rows,
        "possession_type": ["halfcourt"] * n_rows,
        "distance_to_ball": [10.0] * n_rows,
        "court_zone": ["paint"] * n_rows,
    })


def _game_dir(root, name, df, extras=None):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / "tracking_data.csv", index=False)
    for fname, edf in (extras or {}).items():
        edf.to_csv(d / fname, index=False)
    return d


# --- 1. build_clutch_cv ------------------------------------------------------

def test_clutch_cv_skips_sport_blind(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(clutch, "TRACKING_DIR", tmp_path)
    _game_dir(tmp_path, "mlb_2iosUkpL0Bc", _sport_blind(clutch.MIN_TOTAL_ROWS + 10))
    assert clutch._process_one_game("mlb_2iosUkpL0Bc", lambda s: None, verbose=True) == []
    assert "non-NBA tracking schema" in capsys.readouterr().out


def test_clutch_cv_still_reads_nba(tmp_path, monkeypatch):
    monkeypatch.setattr(clutch, "TRACKING_DIR", tmp_path)
    _game_dir(tmp_path, "0022400625", _nba(clutch.MIN_TOTAL_ROWS + 10))
    # The guard must not empty a real corpus: this reaches the clutch split, so it
    # returns past the guard rather than at it.
    clutch._process_one_game("0022400625", lambda s: 1, verbose=False)


# --- 2. build_possession_type_intel ------------------------------------------

def test_possession_type_skips_sport_blind(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(poss_type, "TRACKING_DIR", tmp_path)
    _game_dir(tmp_path, "mlb_2iosUkpL0Bc", _sport_blind(2000))
    assert poss_type.load_game_frames("mlb_2iosUkpL0Bc") is None
    assert "non-NBA tracking schema" in capsys.readouterr().out


def test_possession_type_still_reads_nba(tmp_path, monkeypatch):
    monkeypatch.setattr(poss_type, "TRACKING_DIR", tmp_path)
    _game_dir(tmp_path, "0022400625", _nba(2000))
    out = poss_type.load_game_frames("0022400625")
    assert out is not None and "player_id" in out.columns


# --- 3. build_sequential_possession ------------------------------------------

def test_sequential_skips_sport_blind(tmp_path, capsys):
    # > 50_000 bytes, or the size pre-check returns before the guard is reached.
    d = _game_dir(tmp_path, "mlb_2iosUkpL0Bc", _sport_blind(4000))
    assert (d / "tracking_data.csv").stat().st_size > 50_000
    assert seq.load_tracking(d).empty
    assert "non-NBA tracking schema" in capsys.readouterr().out


def test_sequential_still_reads_nba(tmp_path):
    d = _game_dir(tmp_path, "0022400625", _nba(4000))
    out = seq.load_tracking(d)
    assert not out.empty and "player_id" in out.columns


# --- 4. build_shot_clock_buckets ---------------------------------------------

def _possessions(n):
    return pd.DataFrame({"possession_id": range(n), "duration_sec": [12.0] * n,
                         "team": ["LAL"] * n, "result": ["make"] * n})


def test_shot_clock_skips_sport_blind(tmp_path, monkeypatch):
    monkeypatch.setattr(shotclock, "TRACKING_DIR", tmp_path)
    _game_dir(tmp_path, "mlb_2iosUkpL0Bc", _sport_blind(2000),
              extras={"possessions.csv": _possessions(20)})
    rows, warns = shotclock.process_game("mlb_2iosUkpL0Bc")
    assert any("non-NBA tracking schema" in w for w in warns), warns


def test_shot_clock_still_reads_nba(tmp_path, monkeypatch):
    monkeypatch.setattr(shotclock, "TRACKING_DIR", tmp_path)
    _game_dir(tmp_path, "0022400625", _nba(2000),
              extras={"possessions.csv": _possessions(20)})
    _rows, warns = shotclock.process_game("0022400625")
    assert not any("non-NBA tracking schema" in w for w in warns), warns


# --- 5. build_trade_intel ----------------------------------------------------

def test_trade_intel_skips_sport_blind(tmp_path, capsys):
    d = _game_dir(tmp_path, "mlb_2iosUkpL0Bc", _sport_blind(500))
    assert trade._has_player_id(d / "tracking_data.csv") is False
    assert "non-NBA tracking schema" in capsys.readouterr().out
    assert trade._get_team_for_game_slot(d, 1) is None


def test_trade_intel_still_reads_nba(tmp_path):
    d = _game_dir(tmp_path, "0022400625", _nba(500))
    assert trade._has_player_id(d / "tracking_data.csv") is True
    assert trade._get_team_for_game_slot(d, 1) in ("LAL", "BOS")


# --- 6. eval_live_shot_quality -----------------------------------------------

def test_eval_live_skips_sport_blind(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(evallive, "TRACKING_DIR", tmp_path)
    (tmp_path / "mlb_2iosUkpL0Bc").mkdir()
    _sport_blind(50).to_csv(tmp_path / "mlb_2iosUkpL0Bc" / "shot_log_enriched.csv",
                            index=False)
    (tmp_path / "0022400625").mkdir()
    pd.DataFrame({"made": [1, 0], "defender_distance": [4.0, 6.0],
                  "court_zone": ["paint", "three"]}).to_csv(
        tmp_path / "0022400625" / "shot_log_enriched.csv", index=False)
    out = evallive.load_all_shots()
    assert set(out["_game_id"]) == {"0022400625"}
    assert "non-NBA tracking schema" in capsys.readouterr().out


def test_eval_live_raises_when_every_dir_is_foreign(tmp_path, monkeypatch):
    """B3: a foreign schema is skipped and NAMED, never silently returned empty."""
    monkeypatch.setattr(evallive, "TRACKING_DIR", tmp_path)
    (tmp_path / "mlb_2iosUkpL0Bc").mkdir()
    _sport_blind(50).to_csv(tmp_path / "mlb_2iosUkpL0Bc" / "shot_log_enriched.csv",
                            index=False)
    with pytest.raises(RuntimeError):
        evallive.load_all_shots()
