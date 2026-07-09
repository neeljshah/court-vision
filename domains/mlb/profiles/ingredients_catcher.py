"""domains.mlb.profiles.ingredients_catcher -- the single CATCHER attribute
(framing), reusing prereg_shift_framing.py's build_taken_pitches/
classify_borderline machinery verbatim (the SAME functions claims_shift_framing
.build_framing_claim uses for the VALIDATED_CLAIM framing store) -- zero
reimplementation, just a per-SEASON cut instead of that module's pooled
both-seasons cut (the profile schema is windowed by season).
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.prereg_shift_framing import build_taken_pitches, classify_borderline


def build_framing(pitches: pd.DataFrame) -> pd.DataFrame:
    taken = build_taken_pitches(pitches)
    border = taken[classify_borderline(taken)].copy()
    g = border.groupby("fielder_2")["is_strike"].agg(borderline_strike_rate="mean", n="size").reset_index()
    g = g.rename(columns={"fielder_2": "entity_id"})
    g["raw_value"] = g["borderline_strike_rate"]
    g["ingredients"] = g.apply(lambda r: {
        "borderline_strike_rate": round(float(r.borderline_strike_rate), 4),
        "n_borderline_takes": int(r.n),
    }, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {"framing": build_framing}
