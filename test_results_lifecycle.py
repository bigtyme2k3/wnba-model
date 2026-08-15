from scripts import wnba_s19_m06_results_lifecycle as results


def test_current_model_inference_and_recommendation_scope():
    row={
        "model_version":results.CURRENT_MODEL_VERSION,
        "signal":"UNDER","action":"BET","eligible_for_bet":True,
        "player":"Test Player","pred":8.0,"line":9.5,"american_odds":-110,"sportsbook":"FanDuel",
    }
    assert results.model_version(row)==results.CURRENT_MODEL_VERSION
    assert results.recommendation_scope(row)=="LIVE_BET"


def test_unstamped_history_is_legacy():
    row={"prediction_source":"exact_current_slate_sportsbook_props_plus_player_points_v5_plus_current_injury_intelligence"}
    assert results.model_version(row)=="legacy_unversioned"


def test_research_rows_do_not_enter_current_record():
    rows=[
        {"outcome":"WIN","signal":"OVER","action":"BET","player":"A","pred":12,"line":10.5,"american_odds":-110,"sportsbook":"FanDuel"},
        {"outcome":"LOSS","signal":"UNDER","action":"BET","player":"B","pred":8,"line":10.5,"american_odds":105,"sportsbook":"DraftKings"},
        {"outcome":"WIN","signal":"OVER","action":"WATCH","player":"C","pred":12,"line":10.5,"american_odds":-115,"sportsbook":"Fanatics"},
    ]
    recommended=[row for row in rows if results.recommendation_scope(row)=="LIVE_BET"]
    summary=results.result_summary(recommended)
    assert summary["decisions"]==2
    assert summary["wins"]==1
    assert summary["hit_rate"]==0.5


def test_invalid_price_is_quarantined():
    row={"signal":"OVER","action":"BET","player":"A","pred":12,"line":10.5,"american_odds":-50,"sportsbook":"FanDuel"}
    assert results.recommendation_scope(row)=="QUARANTINED"


def test_yesterday_directional_results_separate_bets_and_research():
    rows=[
        {"date":"2026-08-14","signal":"OVER","outcome":"WIN","result_scope":"LIVE_BET"},
        {"date":"2026-08-14","signal":"UNDER","outcome":"LOSS","result_scope":"RESEARCH_ONLY"},
        {"date":"2026-08-14","signal":"OVER","outcome":"WIN","result_scope":"QUARANTINED"},
        {"date":"2026-08-13","signal":"OVER","outcome":"WIN","result_scope":"LIVE_BET"},
    ]
    daily=results.daily_directional_results(rows,"2026-08-14")
    assert daily["all_directional"]["rows"]==2
    assert daily["all_directional"]["wins"]==1
    assert daily["bet"]["decisions"]==1
    assert daily["research"]["decisions"]==1
    assert [row["group"] for row in daily["by_side"]]==["OVER","UNDER"]
