import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="player-detail-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function num(v,d=0){let n=Number(v);return isNaN(n)?d:n}
  function pct(v){return typeof v==='number'?Math.round(v*100)+'%':'—'}
  function arr(v){if(Array.isArray(v))return v;if(!v)return[];try{let x=JSON.parse(v);return Array.isArray(x)?x:[]}catch(e){return[]}}
  function playerRows(name){return (DATA.props||DATA.player_points||DATA.props_board||[]).filter(p=>String(p.player||'')===String(name||''))}
  function statPill(row){return `<span class="pd-pill ${row.conf==='HIGH'?'high':row.conf==='MED'?'med':''}">${safe(row.stat)}</span>`}
  function metric(label,value,sub=''){return `<article class="pd-metric"><span>${label}</span><b>${safe(value)}</b>${sub?`<small>${sub}</small>`:''}</article>`}
  function trendBoxes(row){let vals=arr(row.last5_vals),opps=arr(row.last5_opps),line=num(row.line),sig=row.signal;if(!vals.length)return '<div class="empty mini">No recent data yet.</div>';return `<div class="pd-trend">${vals.slice(0,5).map((v,i)=>{let hit=sig?(sig==='UNDER'?v<line:sig==='OVER'?v>line:sig==='YES'?v==1:v==0):null;let cls=hit===null?'neutral':hit?'hit':'miss';return `<div class="pd-trend-box ${cls}"><b>${v}</b><span>${safe(opps[i],'')}</span></div>`}).join('')}</div>`}
  function reasons(row){let list=[]; if(row.edge!==undefined)list.push(`Model edge: ${safe(row.edge)}`); if(row.ev_pct!==undefined)list.push(`Expected value: ${safe(row.ev_pct)}%`); if(row.best_book_title||row.best_book)list.push(`Best sportsbook: ${safe(row.best_book_title||row.best_book)}`); if(row.last5_hit!==undefined)list.push(`Last 5 hit rate: ${pct(row.last5_hit)}`); if(row.last10_hit!==undefined)list.push(`Last 10 hit rate: ${pct(row.last10_hit)}`); if(row.opp_rank)list.push(`Opponent rank: ${safe(row.opp_rank)}`); if(row.injury_status&&row.injury_status!=='ACTIVE')list.push(`Injury status: ${row.injury_status}`); if(row.reasoning)list.push(row.reasoning); return list.map(x=>`<li>${x}</li>`).join('')}
  function similarRows(rows,current){return rows.filter(r=>r.stat!==current.stat).slice(0,8).map(r=>`<article class="pd-side-row"><div>${statPill(r)} <b>${safe(r.signal)}</b></div><div>${safe(r.pred)} vs ${safe(r.line)}</div><div class="${num(r.ev_pct)>0?'good':'bad'}">${safe(r.ev_pct)}%</div></article>`).join('') || '<div class="empty mini">No other active markets for this player.</div>'}
  window.openPlayerDetail=function(name,stat){
    const rows=playerRows(name); if(!rows.length)return;
    const row=rows.find(r=>String(r.stat)===String(stat))||rows[0];
    const modal=document.createElement('div'); modal.className='pd-modal';
    modal.innerHTML=`<div class="pd-backdrop" onclick="this.closest('.pd-modal').remove()"></div><section class="pd-panel"><button class="pd-close" onclick="this.closest('.pd-modal').remove()">×</button><header class="pd-header"><div><div class="pd-kicker">Player Detail</div><h2>${safe(row.player)}</h2><p>${safe(row.team)} · ${safe(row.pos)} · ${safe(row.game)} · ${safe(row.injury_status,'ACTIVE')}</p></div><div class="pd-score"><span>${safe(row.score_label||row.grade||row.conf)}</span><b>${safe(row.score,row.conf)}</b></div></header><div class="pd-grid">${metric('Projection', row.stat==='DD'||row.stat==='TD'?Math.round(num(row.pred)*100)+'%':row.pred, `${safe(row.stat)} model`)}${metric('Line', row.stat==='DD'||row.stat==='TD'?'YES':row.line, `${safe(row.best_book_title||row.best_book,'Best book —')}`)}${metric('Edge', row.edge, safe(row.signal))}${metric('EV', safe(row.ev_pct)+'%', `Fair ${safe(row.fair_odds)} · ${safe(row.model_prob_pct)}%`)}</div><div class="pd-main"><article class="pd-card"><h3>Trend Snapshot</h3>${trendBoxes(row)}<div class="pd-hit-grid">${metric('L5 Hit', pct(row.last5_hit), row.signal)}${metric('L10 Hit', pct(row.last10_hit), row.signal)}${metric('Opp Rank', row.opp_rank, '1 tough · 15 easy')}</div></article><article class="pd-card"><h3>Why the Model Likes It</h3><ul class="pd-reasons">${reasons(row)}</ul></article><article class="pd-card"><h3>Other Player Markets</h3>${similarRows(rows,row)}</article><article class="pd-card"><h3>H2H / Matchup</h3><div class="pd-h2h">${arr(row.h2h_last5).length?arr(row.h2h_last5).map(v=>`<span>${v}</span>`).join(''):'<span>—</span>'}</div><p class="pd-note">This panel uses the current baked dashboard data. Deeper similarity matching can plug in when the Strategy Lab/backtest dataset is complete.</p></article></div></section>`;
    document.body.appendChild(modal);
  };
  function attachClickable(){document.querySelectorAll('#tab-props .prop-row .player-name').forEach(el=>{if(el.dataset.pd)return;el.dataset.pd='1';el.style.cursor='pointer';el.title='Open player detail';el.onclick=function(e){e.stopPropagation();let row=el.closest('.prop-row');let stat=row?row.querySelector('.stat-pill')?.textContent:null;openPlayerDetail(el.textContent.trim(),stat)}})}
  const obs=new MutationObserver(()=>attachClickable());obs.observe(document.body,{childList:true,subtree:true});setTimeout(attachClickable,500);
})();
</script>
'''

CSS = r'''
<style id="player-detail-ui-v1-css">
.pd-modal{position:fixed;inset:0;z-index:9999}.pd-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.72);backdrop-filter:blur(6px)}.pd-panel{position:absolute;right:0;top:0;height:100%;width:min(760px,96vw);overflow:auto;background:#080b13;border-left:1px solid rgba(255,255,255,.09);box-shadow:-24px 0 60px #000;padding:22px}.pd-close{position:sticky;top:0;float:right;width:38px;height:38px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#111827;color:#e2e8f0;font-size:24px;z-index:2}.pd-header{display:flex;justify-content:space-between;gap:15px;margin:12px 0 18px}.pd-kicker{color:#60a5fa;font-size:11px;letter-spacing:1.6px;text-transform:uppercase;font-weight:900}.pd-header h2{margin:5px 0 6px;font-size:30px}.pd-header p{color:#7b879b;margin:0}.pd-score{text-align:right}.pd-score span{display:block;color:#7b879b;font-size:11px;text-transform:uppercase}.pd-score b{font-size:34px;color:#00e5a0}.pd-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.pd-metric{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:12px}.pd-metric span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.pd-metric b{display:block;font-size:21px;margin-top:5px}.pd-metric small{display:block;color:#7b879b;margin-top:4px;font-size:11px}.pd-main{display:grid;grid-template-columns:1fr 1fr;gap:12px}.pd-card{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.pd-card h3{margin:0 0 12px}.pd-trend{display:flex;gap:8px}.pd-trend-box{width:54px;height:58px;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,.08)}.pd-trend-box b{font-size:18px}.pd-trend-box span{font-size:10px;opacity:.7}.pd-trend-box.hit{background:rgba(0,229,160,.18);color:#00e5a0}.pd-trend-box.miss{background:rgba(248,113,113,.16);color:#f87171}.pd-trend-box.neutral{background:rgba(148,163,184,.12);color:#94a3b8}.pd-hit-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.pd-reasons{margin:0;padding-left:18px;color:#cbd5e1;line-height:1.5}.pd-side-row{display:grid;grid-template-columns:1fr 90px 70px;gap:8px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.06)}.pd-pill{background:#ffffff10;border-radius:999px;padding:3px 7px;font-size:11px;font-weight:900}.pd-pill.high{color:#00e5a0}.pd-pill.med{color:#f5c518}.pd-h2h{display:flex;gap:8px;flex-wrap:wrap}.pd-h2h span{background:#111827;border:1px solid rgba(255,255,255,.08);padding:8px 10px;border-radius:10px;font-weight:900}.pd-note{color:#7b879b;font-size:12px;line-height:1.4}.empty.mini{font-size:12px;padding:10px;color:#7b879b}@media(max-width:720px){.pd-grid,.pd-main{grid-template-columns:1fr 1fr}.pd-panel{width:100vw}.pd-header{flex-direction:column}.pd-score{text-align:left}}@media(max-width:480px){.pd-grid,.pd-main{grid-template-columns:1fr}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="player-detail-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="player-detail-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ player detail UI patch applied')

if __name__=='__main__':
    main()
