from scripts import wnba_s19_m06_results_lifecycle as results


def test_current_model_inference_and_recommendation_scope():
    row={
        "prediction_source":"exact_current_slate_sportsbook_props_plus_player_points_v5_plus_current_injury_intelligence",
        "signal":"UNDER","eligible_for_bet":True,
    }
    assert results.model_version(row)==results.CURRENT_MODEL_VERSION
    assert results.recommendation_scope(row)=="RECOMMENDED"


def test_research_rows_do_not_enter_current_record():
    rows=[
        {"outcome":"WIN","signal":"OVER","eligible_for_bet":True},
        {"outcome":"LOSS","signal":"UNDER","eligible_for_bet":True},
        {"outcome":"WIN","signal":"PASS","eligible_for_bet":False},
    ]
    recommended=[row for row in rows if results.recommendation_scope(row)=="RECOMMENDED"]
    summary=results.result_summary(recommended)
    assert summary["decisions"]==2
    assert summary["wins"]==1
    assert summary["hit_rate"]==0.5
