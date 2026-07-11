from __future__ import annotations
import argparse,json,os,glob,re
from datetime import date,datetime,timezone
from collections import defaultdict
import pandas as pd

ALLOWED_BOOKS={"draftkings":"DraftKings","fanduel":"FanDuel","fanatics":"Fanatics"}


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


def american_to_prob(odds):
    o = num(odds, -110)
    if o is None: return None
    return abs(o)/(abs(o)+100) if o < 0 else 100/(o+100)


def better_price(a, b):
    if a is None: return b
    if b is None: return a
    return max(float(a), float(b))


def canonical_book(value):
    raw=str(value or '').strip()
    key=re.sub(r'[^a-z0-9]','',raw.lower())
    if 'draftkings' in key or key in {'dk'}: return 'DraftKings'
    if 'fanduel' in key or key in {'fd'}: return 'FanDuel'
    if 'fanatics' in key or 'pointsbet' in key: return 'Fanatics'
    return None


def row_date(v):
    try:
        if v in (None, '') or pd.isna(v): return ''
        s=str(v).replace('Z','+00:00')
        if 'T' in s: return datetime.fromisoformat(s).date().isoformat()
        return str(v)[:10]
    except Exception: return ''


def filter_target_rows(df, target):
    if df.empty: return df, 'empty', 0, 0
    total=len(df)
    if 'game_date' in df.columns:
        out=df[df['game_date'].astype(str).str[:10] == target].copy(); return out, 'game_date', total, len(out)
    if 'commence_time' in df.columns:
        dates=df['commence_time'].apply(row_date); out=df[dates == target].copy(); return out, 'commence_time', total, len(out)
    if 'date' in df.columns:
        out=df[df['date'].astype(str).str[:10] == target].copy(); return out, 'date', total, len(out)
    return df, 'no_date_column', total, total


def candidates(target):
    preferred=[f'data/raw/line_shopping_{target}.csv',f'data/raw/line_shopping_best_{target}.csv','data/raw/line_shopping_today.csv','data/raw/line_shopping_best_today.csv',f'data/raw/props_raw_{target}.csv','data/raw/props_today.csv',f'data/raw/player_points_{target}.csv','data/raw/player_points_today.csv']
    extras=sorted(glob.glob('data/raw/line_shopping*.csv')+glob.glob('data/raw/props_raw_*.csv'),reverse=True)
    seen=[]
    for p in preferred+extras:
        if p not in seen: seen.append(p)
    return seen


def file_rows(path):
    df=read_csv(path); return df,int(len(df)) if not df.empty else 0


def choose_source(target):
    diagnostics=[]
    for p in candidates(target):
        if not os.path.exists(p): continue
        df,rows=file_rows(p)
        try: cols=list(df.columns) if not df.empty else list(pd.read_csv(p,nrows=0).columns)
        except Exception: cols=[]
        filtered,date_filter,original_rows,target_rows=filter_target_rows(df,target)
        diagnostics.append({'path':p,'rows':rows,'target_rows':target_rows,'date_filter':date_filter,'columns':cols[:30]})
        if target_rows>0: return filtered,p,diagnostics
    return pd.DataFrame(),'none',diagnostics


def add_line_shopping(grouped,df,rejected):
    for _,r in df.iterrows():
        market_type=str(r.get('market_type','')).upper(); player=r.get('player'); stat=str(r.get('stat','')).upper().replace('THREES','3PM'); game=r.get('game'); line=num(r.get('line')); side=str(r.get('side','')).upper()
        if market_type!='PROP' or not player or not stat or line is None: continue
        raw_book=r.get('book_title',r.get('book_key',''))
        book=canonical_book(raw_book)
        if not book:
            rejected[str(raw_book or 'unknown')]+=1
            continue
        odds=num(r.get('odds')); rec={'book':book,'line':line,'over_price':None,'under_price':None,'yes_price':None,'no_price':None}
        if side=='OVER': rec['over_price']=odds
        elif side=='UNDER': rec['under_price']=odds
        elif side=='YES': rec['yes_price']=odds; rec['over_price']=odds
        elif side=='NO': rec['no_price']=odds; rec['under_price']=odds
        else: continue
        grouped[(str(player),str(game),stat)].append(rec)


def add_modeled_props(grouped,df,rejected):
    for _,r in df.iterrows():
        player=r.get('player'); stat=str(r.get('stat',r.get('stat_raw',''))).upper().replace('THREES','3PM'); game=r.get('game',r.get('opp',r.get('opp_team',''))); line=num(r.get('line'))
        if not player or line is None: continue
        raw_book=r.get('book',r.get('sportsbook',r.get('source','')))
        book=canonical_book(raw_book)
        if not book:
            rejected[str(raw_book or 'unknown')]+=1
            continue
        grouped[(str(player),str(game),stat)].append({'book':book,'line':line,'over_price':num(r.get('over_price')),'under_price':num(r.get('under_price')),'yes_price':num(r.get('yes_price')),'no_price':num(r.get('no_price'))})


def build(target):
    src_df,source_used,diagnostics=choose_source(target); grouped=defaultdict(list); rejected=defaultdict(int)
    if not src_df.empty and 'market_type' in src_df.columns and 'side' in src_df.columns: add_line_shopping(grouped,src_df,rejected)
    elif not src_df.empty: add_modeled_props(grouped,src_df,rejected)
    markets=[]; books_detected=set()
    for (player,game,stat),rows in grouped.items():
        merged={}
        for r in rows:
            k=(r['book'],r['line']); m=merged.setdefault(k,{'book':r['book'],'line':r['line'],'over_price':None,'under_price':None,'yes_price':None,'no_price':None})
            for fld in ['over_price','under_price','yes_price','no_price']:
                if r.get(fld) is not None: m[fld]=r.get(fld)
        rows=list(merged.values())
        for r in rows: books_detected.add(r['book'])
        lines=[r['line'] for r in rows if r.get('line') is not None]; over_prices=[r.get('over_price') for r in rows if r.get('over_price') is not None]; under_prices=[r.get('under_price') for r in rows if r.get('under_price') is not None]
        best_over=best_under=None; best_over_book=best_under_book=None
        for r in rows:
            if r.get('over_price') is not None and better_price(best_over,r.get('over_price'))==r.get('over_price'): best_over=r.get('over_price'); best_over_book=r.get('book')
            if r.get('under_price') is not None and better_price(best_under,r.get('under_price'))==r.get('under_price'): best_under=r.get('under_price'); best_under_book=r.get('book')
        avg_line=round(sum(lines)/len(lines),2) if lines else None; line_range=round(max(lines)-min(lines),2) if len(lines)>1 else 0
        markets.append({'player':player,'game':game,'stat':stat,'book_count':len(set(r['book'] for r in rows)),'market_rows':len(rows),'consensus_line':avg_line,'line_range':line_range,'best_over_price':best_over,'best_over_book':best_over_book,'best_under_price':best_under,'best_under_book':best_under_book,'consensus_over_probability':round(sum(american_to_prob(x) for x in over_prices if american_to_prob(x) is not None)/max(1,len(over_prices)),4) if over_prices else None,'consensus_under_probability':round(sum(american_to_prob(x) for x in under_prices if american_to_prob(x) is not None)/max(1,len(under_prices)),4) if under_prices else None,'status':'multi_book' if len(set(r['book'] for r in rows))>=2 else 'single_feed','books':sorted(set(r['book'] for r in rows))})
    markets.sort(key=lambda x:(x['book_count'],x['line_range']),reverse=True)
    stale_candidates=[d for d in diagnostics if d.get('rows',0)>0 and d.get('target_rows',0)==0]
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'markets':len(markets),'multi_book_markets':sum(1 for m in markets if m['status']=='multi_book'),'single_feed_markets':sum(1 for m in markets if m['status']=='single_feed'),'books_detected':sorted(books_detected),'allowed_books':['DraftKings','FanDuel','Fanatics'],'rejected_book_rows':sum(rejected.values()),'rejected_books':dict(sorted(rejected.items(),key=lambda x:x[1],reverse=True)),'source_used':source_used,'stale_sources_rejected':[d['path'] for d in stale_candidates[:10]]},'diagnosis':'Strict mode: target-date rows only; sportsbook consensus restricted to DraftKings, FanDuel, and Fanatics.','input_diagnostics':diagnostics,'markets':markets[:300]}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_sportsbook_consensus.json','data/dashboard/wnba_sportsbook_consensus.json']: json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Sportsbook consensus built:',build(args.date)['summary'])

if __name__=='__main__': main()
