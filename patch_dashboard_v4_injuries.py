"""Add injury freshness strip, slate injury summary, and game-level injury details to Dashboard V4."""
from __future__ import annotations
import json,re
from pathlib import Path

HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_injury_intelligence.json')
CSS='''
/* INJURY_UI_START */
.injuryStrip{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 13px;margin:10px 0 14px;border:1px solid var(--line);border-radius:13px;background:#0b1424}
.injuryDot{width:10px;height:10px;border-radius:50%;display:inline-block;background:#35d39a;box-shadow:0 0 10px #35d39a66}.injuryDot.warn{background:#e7bd56}.injuryDot.bad{background:#ef6376}
.injuryPill{border:1px solid var(--line);border-radius:999px;padding:5px 9px;font-size:11px}.injuryPill.out{color:#ef6376}.injuryPill.q{color:#e7bd56}.injuryPill.good{color:#35d39a}
.gameInjuries{display:grid;gap:8px;margin-top:10px}.injuryRow{display:flex;justify-content:space-between;gap:12px;padding:9px 10px;border:1px solid var(--line);border-radius:10px;background:#091221}.injuryStatus{font-weight:900}.injuryStatus.OUT,.injuryStatus.DOUBTFUL{color:#ef6376}.injuryStatus.QUESTIONABLE{color:#e7bd56}.injuryStatus.PROBABLE{color:#35d39a}
/* INJURY_UI_END */
'''

def main():
 if not HTML.exists():return
 html=HTML.read_text(encoding='utf-8');data={}
 try:data=json.load(DATA.open(encoding='utf-8'))
 except Exception:pass
 payload=json.dumps(data,separators=(',',':')).replace('</','<\\/')
 html=re.sub(r'<script>window\.WNBA_INJURY_DATA=.*?</script>','',html,flags=re.S)
 html=html.replace('</head>',f'<script>window.WNBA_INJURY_DATA={payload};</script></head>',1)
 html=re.sub(r'/\* INJURY_UI_START \*/.*?/\* INJURY_UI_END \*/','',html,flags=re.S)
 html=html.replace('</style>',CSS+'</style>',1)
 js=r'''
function injuryData(){return window.WNBA_INJURY_DATA||{}}
function injuryStrip(){const d=injuryData(),s=d.summary||{},age=Number(d.freshness_minutes||0),bad=Number(s.out_or_doubtful||0)>0,warn=Number(s.questionable||0)>0||age>90,cls=bad?'bad':warn?'warn':'';return `<div class="injuryStrip mono"><span class="injuryDot ${cls}"></span><b>Injuries</b><span class="injuryPill ${bad?'out':'good'}">${S(s.out_or_doubtful,0)} OUT/DOUBTFUL</span><span class="injuryPill ${warn?'q':'good'}">${S(s.questionable,0)} QUESTIONABLE</span><span class="small">${S(s.beneficiaries,0)} role boosts · updated ${age?age+'m ago':'now'}</span></div>`}
function injuriesForGame(g){const teams=[g.home_team||g.home,g.away_team||g.away].filter(Boolean),rows=A(injuryData().injuries).filter(x=>teams.includes(x.team));if(!rows.length)return '<div class="small mono">No listed injuries for this matchup.</div>';return `<div class="gameInjuries">${rows.map(x=>`<div class="injuryRow"><div><b class="mono">${E(x.player)}</b><div class="small mono">${E(x.team)} · ${E(x.detail||x.injury_type||'')}</div></div><div class="injuryStatus ${E(x.severity)} mono">${E(x.severity)}</div></div>`).join('')}</div>`}
'''
 if 'function injuryData()' not in html:
  html=html.replace('function decisionRows(){',js+'\nfunction decisionRows(){',1)
 # inject strip in games return and injury detail into simple card details
 html=html.replace("return `<div class=\"section\"><h2 class=\"mono\">Tonight</h2>","return injuryStrip()+`<div class=\"section\"><h2 class=\"mono\">Tonight</h2>",1)
 html=html.replace("${rows.map(detailPlay).join('')}</div></div></div>`","${rows.map(detailPlay).join('')}<div class=\"detailBox\"><div class=\"label mono\">Injury Report</div>${injuriesForGame(g)}</div></div></div></div>`",1)
 HTML.write_text(html,encoding='utf-8');print('Injury UI installed')
if __name__=='__main__':main()
