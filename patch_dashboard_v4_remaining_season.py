from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_remaining_season_intelligence.json')
CSS=r'''<style id="v4-remaining-season-style">.rsGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.rsCard{border:1px solid #22334f;border-radius:12px;padding:11px;background:#08101c}.rsRow{display:grid;grid-template-columns:50px 1fr repeat(5,minmax(70px,.7fr));gap:8px;padding:8px 4px;border-bottom:1px solid #17233a;align-items:center;font-size:12px}.rsHard{color:#ff8b9d}.rsEasy{color:#49e3a5}@media(max-width:700px){.rsRow{grid-template-columns:42px 1fr 70px 70px}.rsHide{display:none}}</style>'''
SCRIPT=r'''<script id="v4-remaining-season-script">(function(){const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));window.remainingSeasonView=function(){const d=(window.DATA&&DATA.remaining_season)||{},s=d.summary||{},t=d.teams||[],g=d.games||[];const rows=t.map(x=>`<div class="rsRow"><b>#${e(x.difficulty_rank)}</b><b>${e(x.team)}</b><span>${e(x.remaining_games)} games</span><span>${e(x.schedule_difficulty)} diff</span><span class="rsHide">${e(x.back_to_backs)} B2B</span><span class="rsHide">${e(x.three_in_four)} 3-in-4</span><span class="rsHide">${e(x.travel_miles)} mi</span></div>`).join('');return `<div class="section"><h2 class="mono">Remaining Season Intelligence</h2><div class="rsGrid"><div class="rsCard"><div class="small">Remaining games</div><b>${e(s.remaining_games||0)}</b></div><div class="rsCard"><div class="small">Teams tracked</div><b>${e(s.teams||0)}</b></div><div class="rsCard"><div class="small">First game</div><b>${e((s.first_game_utc||'').slice(0,10)||'—')}</b></div><div class="rsCard"><div class="small">Last game</div><b>${e((s.last_game_utc||'').slice(0,10)||'—')}</b></div></div></div><div class="section"><h3 class="mono">Schedule Difficulty</h3>${rows||'<div class="empty mono">Schedule data not loaded.</div>'}</div><div class="section"><h3 class="mono">Next Games</h3>${g.slice(0,20).map(x=>`<div class="prodGate"><span>${e(x.away)} @ ${e(x.home)}</span><b>${e((x.date_utc||'').replace('T',' ').slice(0,16))} UTC</b></div>`).join('')}</div></div>`};})();</script>'''
def rep(h,s,e,r):
 i=h.find(s)
 if i<0:return h
 j=h.find(e,i)
 if j<0:return h
 return h[:i]+r.strip()+h[j+len(e):]
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 try:d=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
 except Exception:d={}
 h=HTML.read_text(encoding='utf-8');blob='<script id="v4-remaining-season-data">window.DATA=window.DATA||{};DATA.remaining_season='+json.dumps(d,separators=(',',':'))+';</script>'
 h=rep(h,'<script id="v4-remaining-season-data">','</script>',blob) if 'id="v4-remaining-season-data"' in h else h.replace('</body>',blob+'</body>')
 h=rep(h,'<style id="v4-remaining-season-style">','</style>',CSS) if 'id="v4-remaining-season-style"' in h else h.replace('</head>',CSS+'</head>')
 h=rep(h,'<script id="v4-remaining-season-script">','</script>',SCRIPT) if 'id="v4-remaining-season-script"' in h else h.replace('</body>',SCRIPT+'</body>')
 h=h.replace("['production','Production']","['remaining','Remaining Season'],['production','Production']") if "['remaining','Remaining Season']" not in h else h
 h=h.replace("else if(view==='production')root.innerHTML=safe(window.productionReadiness)","else if(view==='remaining')root.innerHTML=safe(window.remainingSeasonView);else if(view==='production')root.innerHTML=safe(window.productionReadiness)") if "view==='remaining'" not in h else h
 HTML.write_text(h,encoding='utf-8');print('Remaining Season Intelligence tab embedded')
if __name__=='__main__':main()
