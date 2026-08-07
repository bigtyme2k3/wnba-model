from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path("docs/index.html")
DASH = Path("data/dashboard")
MARKER = "canonical-daily-runtime-v1"


def load(name: str, default):
    path = DASH / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")

    manifest = load("wnba_daily_canonical_manifest.json", {})
    master = load("wnba_master.json", {})
    props = load("wnba_player_props.json", {})
    target = str(
        manifest.get("target_date")
        or master.get("target_date")
        or props.get("target_date")
        or ""
    )
    games = master.get("today_games") or []
    rows = props.get("rows") or []

    if not target:
        raise SystemExit("Canonical target date missing")
    if manifest.get("status") != "PASS":
        raise SystemExit(f"Canonical manifest not PASS: {manifest.get('failures')}")
    if props.get("target_date") != target:
        raise SystemExit("Canonical player props date mismatch")

    active_games = {str(game.get("game") or "") for game in games}
    bad_rows = [row for row in rows if str(row.get("game") or "") not in active_games]
    if bad_rows:
        raise SystemExit(f"Canonical props contain {len(bad_rows)} off-slate rows")

    payload = json.dumps(
        {
            "target_date": target,
            "generated_at_utc": manifest.get("generated_at_utc"),
            "games": games,
            "props": rows,
            "game_count": len(games),
            "prop_count": len(rows),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    block = f'''\n<!-- {MARKER} -->
<style id="canonical-daily-runtime-style">
.canon-panel{{border:1px solid #26334f;border-radius:18px;background:#0b1220;padding:16px;color:#e5e7eb}}
.canon-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.canon-card{{border:1px solid #26334f;border-radius:14px;padding:13px;background:#0b1020}}
.canon-table{{width:100%;border-collapse:collapse}}.canon-table th,.canon-table td{{padding:11px;border-bottom:1px solid #26334f;text-align:left}}
.canon-muted{{color:#94a3b8;font-size:12px}}.canon-good{{color:#34d399}}.canon-empty{{padding:28px;text-align:center;color:#94a3b8}}
@media(max-width:800px){{.canon-grid{{grid-template-columns:1fr}}}}
</style>
<script id="canonical-daily-runtime-script">
(function(){{
 const C={payload}; window.WNBA_CANONICAL_DAILY=C;
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const leaves=()=>[...document.querySelectorAll('h1,h2,h3,h4,div,span,p,b')].filter(e=>e.children.length===0);
 const exact=t=>leaves().find(e=>e.textContent.trim()===t);
 const countText=(node,text)=>(node.textContent.match(new RegExp(text,'g'))||[]).length;
 function updateDate(){{
   const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
   let n; while(n=walker.nextNode()){{
     if(/Slate\s+\d{{4}}-\d{{2}}-\d{{2}}/.test(n.nodeValue)) n.nodeValue=n.nodeValue.replace(/Slate\s+\d{{4}}-\d{{2}}-\d{{2}}/,'Slate '+C.target_date);
     if(/Updated\s+\d{{1,2}}\/\d{{1,2}}\/\d{{4}}[^\n]*/.test(n.nodeValue)) n.nodeValue='Updated '+C.target_date;
   }}
   const badge=leaves().find(e=>/\d+\s+odds markets/i.test(e.textContent||''));
   if(badge) badge.textContent=C.prop_count+' canonical prop markets';
 }}
 function gamesHtml(){{return `<div class="canon-panel" data-canonical-panel="games"><h2>Today's Games</h2><div class="canon-muted">Canonical slate ${{esc(C.target_date)}} · ${{C.game_count}} games</div><div class="canon-grid" style="margin-top:12px">${{C.games.map(g=>`<div class="canon-card"><b>${{esc(g.game)}}</b><div class="canon-muted">${{esc(g.start_time)}} · ${{esc(g.status)}}</div><div style="margin-top:8px">Spread ${{esc(g.spread)}} · Total ${{esc(g.total)}}</div></div>`).join('')||'<div class="canon-card">No games scheduled.</div>'}}</div></div>`}}
 function matchupHtml(){{return `<div class="canon-panel" data-canonical-panel="matchups"><h2>Matchups</h2><div class="canon-muted">Current slate only · ${{esc(C.target_date)}}</div><div class="canon-grid" style="margin-top:12px">${{C.games.map(g=>`<div class="canon-card"><div class="canon-muted">MATCHUP</div><b>${{esc(g.game)}}</b><div style="margin-top:8px">Spread ${{esc(g.spread)}} · Total ${{esc(g.total)}}</div><div class="canon-muted">Model analysis pending current-slate feature generation.</div></div>`).join('')}}</div></div>`}}
 function propsHtml(){{return `<div class="canon-panel" data-canonical-panel="props"><h2>Player Props</h2><div class="canon-muted">Canonical Odds API rows · ${{C.prop_count}} props · ${{esc(C.target_date)}}</div><div style="overflow:auto;margin-top:12px"><table class="canon-table"><thead><tr><th>Player</th><th>Game</th><th>Stat</th><th>Line</th><th>Best Over</th><th>Best Under</th><th>History</th></tr></thead><tbody>${{C.props.slice(0,500).map(r=>`<tr><td><b>${{esc(r.player)}}</b><div class="canon-muted">${{esc(r.team)}}</div></td><td>${{esc(r.game)}}</td><td class="canon-good">${{esc(r.stat)}}</td><td>${{esc(r.line)}}</td><td>${{esc(r.best_over_book)}} ${{esc(r.best_over_price)}}</td><td>${{esc(r.best_under_book)}} ${{esc(r.best_under_price)}}</td><td>—</td></tr>`).join('')}}</tbody></table></div></div>`}}
 function booksHtml(){{return `<div class="canon-panel" data-canonical-panel="sportsbooks"><h2>Best Available Lines</h2><div class="canon-muted">Canonical current-slate sportsbook comparison · ${{C.prop_count}} rows</div><div style="overflow:auto;margin-top:12px"><table class="canon-table"><thead><tr><th>Player</th><th>Stat</th><th>Line</th><th>Best Over</th><th>Best Under</th><th>Game</th></tr></thead><tbody>${{C.props.slice(0,500).map(r=>`<tr><td>${{esc(r.player)}}</td><td class="canon-good">${{esc(r.stat)}}</td><td>${{esc(r.line)}}</td><td>${{esc(r.best_over_book)}} ${{esc(r.best_over_price)}}</td><td>${{esc(r.best_under_book)}} ${{esc(r.best_under_price)}}</td><td>${{esc(r.game)}}</td></tr>`).join('')}}</tbody></table></div></div>`}}
 function emptyHtml(title,message,key){{return `<div class="canon-panel" data-canonical-panel="${{key}}"><h2>${{esc(title)}}</h2><div class="canon-empty">${{esc(message)}}<br><span class="canon-muted">Canonical slate ${{esc(C.target_date)}}</span></div></div>`}}
 function replacePanel(title,html,requiredWords){{
   const h=exact(title); if(!h) return false; let p=h;
   for(let i=0;i<8&&p;i++,p=p.parentElement){{const txt=p.textContent||'';if(requiredWords.every(w=>txt.includes(w))){{if(!p.querySelector('[data-canonical-panel]'))p.innerHTML=html;return true}}}}
   return false;
 }}
 function replaceRepeatedLabel(label,html,minCount){{
   const nodes=leaves().filter(e=>e.textContent.trim()===label); if(nodes.length<minCount)return false;
   let p=nodes[0];
   for(let i=0;i<9&&p;i++,p=p.parentElement){{if(countText(p,label)>=minCount){{if(!p.querySelector('[data-canonical-panel]'))p.innerHTML=html;return true}}}}
   return false;
 }}
 function setMetric(label,value){{
   const node=exact(label); if(!node)return; const box=node.parentElement; if(!box)return;
   const candidates=[...box.querySelectorAll('div,span')].filter(e=>e.children.length===0&&e!==node);
   const target=candidates.find(e=>/Loaded|^\d+$|^\$?\d/.test(e.textContent.trim())); if(target)target.textContent=value;
 }}
 function cleanTerminal(){{
   const final=document.getElementById('terminalFinalSection');
   if(final&&!final.dataset.canonicalClean){{final.dataset.canonicalClean='1';final.innerHTML='<div class="term-section-title">Final Decisions</div><div class="term-row term-empty">No current-slate qualified decisions have been generated yet.</div>'}}
   const card=document.getElementById('terminalCardSection');
   if(card&&!card.dataset.canonicalClean){{card.dataset.canonicalClean='1';card.innerHTML='<div class="term-section-title">Top Betting Card</div><div class="term-row term-empty">No canonical betting card is available yet.</div>'}}
 }}
 function apply(){{
   updateDate();
   replacePanel("Today's Games",gamesHtml(),['Yesterday Results']);
   replacePanel('Player Props',propsHtml(),['All Games','Showing']);
   replacePanel('Best Available Lines',booksHtml(),['ODDS','PROPS']);
   replacePanel('AI Coach',emptyHtml('AI Center','No current-slate AI recommendations are available until projections are regenerated.','ai-center'),['MONTE CARLO','PROJECTION AI']);
   replaceRepeatedLabel('MATCHUP',matchupHtml(),3);
   replaceRepeatedLabel('BET',emptyHtml('Best Bets','No current-slate bets have passed the model guardrails.','best-bets'),2);
   cleanTerminal();
   setMetric('PROPS',String(C.prop_count)); setMetric('BEST BETS','0'); setMetric('ODDS',String(C.prop_count));
   document.querySelectorAll('*').forEach(e=>{{if(e.children.length===0&&/(?:NaN|null%)/.test(e.textContent||''))e.textContent='—'}});
 }}
 apply(); setTimeout(apply,500); setTimeout(apply,1800);
 new MutationObserver(()=>{{clearTimeout(window.__canonTimer);window.__canonTimer=setTimeout(apply,100)}}).observe(document.body,{{childList:true,subtree:true}});
}})();
</script>\n'''

    html = HTML.read_text(encoding="utf-8")
    html = re.sub(
        r'\n?<!-- canonical-daily-runtime-v1 -->\s*'
        r'<style id="canonical-daily-runtime-style">.*?</style>\s*'
        r'<script id="canonical-daily-runtime-script">.*?</script>\s*',
        "\n",
        html,
        flags=re.S,
    )
    if "</body>" not in html:
        raise SystemExit("Dashboard shell invalid: closing body tag missing")
    html = html.replace("</body>", block + "\n</body>", 1)
    HTML.write_text(html, encoding="utf-8")
    print(
        {
            "target_date": target,
            "games": len(games),
            "props": len(rows),
            "marker": MARKER,
            "tabs": ["games", "matchups", "player_props", "sportsbooks", "best_bets", "ai_center", "terminal"],
        }
    )


if __name__ == "__main__":
    main()
