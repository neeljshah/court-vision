"""Existence-floored MLB functional probe bodies for pod preflight."""
from __future__ import annotations


MLB_EXISTENCE_FLOOR_PROBES = {
    "parquet_mlb_games": (
        "import pandas as pd; from domains.mlb.predictor import _corpus_path\n"
        "df = pd.read_parquet(_corpus_path(None))\n"
        "assert len(df) > 0, 'MLB games corpus is empty'\n"
        "print('rows=%d cols=%d' % (len(df), len(df.columns)))\n"),
    "mlb_predictor_init": (
        "from domains.mlb.predictor import MLBPredictor; p = MLBPredictor()\n"
        "assert p.n_games > 0 and len(p.teams) > 0, 'MLB predictor has no games or teams'\n"
        "print('n_games=%d teams=%d r_home=%.3f' % (p.n_games, len(p.teams), p.r_home))\n"),
    # produce_sport() is the BUILDER produce_once() wraps; it never reaches
    # store.save, so this probe cannot overwrite latest.json.
    "produce_mlb_dry": (
        "from predict_service.produce import produce_sport; e = produce_sport('mlb')\n"
        "assert e.status == 'ok' and len(e.predictions) > 0, 'MLB production is unavailable or empty'\n"
        "print('status=%s predictions=%d markets=%d'"
        " % (e.status, len(e.predictions), len(e.markets)))\n"),
}
