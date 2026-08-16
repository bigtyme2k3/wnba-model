import wnba_remaining_season_intelligence as remaining


def test_scoreboard_strength_uses_current_overall_record():
    raw={"events":[{"competitions":[{"competitors":[{
        "team":{"abbreviation":"NY"},
        "records":[{"name":"overall","type":"total","summary":"20-10"}],
    }]}]}]}
    strength=remaining.scoreboard_strength(raw)
    assert round(strength["NY"],4)==0.6667
