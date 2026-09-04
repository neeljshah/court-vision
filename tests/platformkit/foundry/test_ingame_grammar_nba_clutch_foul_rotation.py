"""Focused construct checks for the S226 clutch foul/rotation grammar."""
from __future__ import annotations

import ast

import numpy as np
import pandas as pd

from scripts.platformkit.foundry import ingame_grammar_nba_clutch_foul_rotation as grammar
from scripts.platformkit.foundry.ingame_screen import BAR


def test_s226_grammar_is_deterministic_and_imports_the_immutable_bar() -> None:
    source = ast.parse(open(grammar.__file__, encoding="utf-8").read())
    assigned = {
        target.id for node in ast.walk(source) if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }
    assert "BAR" not in assigned
    assert grammar.BAR == BAR == 0.004
    first = grammar.enumerate_hypotheses()
    second = grammar.enumerate_hypotheses()
    assert first == second
    assert len(first) == len(grammar.BASE) * len(grammar.TRANSFORMS)
    frame = pd.DataFrame({
        "game": ["g1", "g1", "g2"], "ts": [1, 2, 1],
        **{column: np.arange(3, dtype=float) for column in grammar.BASE},
    })
    grid = grammar.build_grid(frame)
    assert list(grid.index) == list(frame.index)
    assert set(grammar.hypothesis_column(item) for item in first) == set(grid.columns)
