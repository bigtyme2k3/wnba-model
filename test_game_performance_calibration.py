import wnba_game_performance as gp
import wnba_sprint2_prediction_engine as game_engine


def test_calibration_requires_segment_depth():
    rows=[]
    for i in range(12):
        rows.append({"graded":True,"probability":0.8,"result":"WIN" if i<6 else "LOSS"})
    out=gp.calibration(rows,"probability",lambda row:row["result"])
    assert out["samples"]==12
    assert out["status"]=="COLLECTING"
    assert out["diagnosis"]=="OVERCONFIDENT"
    assert out["buckets"][0]["bucket_ready"] is False
    assert out["buckets"][0]["shrunk_empirical_probability"]==0.5


def test_recommended_performance_excludes_passes():
    rows=[
        {"graded":True,"result":"WIN","recommendation":"A"},
        {"graded":True,"result":"LOSS","recommendation":"A"},
        {"graded":True,"result":"PASS","recommendation":"PASS"},
    ]
    out=gp.market_summary(rows,"result","recommendation")
    assert out["decisions"]==2
    assert out["record"]=={"wins":1,"losses":1,"pushes":0}
    assert out["scope"]=="RECOMMENDED_WAGERS_ONLY"
    assert out["sample_sufficient"] is False


def test_legacy_rows_are_identified_without_rewriting_ledger():
    row={"total_source":"standings_strength+market_prior"}
    assert gp.row_model_version(row)==gp.LEGACY_MODEL_VERSION
    assert "model_version" not in row


def test_team_history_blocks_target_and_future_games():
    perf={"result_history":[
        {"graded":True,"target_date":"2026-08-13","away_team":"Away","home_team":"Home","actual_away_score":80,"actual_home_score":90},
        {"graded":True,"target_date":"2026-08-14","away_team":"Away","home_team":"Home","actual_away_score":81,"actual_home_score":91},
        {"graded":True,"target_date":"2026-08-15","away_team":"Away","home_team":"Home","actual_away_score":82,"actual_home_score":92},
    ]}
    history=game_engine.build_team_history(perf,"2026-08-14")
    assert [row["date"] for row in history["Away"]]==["2026-08-13"]
