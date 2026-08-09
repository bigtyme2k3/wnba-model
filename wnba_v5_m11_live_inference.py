"""V5-M11 live inference bridge.

Applies the M05 KNN research champion to the current ranked opportunity board.
Live features are reconstructed only from certified historical player/stat games
strictly before the board date. No V4 probability is reused or relabeled as V5.
Sprint 3 M01 freshness guard must explicitly permit live inference.

Outputs:
  data/dashboard/wnba_v5_live_inference.json
  data/dashboard/wnba_v5_live_inference.csv
  data/dashboard/wnba_v5_m11_report.json
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

FEATURES = Path('data/dashboard/wnba_v5_historical_features.csv')
RANKINGS = Path('data/warehouse/wnba_opportunity_rankings.json')
M05 = Path('data/dashboard/wnba_v5_m05_report.json')
FRESHNESS = Path('data/dashboard/wnba_v5_s3_m01_freshness.json')
OUT_JSON = Path('data/dashboard/wnba_v5_live_inference.json')
OUT_CSV = Path('data/dashboard/wnba_v5_live_inference.csv')
REPORT = Path('data/dashboard/wnba_v5_m11_report.json')

FEATURE_NAMES = [
    'market_implied_probability', 'line_minus_prior_mean', 'rolling3_actual_mean',
    'rolling5_actual_mean', 'rolling5_actual_std', 'rolling5_trend_slope',
    'historical_hit_rate_at_current_line', 'historical_hit_rate_l5_at_current_line',
    'prior_games'
]
MIN_PRIOR = 3
K = 15


def f(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def clamp(v, lo=0.02, hi=0.98):
    return max(lo, min(hi, v))


def implied(odds):
    o = f(odds)
    if o is None or o == 0:
        return None
    return abs(o) / (abs(o) + 100.0) if o < 0 else 100.0 / (o + 100.0)


def slope(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2.0
    ym = mean(xs)
    den = sum((i - xm) ** 2 for i in range(n))
    return sum((i - xm) * (y - ym) for i, y in enumerate(xs)) / den if den else 0.0


def hit(actual, line, side):
    s = str(side or '').upper()
    if s == 'OVER':
        return 1.0 if actual > line else (0.5 if actual == line else 0.0)
    if s == 'UNDER':
        return 1.0 if actual < line else (0.5 if actual == line else 0.0)
    return None


def rowx(r):
    out = []
    for k in FEATURE_NAMES:
        x = f(r.get(k))
        if x is None:
            return None
        out.append(x)
    return out


def standardize(X):
    p = len(X[0])
    mu = [mean(r[j] for r in X) for j in range(p)]
    sd = []
    for j in range(p):
        s = pstdev(r[j] for r in X)
        sd.append(s if s > 1e-8 else 1.0)
    Z = [[(r[j] - mu[j]) / sd[j] for j in range(p)] for r in X]
    return Z, mu, sd


def knn(train, x, k=K):
    X = [t[0] for t in train]
    Z, mu, sd = standardize(X)
    zx = [(x[j] - mu[j]) / sd[j] for j in range(len(x))]
    ds = []
    for z, (_, y) in zip(Z, train):
        d = sum((z[j] - zx[j]) ** 2 for j in range(len(zx)))
        ds.append((d, y))
    ds.sort(key=lambda t: t[0])
    q = ds[:min(k, len(ds))]
    weights = [1.0 / (math.sqrt(d) + 0.25) for d, _ in q]
    den = sum(weights)
    p = clamp(sum(w * y for w, (_, y) in zip(weights, q)) / den)
    avg_distance = sum(math.sqrt(d) for d, _ in q) / len(q)
    neighbor_rate = sum(y for _, y in q) / len(q)
    return p, avg_distance, neighbor_rate, len(q)


def ranking_rows(payload):
    if not isinstance(payload, dict):
        return []
    rows = payload.get('all_ranked')
    if isinstance(rows, list) and rows:
        return rows
    rows = payload.get('top_opportunities')
    return rows if isinstance(rows, list) else []


def line_of(r):
    for k in ('best_line', 'line', 'alt_line'):
        x = f(r.get(k))
        if x is not None:
            return x
    return None


def odds_of(r):
    for k in ('best_odds', 'american_odds', 'odds', 'price'):
        x = f(r.get(k))
        if x is not None:
            return x
    return None


def rank_key(r):
    existing = r.get('ranking_key')
    if existing:
        return str(existing)
    return '|'.join(norm(x) for x in (
        r.get('date'), r.get('player'), r.get('game'),
        r.get('market') or r.get('stat'), r.get('side') or r.get('signal')
    ))


def build_history(feature_rows):
    unique = {}
    for r in feature_rows:
        player = norm(r.get('player'))
        stat = str(r.get('stat') or '').upper()
        date = str(r.get('game_date') or '')[:10]
        gid = str(r.get('game_id') or '')
        actual = f(r.get('target_actual'))
        if not player or not stat or not date or actual is None:
            continue
        unique[(player, stat, date, gid)] = actual
    hist = defaultdict(list)
    for (player, stat, date, gid), actual in unique.items():
        hist[(player, stat)].append({'date': date, 'game_id': gid, 'actual': actual})
    for k in hist:
        hist[k].sort(key=lambda x: (x['date'], x['game_id']))
    return hist


def live_features(r, history, target_date):
    player = norm(r.get('player'))
    stat = str(r.get('market') or r.get('stat') or '').upper()
    side = str(r.get('side') or r.get('signal') or '').upper()
    line = line_of(r)
    odds = odds_of(r)
    market_p = implied(odds)
    if not player or not stat or side not in {'OVER', 'UNDER'} or line is None or market_p is None:
        return None, 'MISSING_MARKET_FIELDS', 0
    prior = [x for x in history.get((player, stat), []) if x['date'] < target_date]
    actuals = [x['actual'] for x in prior]
    if len(actuals) < MIN_PRIOR:
        return None, 'INSUFFICIENT_PLAYER_STAT_HISTORY', len(actuals)
    h3 = actuals[-3:]
    h5 = actuals[-5:]
    past_hits = [hit(x, line, side) for x in actuals]
    h5_hits = [hit(x, line, side) for x in h5]
    vals = {
        'market_implied_probability': market_p,
        'line_minus_prior_mean': line - mean(actuals),
        'rolling3_actual_mean': mean(h3),
        'rolling5_actual_mean': mean(h5),
        'rolling5_actual_std': pstdev(h5) if len(h5) >= 2 else 0.0,
        'rolling5_trend_slope': slope(h5),
        'historical_hit_rate_at_current_line': mean(past_hits),
        'historical_hit_rate_l5_at_current_line': mean(h5_hits),
        'prior_games': float(len(actuals)),
    }
    return vals, None, len(actuals)


def probability_band(p):
    if p >= 0.70: return '70%+'
    if p >= 0.65: return '65-69.9%'
    if p >= 0.60: return '60-64.9%'
    if p >= 0.55: return '55-59.9%'
    if p >= 0.50: return '50-54.9%'
    return '<50%'


def publish_blocked(now, freshness):
    rankings = json.loads(RANKINGS.read_text(encoding='utf-8')) if RANKINGS.exists() else {}
    rows = ranking_rows(rankings)
    report = {
        'version':'V5','module':'V5-M11','stage':'LIVE_V5_INFERENCE',
        'status':'BLOCKED_STALE_SLATE','generated_at_utc':now,
        'target_date':rankings.get('target_date'),'ranked_rows':len(rows),
        'scored_rows':0,'unscored_rows':len(rows),'scoring_coverage_pct':0.0,
        'research_champion':'KNN','training_rows':None,'freshness_guard_status':freshness.get('status'),
        'freshness_reason':freshness.get('reason'),'research_only':True,'production_ready':False,
        'next_action':'REFRESH_CURRENT_OPPORTUNITY_BOARD'
    }
    unscored=[{
        'ranking_key':rank_key(r),'date':r.get('date'),'player':r.get('player'),'game':r.get('game'),
        'market':r.get('market') or r.get('stat'),'side':r.get('side') or r.get('signal'),
        'line':line_of(r),'odds':odds_of(r),'best_book':r.get('best_book'),'prior_games':None,
        'status':'UNSCORED','reason':'BLOCKED_STALE_SLATE'
    } for r in rows]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({'report':report,'scored':[],'unscored':unscored},indent=2)+'\n',encoding='utf-8')
    fields=['ranking_key','date','player','game','market','side','line','odds','best_book','prior_games','status','model','knn_probability','v5_probability','market_implied_probability','probability_edge','probability_band','confidence_score','uncertainty_score','neighbor_count','neighbor_hit_rate','average_neighbor_distance']
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        csv.DictWriter(h,fieldnames=fields).writeheader()
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


def main():
    now = datetime.now(timezone.utc).isoformat()
    m05 = json.loads(M05.read_text(encoding='utf-8')) if M05.exists() else {}
    if m05.get('research_champion') != 'KNN':
        raise SystemExit('M11_BLOCKED: M05 research champion is not KNN')

    freshness=json.loads(FRESHNESS.read_text(encoding='utf-8')) if FRESHNESS.exists() else {}
    if not freshness or freshness.get('allow_live_inference') is not True:
        publish_blocked(now, freshness or {'status':'MISSING_FRESHNESS_GUARD','reason':'S3-M01 freshness output is required before live scoring.'})
        return

    feature_rows = list(csv.DictReader(FEATURES.open(encoding='utf-8-sig', newline='')))
    train = []
    for r in feature_rows:
        x = rowx(r)
        y = f(r.get('target_win'))
        pg = int(f(r.get('prior_games'), 0) or 0)
        if x is not None and y in (0.0, 1.0) and pg >= MIN_PRIOR:
            train.append((x, int(y)))
    if len(train) < 40:
        raise SystemExit('M11_BLOCKED: insufficient certified KNN training rows')

    history = build_history(feature_rows)
    rankings = json.loads(RANKINGS.read_text(encoding='utf-8')) if RANKINGS.exists() else {}
    rows = ranking_rows(rankings)
    target_date = str(rankings.get('target_date') or (rows[0].get('date') if rows else '') or '')[:10]
    if not target_date:
        raise SystemExit('M11_BLOCKED: no ranked target date')

    scored = []
    unscored = []
    for r in rows:
        vals, reason, prior_games = live_features(r, history, target_date)
        base = {
            'ranking_key': rank_key(r),'date': r.get('date') or target_date,'player': r.get('player'),
            'game': r.get('game'),'market': r.get('market') or r.get('stat'),'side': r.get('side') or r.get('signal'),
            'line': line_of(r),'odds': odds_of(r),'best_book': r.get('best_book'),'prior_games': prior_games,
        }
        if vals is None:
            unscored.append({**base, 'status': 'UNSCORED', 'reason': reason})
            continue
        x = [vals[k] for k in FEATURE_NAMES]
        p, avg_dist, neighbor_rate, neighbor_count = knn(train, x)
        market_p = vals['market_implied_probability']
        uncertainty = min(1.0, math.sqrt(p * (1 - p)) * 2.0)
        confidence = max(0.0, min(1.0, (1.0 - uncertainty) * 0.65 + min(prior_games / 10.0, 1.0) * 0.20 + (1.0 / (1.0 + avg_dist)) * 0.15))
        scored.append({
            **base,'status':'SCORED','model':'KNN','knn_probability':round(p,6),'v5_probability':round(p,6),
            'market_implied_probability':round(market_p,6),'probability_edge':round(p-market_p,6),
            'probability_band':probability_band(p),'confidence_score':round(confidence,6),'uncertainty_score':round(uncertainty,6),
            'neighbor_count':neighbor_count,'neighbor_hit_rate':round(neighbor_rate,6),'average_neighbor_distance':round(avg_dist,6),
            'feature_snapshot':{k:round(vals[k],6) for k in FEATURE_NAMES},'research_only':True,
        })

    coverage = (100.0 * len(scored) / len(rows)) if rows else 0.0
    report = {
        'version':'V5','module':'V5-M11','stage':'LIVE_V5_INFERENCE','status':'READY_SHADOW' if scored else 'STANDBY_NO_SCORABLE_ROWS',
        'generated_at_utc':now,'target_date':target_date,'ranked_rows':len(rows),'scored_rows':len(scored),'unscored_rows':len(unscored),
        'scoring_coverage_pct':round(coverage,2),'research_champion':'KNN','training_rows':len(train),
        'freshness_guard_status':freshness.get('status'),'leakage_policy':'Live rolling features use only certified player/stat games strictly before target_date.',
        'research_only':True,'production_ready':False,'next_module':'V5-M12 Post-Game Learning + Forward Validation',
    }
    payload={'report':report,'scored':scored,'unscored':unscored}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    fields=['ranking_key','date','player','game','market','side','line','odds','best_book','prior_games','status','model','knn_probability','v5_probability','market_implied_probability','probability_edge','probability_band','confidence_score','uncertainty_score','neighbor_count','neighbor_hit_rate','average_neighbor_distance']
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for r in scored:w.writerow({k:r.get(k) for k in fields})
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
