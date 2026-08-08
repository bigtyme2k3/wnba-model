from __future__ import annotations

import json
from pathlib import Path

HTML = Path('docs/index.html')
SCORES = Path('data/dashboard/wnba_alt_streaks.json')
SCRIPT_ID = 'alt-props-score-overlay-script'
STYLE_ID = 'alt-props-score-overlay-style'

STYLE = r'''<style id="alt-props-score-overlay-style">
.altScoreCell{min-width:92px}.altScoreNum{font-size:17px;font-weight:950;color:#55dfae}.altScoreMeta{font-size:9px;color:#8290aa;margin-top:2px}.altScoreBet{color:#55dfae}.altScoreLean{color:#f0c25e}.altScoreWatch{color:#9fb3d1}.altScorePass{color:#6c788d}.altUnscored{color:#566276;font-size:10px}
</style>'''


def load_scores() -> dict:
    try:
        payload=json.load(SCORES.open(encoding='utf-8')) if SCORES.exists() else {}
    except Exception:
        payload={}
    rows=[r for r in payload.get('rows',[]) if isinstance(r,dict)]
    rows=[r for r in rows if r.get('streak_score') is not None and r.get('line_type') == 'alternate']
    return {'target_date': payload.get('target_date'), 'rows': rows}


def esc_script_json(value: dict) -> str:
    return json.dumps(value,separators=(',',':'),ensure_ascii=False).replace('</','<\\/')


def build_script(payload: dict) -> str:
    data=esc_script_json(payload)
    return r'''<script id="alt-props-score-overlay-script">(function(){
const SCORE_DATA=__DATA__;
const norm=v=>String(v??'').trim().toLowerCase().replace(/\s+/g,' ');
let domSortKey=null,domSortDir='asc';
const COL_KEYS=['score','player','team','stat','line','streak','l10','season','avg','opp','odds','books'];
function sideFromCell(text){const t=String(text||'').trim().toUpperCase();return t.startsWith('U')?'UNDER':t.startsWith('O')?'OVER':''}
function lineFromCell(text){const m=String(text||'').match(/-?\d+(?:\.\d+)?/);return m?Number(m[0]):null}
function fullKey(player,team,stat,side,line){return [norm(player),norm(team),String(stat||'').trim().toUpperCase(),String(side||'').toUpperCase(),Number(line)].join('|')}
function looseKey(player,stat,side,line){return [norm(player),String(stat||'').trim().toUpperCase(),String(side||'').toUpperCase(),Number(line)].join('|')}
const INDEX=new Map(), LOOSE=new Map(), AMBIGUOUS=new Set();
for(const r of (SCORE_DATA.rows||[])){
  const fk=fullKey(r.player,r.team,r.stat,r.side,r.alt_line);
  const prior=INDEX.get(fk);
  if(!prior || Number(r.streak_score||0)>Number(prior.streak_score||0)) INDEX.set(fk,r);
  const lk=looseKey(r.player,r.stat,r.side,r.alt_line);
  if(LOOSE.has(lk)){
    const old=LOOSE.get(lk);
    if(norm(old.game)!==norm(r.game)) AMBIGUOUS.add(lk);
    if(Number(r.streak_score||0)>Number(old.streak_score||0)) LOOSE.set(lk,r);
  }else LOOSE.set(lk,r);
}
function findScore(player,team,stat,side,line){
  const exact=INDEX.get(fullKey(player,team,stat,side,line));
  if(exact)return exact;
  const lk=looseKey(player,stat,side,line);
  return AMBIGUOUS.has(lk)?null:LOOSE.get(lk);
}
function scoreClass(action){action=String(action||'').toUpperCase();return action==='BET'?'altScoreBet':action==='LEAN'?'altScoreLean':action==='WATCH'?'altScoreWatch':'altScorePass'}
function pct(v){const n=Number(v);return Number.isFinite(n)?(n*100).toFixed((n*100)%1?1:0)+'%':'—'}
function val(v){const n=Number(v);return Number.isFinite(n)?String(Number(n.toFixed(1))):'—'}
function applyMetrics(td,scored){
  if(!scored)return;
  if(td[4]) td[4].innerHTML='<span class="altRank">'+val(scored.streak)+'</span><div class="altBook">streak</div>';
  if(td[5]) td[5].textContent=pct(scored.l10_pct);
  if(td[6]) td[6].textContent=pct(scored.season_pct);
  if(td[7]) td[7].textContent=val(scored.average);
  if(td[8]) td[8].textContent=val(scored.opponent_rank);
}
function numericText(text){const m=String(text||'').replace(/,/g,'').match(/-?\d+(?:\.\d+)?/);return m?Number(m[0]):null}
function cellValue(tr,key){
  const td=[...tr.children],i=COL_KEYS.indexOf(key),cell=td[i];
  if(!cell)return null;
  if(['score','line','streak','l10','season','avg','opp','odds'].includes(key)) return numericText(cell.textContent);
  return String(cell.textContent||'').trim().toLowerCase();
}
function updateSortHeaders(key,dir){
  const table=document.querySelector('.altTable');if(!table)return;
  const ths=[...table.querySelectorAll('thead th')];
  ths.forEach((th,i)=>{
    const k=COL_KEYS[i],btn=th.querySelector('.altSortBtn');if(!btn)return;
    btn.classList.toggle('active',k===key);
    let arrow=btn.querySelector('.altSortArrow');
    if(!arrow){arrow=document.createElement('span');arrow.className='altSortArrow';btn.appendChild(arrow)}
    arrow.textContent=k===key?(dir==='asc'?'▲':'▼'):'↕';
  });
  const summary=document.querySelector('.altSortSummary');
  if(summary){const label=key?key.replace(/^./,c=>c.toUpperCase()):'Original';summary.textContent=key?'Sorted: '+label+' '+(dir==='asc'?'▲':'▼')+' · click active header again to reverse · third click resets':'Sorted: Original · click a header to sort'}
}
function sortDom(key){
  const table=document.querySelector('.altTable'),tbody=table?.querySelector('tbody');if(!tbody)return;
  if(domSortKey!==key){domSortKey=key;domSortDir='asc'}else if(domSortDir==='asc'){domSortDir='desc'}else{domSortKey=null;domSortDir='asc'}
  const rows=[...tbody.querySelectorAll('tr')];
  rows.forEach((tr,i)=>{if(tr.dataset.altOriginalOrder===undefined)tr.dataset.altOriginalOrder=String(i)});
  if(!domSortKey){rows.sort((a,b)=>Number(a.dataset.altOriginalOrder)-Number(b.dataset.altOriginalOrder))}
  else rows.sort((a,b)=>{
    const av=cellValue(a,domSortKey),bv=cellValue(b,domSortKey);
    const am=av===null||av===undefined||av==='',bm=bv===null||bv===undefined||bv==='';
    if(am&&bm)return Number(a.dataset.altOriginalOrder)-Number(b.dataset.altOriginalOrder);
    if(am)return 1;if(bm)return -1;
    let c=(typeof av==='number'&&typeof bv==='number')?av-bv:String(av).localeCompare(String(bv));
    if(c===0)c=Number(a.dataset.altOriginalOrder)-Number(b.dataset.altOriginalOrder);
    return domSortDir==='asc'?c:-c;
  });
  rows.forEach(tr=>tbody.appendChild(tr));updateSortHeaders(domSortKey,domSortDir);
}
function applyScores(){
  const table=document.querySelector('.altTable');
  if(!table)return;
  const head=table.querySelector('thead tr');
  if(head && !head.querySelector('[data-alt-score-head]')){
    const th=document.createElement('th');th.dataset.altScoreHead='1';th.innerHTML='<button class="altSortBtn" onclick="window.altPropsSort(\'score\')" title="Sort Score ascending/descending">Score<span class="altSortArrow">↕</span></button>';
    head.insertBefore(th,head.firstElementChild);
  }
  let eligible=0,unscored=0,rowNo=0;
  for(const tr of table.querySelectorAll('tbody tr')){
    if(tr.dataset.altOriginalOrder===undefined)tr.dataset.altOriginalOrder=String(rowNo);rowNo++;
    const td=[...tr.children];
    if(!td.length || tr.dataset.altScoreApplied==='1')continue;
    const player=(td[0]?.querySelector('.altPlayer')?.textContent||td[0]?.textContent||'').replace(/^\s*▸\s*/,'').trim();
    const team=(td[1]?.textContent||'').trim();
    const stat=(td[2]?.textContent||'').trim();
    const lineText=(td[3]?.textContent||'').trim();
    const side=sideFromCell(lineText), line=lineFromCell(lineText);
    const scored=findScore(player,team,stat,side,line);
    applyMetrics(td,scored);
    const cell=document.createElement('td');cell.className='altScoreCell';
    if(scored){
      eligible++;
      const score=Number(scored.streak_score).toFixed(1);
      const grade=scored.streak_grade||'—', action=scored.streak_action||'—';
      cell.innerHTML='<div class="altScoreNum">'+score+'</div><div class="altScoreMeta '+scoreClass(action)+'">'+grade+' · '+action+'</div>';
      tr.dataset.performanceEligible='1';
    }else{
      cell.innerHTML='<span class="altUnscored">UNSCORED</span>';
      tr.dataset.performanceEligible='0';
      unscored++;
    }
    tr.insertBefore(cell,tr.firstElementChild);tr.dataset.altScoreApplied='1';
  }
  const summary=document.querySelector('.altSummary');
  if(summary){
    let badge=summary.querySelector('[data-score-eligible]');
    if(!badge){badge=document.createElement('span');badge.dataset.scoreEligible='1';summary.appendChild(badge)}
    badge.innerHTML='<b>'+eligible+'</b> scored / performance eligible'+(unscored?' · '+unscored+' unmatched current rows':'');
  }
}
function later(){setTimeout(applyScores,0);setTimeout(applyScores,60)}
const oldRender=window.render;
if(typeof oldRender==='function')window.render=function(view){const out=oldRender(view);if(view==='alt-props')later();return out};
const oldFilter=window.altPropsSetFilter;
if(typeof oldFilter==='function')window.altPropsSetFilter=function(){const out=oldFilter.apply(this,arguments);domSortKey=null;domSortDir='asc';later();return out};
window.altPropsSort=function(key){later();setTimeout(()=>sortDom(key),70)};
window.WNBA_ALT_PROP_SCORES={version:'1.3',source:'wnba_alt_streaks',alternate_only:true,performance_eligible_only:true,unscored_rows_visible:true,team_optional_match:true,scored_rows:(SCORE_DATA.rows||[]).length,dom_sorting:true,sortable_score:true,sortable_true_metrics:true};
later();
})();</script>'''.replace('__DATA__',data)


def replace_or_insert(html: str, tag: str, element_id: str, replacement: str) -> str:
    start=html.find(f'<{tag} id="{element_id}">')
    if start>=0:
        end=html.find(f'</{tag}>',start)
        if end>=0:return html[:start]+replacement+html[end+len(tag)+3:]
    anchor='</head>' if tag=='style' else '</body>'
    return html.replace(anchor,replacement+'\n'+anchor,1)


def main() -> None:
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    payload=load_scores()
    html=HTML.read_text(encoding='utf-8')
    html=replace_or_insert(html,'style',STYLE_ID,STYLE)
    html=replace_or_insert(html,'script',SCRIPT_ID,build_script(payload))
    HTML.write_text(html,encoding='utf-8')
    print({'status':'PASS','scored_alt_rows':len(payload['rows']),'alternate_only':True,'performance_eligible_only':True,'unscored_rows_visible':True,'team_optional_match':True,'true_streak_metrics':True,'dom_sorting':True,'sortable_score':True})

if __name__=='__main__':main()
