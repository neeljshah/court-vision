"""Possession-level Monte-Carlo simulation (FRONT A).

``possession_model``  -- learns P(outcome | state) per possession + points draw.
``rest_of_game_sim``  -- Monte-Carlo rolls a mid-game state to a final-score /
                          win-prob distribution.

Leak-free by construction: every per-possession training row is featurized from
events strictly BEFORE the possession start (within the game) plus optional
team-strength priors the caller derives from games strictly before this game's
date. Walk-forward training/eval only. See ``.planning/ingame/SPEC.md``.
"""
