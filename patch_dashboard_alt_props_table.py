from __future__ import annotations

import os
import re
from pathlib import Path

HTML = Path('docs/index.html')
STYLE_ID = 'alt-props-table-style'
SCRIPT_ID = 'alt-props-table-script'

STYLE = r'''<style id="alt-props-table-style">
.altDesk{padding:4px 0 28px}.altDeskHead{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin:4px 0 14px}.altDeskTitle{font-size:24px;font-weight:900;letter-spacing:.03em}.altDeskCount{color:#8290aa;font-size:11px}.altFilterWrap{border-top:1px solid #18263b;border-bottom:1px solid #18263b;padding:13px 0;margin-bottom:12px}.altFilterLabel{font-size:10px;color:#6f7d96;letter-spacing:.14em;text-transform:uppercase;margin:0 0 7px}.altFilterRow{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px}.altFilterRow:last-child{margin-bottom:0}.altChip{appearance:none;border:1px solid #263854;background:#08111f;color:#a8b3c7;border-radius:8px;padding:8px 13px;font-size:12px;cursor:pointer}.altChip.active{border-color:#2ed69b;box-shadow:0 0 0 1px #2ed69b inset;color:#e9fff8;background:#08231b}.altTableWrap{overflow:auto;border:1px solid #17263c;border-radius:12px;background:#050a12;max-height:74vh}.altTable{width:100%;border-collapse:collapse;min-width:1040px}.altTable th{position:sticky;top:0;z-index:2;background:#070c14;color:#69768d;font-size:10px;letter-spacing:.09em;text-transform:uppercase;text-align:left;padding:0;border-bottom:1px solid #1b2a40}.altSortBtn{appearance:none;border:0;background:transparent;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;width:100%;padding:12px 10px;text-align:left;cursor:pointer;white-space:nowrap}.altSortBtn:hover{color:#c8d2e2;background:#0a1220}.altSortBtn.active{color:#55dfae}.altSortArrow{display:inline-block;margin-left:5px;color:#55dfae;font-size:9px;min-width:8px}.altTable td{padding:13px 10px;border-bottom:1px solid #111d2e;vertical-align:middle;font-size:12px}.altTable tr:hover td{background:#09111d}.altPlayer{font-weight:800;color:#f3f6fb}.altTeam{color:#697890;font-size:10px;margin-top:2px}.altStat{font-weight:800;color:#5ee5b5}.altLine{font-weight:900;color:#f2f5fb}.altOdd{font-weight:900}.altOdd.good{color:#52e0aa}.altOdd.mid{color:#f2c15f}.altBook{color:#8492a8;font-size:10px;margin-top:2px}.altMuted{color:#536078}.altRank{font-weight:800}.oppElite{color:#ff5f70}.oppTough{color:#ff9f43}.oppAverage{color:#ffd166}.oppSoft{color:#76d99b}.oppWeak{color:#22e6a2}.oppLabel{font-size:9px;margin-top:2px}.altSportsbook{color:#aebbd0}.altCaret{color:#44516a;margin-right:7px}.altSummary{display:flex;gap:14px;flex-wrap:wrap;color:#77859c;font-size:11px;margin:0 0 10px}.altSummary b{color:#d9e1ee}.altSortSummary{color:#55dfae}.altEmpty{padding:26px;border:1px solid #263854;border-radius:12px;color:#8795aa;background:#08111f}.altTier{-webkit-font-smoothing:antialiased}
@media(max-width:800px){.altDeskHead{align-items:flex-start;flex-direction:column}.altTableWrap{border-radius:0;margin-left:-10px;margin-right:-10px}.altChip{padding:7px 10px}.altDeskTitle{font-size:21px}.altSortBtn{padding:11px 8px}}
</style>'''

SCRIPT = r'''<script id="alt-props-table-script">(function(){
const originalRender=window.render;
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
let statFilter='ALL', oddsTier='ALL', sortKey=null, sortDir='desc';
const allowedStats=['PTS','REB','AST','3PM','PRA','PR','PA','RA','STL','BLK'];
const columns=[
 ['player','Player','text'],['team','Team','text'],['stat','Stat','text'],['line','ALT Line','number'],['streak','Streak','number'],
 ['l10','L10','number'],['season','Season','number'],['avg','Avg','number'],['opp','Opp Rank','number'],['odds','Odds','number'],['sportsbook','Sportsbook','text']
];
function canonical(){return window.WNBA_CANONICAL_DAILY||{}}
function games(){const c=canonical();return Array.isArray(c.games)?c.games:[]}
function rows(){const p=(window.DATA&&DATA.alt_streaks)||{},c=canonical(),sourceTarget=String(p.target_date||''),currentTarget=String(c.target_date||''),allowed=new Set(['fanduel','draftkings','fanatics']);if(!sourceTarget||!currentTarget||sourceTarget!==currentTarget)return[];return (Array.isArray(p.rows)?p.rows:[]).filter(r=>r.line_type==='alternate'&&Number(r.streak)>=5&&allowed.has(String(r.best_book||'').toLowerCase()))}
function firstValue(obj,keys){for(const k of keys){const v=obj?.[k];if(v!==null&&v!==undefined&&v!=='')return v}return null}
function numValue(obj,keys){const v=firstValue(obj,keys);if(v===null)return null;const n=Number(v);return Number.isFinite(n)?n:null}
function exactPrice(r){const n=Number(r.best_odds);return {side:String(r.side||'—').toUpperCase(),price:Number.isFinite(n)?n:null,book:r.best_book||'—'}}
function tierOk(price){if(oddsTier==='ALL')return true;if(price==null)return false;if(oddsTier==='150')return price<=-150&&price>=-299;if(oddsTier==='300')return price<=-300&&price>=-499;if(oddsTier==='500')return price<=-500;return true}
function enrich(r){return {...r,line:r.alt_line,_best:exactPrice(r),_l10:numValue(r,['l10_pct','last10_pct']),_season:numValue(r,['season_pct']),_avg:numValue(r,['average','avg']),_opp:numValue(r,['opponent_rank'])}}
function ladders(){return rows().map(enrich)}
function sortValue(r,key){if(key==='player')return String(r.player||'').toLowerCase();if(key==='team')return String(r.team||'').toLowerCase();if(key==='stat')return String(r.stat||'').toLowerCase();if(key==='line')return Number(r.line);if(key==='streak')return Number(r.streak);if(key==='l10')return r._l10;if(key==='season')return r._season;if(key==='avg')return r._avg;if(key==='opp')return r._opp;if(key==='odds')return r._best.price;if(key==='sportsbook')return String(r._best.book||'').toLowerCase();return null}
function compareValues(a,b,type,dir){const aMissing=a===null||a===undefined||a===''||(type==='number'&&!Number.isFinite(Number(a)));const bMissing=b===null||b===undefined||b===''||(type==='number'&&!Number.isFinite(Number(b)));if(aMissing&&bMissing)return 0;if(aMissing)return 1;if(bMissing)return -1;let c=0;if(type==='text')c=String(a).localeCompare(String(b));else c=Number(a)-Number(b);return dir==='asc'?c:-c}
function filtered(){const data=ladders().filter(r=>(statFilter==='ALL'||String(r.stat).toUpperCase()===statFilter)&&tierOk(r._best.price));if(sortKey){const meta=columns.find(c=>c[0]===sortKey),type=meta?.[2]||'text';data.sort((a,b)=>compareValues(sortValue(a,sortKey),sortValue(b,sortKey),type,sortDir)||String(a.player||'').localeCompare(String(b.player||''))||Number(a.line)-Number(b.line));return data}return data.sort((a,b)=>{const pa=a._best.price??-9999,pb=b._best.price??-9999;if(pb!==pa)return pb-pa;return String(a.player).localeCompare(String(b.player))||Number(a.line)-Number(b.line)})}
function chips(items,current,kind){return items.map(v=>`<button class="altChip ${v===current?'active':''}" onclick="window.altPropsSetFilter('${kind}','${v}')">${v==='150'?'−150 to −299':v==='300'?'−300 to −499':v==='500'?'−500+':v}</button>`).join('')}
function oddsClass(p){if(p==null)return '';const a=Math.abs(Number(p));return a>=300?'good':a>=150?'mid':''}
function sortHeader(key,label){const active=sortKey===key;const arrow=active?(sortDir==='asc'?'▲':'▼'):'↕';return `<th><button class="altSortBtn ${active?'active':''}" onclick="window.altPropsSort('${key}')" title="Sort ${esc(label)} ascending/descending">${esc(label)}<span class="altSortArrow">${arrow}</span></button></th>`}
function displayPct(v){if(v===null||v===undefined)return '—';return `${Number(v).toFixed(Number(v)%1?1:0)}%`}
function displayNum(v){if(v===null||v===undefined)return '—';return Number(v).toFixed(Number(v)%1?1:0)}
function oppClass(rank){if(rank==null)return {css:'altMuted',label:'—'};if(rank<=3)return {css:'oppElite',label:'ELITE'};if(rank<=5)return {css:'oppTough',label:'TOUGH'};if(rank<=8)return {css:'oppAverage',label:'AVERAGE'};if(rank<=11)return {css:'oppSoft',label:'SOFT'};return {css:'oppWeak',label:'WEAK'}}
function renderTable(){const c=canonical(),data=filtered(),all=ladders(),target=esc(c.target_date||''),root=document.getElementById('root');if(!root)return;const stats=[...new Set(all.map(r=>String(r.stat||'').toUpperCase()).filter(Boolean))].filter(s=>allowedStats.includes(s)),uniquePlayers=new Set(data.map(r=>r.player)).size,uniqueGames=new Set(data.map(r=>r.game).filter(Boolean)).size,sortLabel=sortKey?(columns.find(c=>c[0]===sortKey)?.[1]||sortKey):'Odds',sortText=`${sortLabel} ${sortKey?(sortDir==='asc'?'▲':'▼'):'▼'}`;root.innerHTML=`<div class="section altDesk"><div class="canonGate">CURRENT SLATE · ${target}</div><div class="altDeskHead"><div><div class="altDeskTitle mono">ALT Streaks</div><div class="altDeskCount mono">FanDuel · DraftKings · Fanatics only · one row per exact sportsbook line</div></div></div><div class="altFilterWrap"><div class="altFilterLabel">Stat type</div><div class="altFilterRow">${chips(['ALL',...stats],statFilter,'stat')}</div><div class="altFilterLabel">Odds tier</div><div class="altFilterRow altTier">${chips(['ALL','150','300','500'],oddsTier,'odds')}</div></div><div class="altSummary mono"><span><b>${data.length}</b> sportsbook lines</span><span><b>${uniquePlayers}</b> players</span><span><b>${uniqueGames}</b> active games</span><span class="altSortSummary">Sorted: ${esc(sortText)} · click active header again to reverse · third click resets</span></div>${data.length?`<div class="altTableWrap"><table class="altTable"><thead><tr>${columns.map(c=>sortHeader(c[0],c[1])).join('')}</tr></thead><tbody>${data.map(r=>{const b=r._best,o=oppClass(r._opp);return `<tr><td><span class="altCaret">▸</span><span class="altPlayer">${esc(r.player)}</span></td><td>${esc(r.team||'—')}</td><td class="altStat">${esc(r.stat||'—')}</td><td class="altLine">${b.side==='UNDER'?'U':'O'} ${esc(r.line)}</td><td class="altRank">${esc(r.streak??0)}<div class="altBook">straight</div></td><td class="${r._l10==null?'altMuted':''}">${displayPct(r._l10)}</td><td class="${r._season==null?'altMuted':''}">${displayPct(r._season)}</td><td class="${r._avg==null?'altMuted':''}">${displayNum(r._avg)}</td><td class="${o.css}">${displayNum(r._opp)}<div class="oppLabel">${o.label}</div></td><td><div class="altOdd ${oddsClass(b.price)}">${b.price==null?'—':esc(b.price)}</div></td><td class="altSportsbook">${esc(b.book)}</td></tr>`}).join('')}</tbody></table></div>`:`<div class="altEmpty">No qualifying exact ALT lines are currently available from FanDuel, DraftKings, or Fanatics.</div>`}</div>`;window.scrollTo(0,0)}
window.altPropsSetFilter=function(kind,value){if(kind==='stat')statFilter=value;if(kind==='odds')oddsTier=value;renderTable()};
window.altPropsSort=function(key){if(sortKey!==key){sortKey=key;sortDir='asc'}else if(sortDir==='asc'){sortDir='desc'}else{sortKey=null;sortDir='desc'}renderTable()};
window.render=function(view){if(typeof originalRender==='function')originalRender(view);if(view==='alt-props')setTimeout(renderTable,0)};
window.WNBA_ALT_PROPS_TABLE={version:'1.3',style:'sportsbook-line-streak-table',exact_market_rows:true,row_gate:'target-date-artifact',allowed_sportsbooks:['FanDuel','DraftKings','Fanatics'],sortable_columns:columns.map(c=>c[0])};
})();</script>'''
SCRIPT = SCRIPT.replace(
    'Current alternate lines · canonical sportsbook feed',
    'FanDuel · DraftKings · Fanatics only',
)


def replace_element(html: str, tag: str, element_id: str, replacement: str) -> str:
    pattern = rf'<{tag} id="{re.escape(element_id)}">.*?</{tag}>'
    html, count = re.subn(pattern, lambda _m: replacement, html, count=1, flags=re.S)
    if count:
        return html
    anchor = '</head>' if tag == 'style' else '</body>'
    return html.replace(anchor, replacement + '\n' + anchor, 1)


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    html = HTML.read_text(encoding='utf-8')
    html = replace_element(html, 'style', STYLE_ID, STYLE)
    html = replace_element(html, 'script', SCRIPT_ID, SCRIPT)
    HTML.write_text(html, encoding='utf-8')
    # The ALT table owns only ALT presentation. The performance-panel helper has
    # an optional legacy side effect that re-runs Sprint 19 M03. During a Pages
    # build that can fail on a stale game artifact even when the canonical slate
    # and current V5 inference are already healthy. Suppress that side effect here.
    old_panel_only = os.environ.get('ALT_PANEL_ONLY')
    os.environ['ALT_PANEL_ONLY'] = '1'
    try:
        from patch_dashboard_alt_props_performance_panel import main as apply_alt_performance_panel
        apply_alt_performance_panel()
    finally:
        if old_panel_only is None:
            os.environ.pop('ALT_PANEL_ONLY', None)
        else:
            os.environ['ALT_PANEL_ONLY'] = old_panel_only
    print({'status':'PASS','alt_props_ui':'streak-table','filters':['stat','odds-tier'],'sorting':['player','team','stat','line','streak','l10','season','avg','opp','odds','books'],'performance_panel':'below-table','canonical_only':True,'m03_side_effect':False})


if __name__ == '__main__':
    main()

# Canonical Pages deploy trigger: stable ALT target-date renderer.
