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
    # Only rows with a real frozen model score are eligible for ALT Performance.
    rows=[r for r in rows if r.get('streak_score') is not None]
    return {'target_date': payload.get('target_date'), 'rows': rows}


def esc_script_json(value: dict) -> str:
    return json.dumps(value,separators=(',',':'),ensure_ascii=False).replace('</','<\\/')


def build_script(payload: dict) -> str:
    data=esc_script_json(payload)
    return r'''<script id="alt-props-score-overlay-script">(function(){
const SCORE_DATA=__DATA__;
const norm=v=>String(v??'').trim().toLowerCase().replace(/\s+/g,' ');
function sideFromCell(text){const t=String(text||'').trim().toUpperCase();return t.startsWith('U')?'UNDER':t.startsWith('O')?'OVER':''}
function lineFromCell(text){const m=String(text||'').match(/-?\d+(?:\.\d+)?/);return m?Number(m[0]):null}
function key(player,team,stat,side,line){return [norm(player),norm(team),String(stat||'').trim().toUpperCase(),String(side||'').toUpperCase(),Number(line)].join('|')}
const INDEX=new Map();
for(const r of (SCORE_DATA.rows||[])){
  const k=key(r.player,r.team,r.stat,r.side,r.alt_line);
  const prior=INDEX.get(k);
  if(!prior || Number(r.streak_score||0)>Number(prior.streak_score||0)) INDEX.set(k,r);
}
function scoreClass(action){action=String(action||'').toUpperCase();return action==='BET'?'altScoreBet':action==='LEAN'?'altScoreLean':action==='WATCH'?'altScoreWatch':'altScorePass'}
function applyScores(){
  const table=document.querySelector('.altTable');
  if(!table)return;
  const head=table.querySelector('thead tr');
  if(head && !head.querySelector('[data-alt-score-head]')){
    const th=document.createElement('th');th.dataset.altScoreHead='1';th.innerHTML='<div class="altSortBtn" style="cursor:default">Score</div>';
    head.insertBefore(th,head.firstElementChild);
  }
  let eligible=0,unscored=0;
  for(const tr of table.querySelectorAll('tbody tr')){
    const td=[...tr.children];
    if(!td.length)continue;
    if(tr.dataset.altScoreApplied==='1')continue;
    const player=(td[0]?.querySelector('.altPlayer')?.textContent||td[0]?.textContent||'').replace(/^\s*▸\s*/,'').trim();
    const team=(td[1]?.textContent||'').trim();
    const stat=(td[2]?.textContent||'').trim();
    const lineText=(td[3]?.textContent||'').trim();
    const side=sideFromCell(lineText), line=lineFromCell(lineText);
    const scored=INDEX.get(key(player,team,stat,side,line));
    const cell=document.createElement('td');cell.className='altScoreCell';
    if(scored){
      eligible++;
      const score=Number(scored.streak_score).toFixed(1);
      const grade=scored.streak_grade||'—', action=scored.streak_action||'—';
      cell.innerHTML='<div class="altScoreNum">'+score+'</div><div class="altScoreMeta '+scoreClass(action)+'">'+grade+' · '+action+'</div>';
      tr.dataset.performanceEligible='1';
    }else{
      // A missing model score must never remove a valid current sportsbook market.
      // Keep the market visible and mark it ineligible for performance snapshotting.
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
    badge.innerHTML='<b>'+eligible+'</b> scored / performance eligible'+(unscored?' · '+unscored+' unscored visible':'');
  }
}
function later(){setTimeout(applyScores,0);setTimeout(applyScores,60)}
const oldRender=window.render;
if(typeof oldRender==='function')window.render=function(view){const out=oldRender(view);if(view==='alt-props')later();return out};
for(const name of ['altPropsSetFilter','altPropsSort']){
  const fn=window[name];
  if(typeof fn==='function')window[name]=function(){const out=fn.apply(this,arguments);later();return out};
}
window.WNBA_ALT_PROP_SCORES={version:'1.1',source:'wnba_alt_streaks',performance_eligible_only:true,unscored_rows_visible:true,scored_rows:(SCORE_DATA.rows||[]).length};
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
    print({'status':'PASS','scored_alt_rows':len(payload['rows']),'performance_eligible_only':True,'unscored_rows_visible':True})

if __name__=='__main__':main()
