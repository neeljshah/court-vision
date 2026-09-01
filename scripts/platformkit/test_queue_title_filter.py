"""The title filter must not drop real games, and must catch the observed junk.

Run: python -m pytest scripts/platformkit/test_queue_title_filter.py -q
"""
from scripts.platformkit.queue_title_filter import rejects

REAL_FOOTBALL = [
    "2003 SEC Football Championship Game | LSU Tigers vs. Georgia Bulldogs | Full Game Replay",
    "2024 SEC Football Championship | Texas Longhorns vs. Georgia Bulldogs | Full Game Replay",
    # No mention of "football" at all -- an inclusion rule would wrongly drop it.
    "Victor Cruz takes over the game | Giants vs. Jets FULL Preseason Game 2010",
]
OBSERVED_JUNK = [
    "Chargers Hall of Fame QB Dan Fouts | NFL Players: Second Acts Podcast",
    "Florida State Seminoles at Florida Gators | Full Match Replay | 2026 SEC Soccer",
    "Kansas vs. Pittsburgh Full Match Replay | 2026 ACC Volleyball",
    "2026 SEC Women's Basketball Tournament South Carolina Gamecocks vs. Texas Longhorns | Full Game",
    "Auburn Press Conference | Week 1 | 2026 SEC Football",
    "ACC Men's Basketball Coaches Teleconference - 2/26/18",
    "SEC AI in Sports Panel",
]


def test_real_football_games_are_kept():
    for title in REAL_FOOTBALL:
        assert rejects(title) is None, title


def test_every_observed_contaminant_is_dropped():
    """These are the actual titles found in the football queue, not inventions."""
    for title in OBSERVED_JUNK:
        assert rejects(title) is not None, title


def test_an_unreadable_title_is_not_treated_as_evidence():
    """Fail open: absence of a title says nothing about the video."""
    assert rejects("") is None
