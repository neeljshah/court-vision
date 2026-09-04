from scripts.platformkit.eval_gate.s280_cross_venue import parse_kalshi_id, parse_polymarket_id


def test_parse_venue_ids_from_three_required_fixtures():
    assert parse_kalshi_id("KXNBAGAME-26APR26LALHOU-HOU") == ("2026-04-26", "LAL", "HOU")
    assert parse_polymarket_id("nba-mia-min-2026-01-06") == ("2026-01-06", "MIA", "MIN")
    assert parse_kalshi_id("not-an-nba-market") is None
