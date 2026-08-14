import wnba_game_performance as gp


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
