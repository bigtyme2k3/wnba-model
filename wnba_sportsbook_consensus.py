from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
from collections import defaultdict
import pandas as pd


def read_csv(path):
    try:
        if os.path.exists(path):
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def num(v, d=None):
    try:
        if pd.isna(v): return d
        return float(v)
    except Exception:
        return d


def norm(v):
    return str(v or '').strip().lower()


def american_to_prob(odds):
    o = num(odds, -110)
    if o is None: return None
    return abs(o)/(abs(o)+100) if o < 0 else 100/(o+100)


def better_price(a, b):
    # For American odds, larger number is usually better for bettor: +120 > +105 > -105 > -120.
    if a is None: return b
    if b is None: return a
    return max(float(a), float(b))


def load_props(target):
    for p in [f'data/raw/player_points_{target}.csv', 'data/raw/player_points_today.csv']:
        df = read_csv(p)
        if not df.empty:
            return df, p
    return pd.DataFrame(), None


def load_raw_props(target):
    for p in [f'data/raw/props_raw_{target}.csv', 'data/raw/props_today.csv']:
        df = read_csv(p)
        if not df.empty:
            return df, p
    return pd.DataFrame(), None


def build(target):
    props, props_path = load_props(target)
    raw, raw_path = load_raw_props(target)
    grouped = defaultdict(list)

    # Prefer raw props because they may contain multiple books. Fall back to modeled player_points.
    src_df = raw if not raw.empty else props
    source_used = raw_path or props_path or 'none'
    for _, r in src_df.iterrows():
        player = r.get('player')
        stat = str(r.get('stat', r.get('stat_raw', ''))).upper().replace('THREES','3PM')
        game = r.get('game', r.get('opp', r.get('opp_team', '')))
        line = num(r.get('line'))
        if not player or line is None:
            continue
        book = str(r.get('book', r.get('sportsbook', r.get('source', 'current feed'))) or 'current feed')
        over = num(r.get('over_price'))
        under = num(r.get('under_price'))
        yes = num(r.get('yes_price'))
        no = num(r.get('no_price'))
        key = (str(player), str(game), stat)
        grouped[key].append({'book': book, 'line': line, 'over_price': over, 'under_price': under, 'yes_price': yes, 'no_price': no})

    markets=[]
    books_detected=set()
    for (player, game, stat), rows in grouped.items():
        for r in rows:
            books_detected.add(r['book'])
        lines=[r['line'] for r in rows if r.get('line') is not None]
        over_prices=[r.get('over_price') for r in rows if r.get('over_price') is not None]
        under_prices=[r.get('under_price') for r in rows if r.get('under_price') is not None]
        best_over=None; best_under=None; best_over_book=None; best_under_book=None
        for r in rows:
            if r.get('over_price') is not None and better_price(best_over, r.get('over_price')) == r.get('over_price'):
                best_over = r.get('over_price'); best_over_book = r.get('book')
            if r.get('under_price') is not None and better_price(best_under, r.get('under_price')) == r.get('under_price'):
                best_under = r.get('under_price'); best_under_book = r.get('book')
        avg_line = round(sum(lines)/len(lines),2) if lines else None
        consensus_over_prob = round(sum(american_to_prob(x) for x in over_prices if american_to_prob(x) is not None)/max(1,len(over_prices)),4) if over_prices else None
        consensus_under_prob = round(sum(american_to_prob(x) for x in under_prices if american_to_prob(x) is not None)/max(1,len(under_prices)),4) if under_prices else None
        line_range = round(max(lines)-min(lines),2) if len(lines) > 1 else 0
        markets.append({
            'player': player, 'game': game, 'stat': stat, 'book_count': len(set(r['book'] for r in rows)),
            'market_rows': len(rows), 'consensus_line': avg_line, 'line_range': line_range,
            'best_over_price': best_over, 'best_over_book': best_over_book,
            'best_under_price': best_under, 'best_under_book': best_under_book,
            'consensus_over_probability': consensus_over_prob,
            'consensus_under_probability': consensus_under_prob,
            'status': 'multi_book' if len(set(r['book'] for r in rows)) >= 2 else 'single_feed',
            'books': sorted(set(r['book'] for r in rows))[:10]
        })
    markets.sort(key=lambda x: (x['book_count'], x['line_range']), reverse=True)
    report={
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'summary': {
            'markets': len(markets),
            'multi_book_markets': sum(1 for m in markets if m['status']=='multi_book'),
            'single_feed_markets': sum(1 for m in markets if m['status']=='single_feed'),
            'books_detected': sorted(books_detected),
            'source_used': source_used,
        },
        'diagnosis': 'If books_detected has only one item, the issue is upstream odds ingestion, not the dashboard.',
        'markets': markets[:250]
    }
    os.makedirs('data/warehouse', exist_ok=True); os.makedirs('data/dashboard', exist_ok=True)
    for p in ['data/warehouse/wnba_sportsbook_consensus.json','data/dashboard/wnba_sportsbook_consensus.json']:
        json.dump(report, open(p,'w',encoding='utf-8'), indent=2)
    return report


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date', default=str(date.today())); args=ap.parse_args()
    print('Sportsbook consensus built:', build(args.date)['summary'])

if __name__=='__main__': main()
