from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_ID = "v4-games-ux-style"
SCRIPT_ID = "v4-games-ux-script"

STYLE = r'''<style id="v4-games-ux-style">
.gamesUxControls{position:sticky;top:0;z-index:11;display:flex;gap:8px;overflow:auto;padding:10px 0;background:rgba(5,11,20,.96);backdrop-filter:blur(12px);border-bottom:1px solid #18253a}.gamesUxChip{white-space:nowrap;border:1px solid #2a3d5d;background:#0a1423;color:#b9c8df;border-radius:999px;padding:8px 12px;font-size:11px;font-weight:900;cursor:pointer}.gamesUxChip.active{border-color:var(--green);color:var(--green);background:rgba(0,227,155,.1)}.gamesUxMeta{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:11px;margin:7px 0 12px}.gamesUxWrap .grid2{grid-template-columns:minmax(0,1.7fr) minmax(280px,.8fr)}.gamesUxWrap .gameCard{border:1px solid #20304a;background:linear-gradient(180deg,#0a1423,#08101c);border-radius:16px;margin-top:12px;padding:14px}.gamesUxWrap .gameCard[data-decision="BET"]{border-color:rgba(0,227,155,.5);box-shadow:0 0 0 1px rgba(0,227,155,.08) inset}.gamesUxWrap .marketGrid{grid-template-columns:repeat(3,minmax(0,1fr))}.gamesUxWrap .marketBox{min-height:105px}.gamesUxWrap .candidateToggle summary{padding:8px 0}.gamesUxEmpty{display:none!important}
@media(max-width:1050px){.gamesUxWrap .grid2{grid-template-columns:1fr}.gamesUxWrap .grid2>.section:last-child{order:2}.gamesUxWrap .marketGrid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:760px){.gamesUxWrap .gamesSummary{grid-template-columns:1fr 1fr}.gamesUxWrap .marketGrid{grid-template-columns:1fr}.gamesUxWrap .marketBox{min-height:auto}.gamesUxWrap .gameSummaryLine{display:grid;grid-template-columns:1fr 1fr}.gamesUxWrap .freshness{overflow:auto;flex-wrap:nowrap}.gamesUxWrap .row{align-items:flex-start}.gamesUxMeta{flex-direction:column}.gamesUxWrap .candidateList{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="v4-games-ux-script">
(function(){
 const original=window.gamesV25;
 if(typeof original!=='function')return;
 const state=window.WNBA_GAMES_UX_STATE||{filter:'all'};
 window.WNBA_GAMES_UX_STATE=state;
 function classify(card){
   const text=(card.textContent||'').toUpperCase();
   let decision='PASS';
   if(text.includes('BET'))decision='BET'; else if(text.includes('LEAN'))decision='LEAN';
   card.dataset.decision=decision;
   card.dataset.largeEdge=/EDGE\s+[+-]?(?:[3-9]|\d{2,})(?:\.\d+)?/.test(text)?'1':'0';
   card.dataset.players=text.includes('PLAYER CANDIDATES')&&!text.includes('PLAYER CANDIDATES (0)')?'1':'0';
   card.dataset.recent=text.includes('FINAL')?'1':'0';
 }
 function matches(card){
   const f=state.filter;
   if(f==='all')return true;
   if(f==='bet')return card.dataset.decision==='BET';
   if(f==='lean')return card.dataset.decision==='LEAN';
   if(f==='pass')return card.dataset.decision==='PASS'&&card.dataset.recent!=='1';
   if(f==='edge')return card.dataset.largeEdge==='1';
   if(f==='players')return card.dataset.players==='1';
   return true;
 }
 function enhance(html){
   const box=document.createElement('div');box.innerHTML=html;
   const cards=[...box.querySelectorAll('.gameCard')];cards.forEach(classify);
   const visible=cards.filter(matches).length;
   cards.forEach(c=>{if(!matches(c))c.classList.add('gamesUxEmpty')});
   const chips=[['all','All Games'],['bet','Model Bets'],['lean','Leans'],['pass','Passes'],['edge','Large Edges'],['players','Player Props']].map(([k,l])=>`<button class="gamesUxChip ${state.filter===k?'active':''}" data-games-filter="${k}">${l}</button>`).join('');
   return `<div class="gamesUxWrap"><div class="gamesUxControls">${chips}</div><div class="gamesUxMeta mono"><span>Showing ${visible} of ${cards.length} game cards</span><span>Tap a matchup's Player candidates to expand</span></div>${box.innerHTML}</div>`;
 }
 window.gamesV25=function(){return enhance(original())};
 document.addEventListener('click',function(e){
   const b=e.target.closest('[data-games-filter]');if(!b)return;
   e.preventDefault();e.stopImmediatePropagation();state.filter=b.dataset.gamesFilter||'all';
   const root=document.getElementById('root');if(root)root.innerHTML=window.gamesV25();
   window.scrollTo({top:0,behavior:'instant'});
 },true);
 window.WNBA_GAMES_UX={version:'1.0',state};
})();
</script>'''


def replace_or_insert(html: str, tag: str, marker: str, block: str, before: str) -> str:
    start = html.find(f'<{tag} id="{marker}">')
    if start >= 0:
        end_tag = f'</{tag}>'
        end = html.find(end_tag, start)
        if end >= 0:
            return html[:start] + block + html[end + len(end_tag):]
    return html.replace(before, block + "\n" + before, 1)


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    html = replace_or_insert(html, "style", STYLE_ID, STYLE, "</head>")
    html = replace_or_insert(html, "script", SCRIPT_ID, SCRIPT, "</body>")
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Games tablet UX applied")


if __name__ == "__main__":
    main()
