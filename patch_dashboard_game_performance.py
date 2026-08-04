"""Inject a screenshot-verifiable Game Performance tab into docs/index.html."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_game_performance.json")
START = "<!-- WNBA_GAME_PERFORMANCE_START -->"
END = "<!-- WNBA_GAME_PERFORMANCE_END -->"


def pct(value):
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "—"


def record(payload):
    r = payload.get("record") or {}
    return f"{int(r.get('wins') or 0)}-{int(r.get('losses') or 0)}-{int(r.get('pushes') or 0)}"


def build(payload: dict) -> str:
    summary = payload.get("summary") or {}
    spread = payload.get("spread") or {}
    total = payload.get("total") or {}
    cards = []
    for row in (payload.get("recent_games") or [])[:20]:
        cards.append(f'''<article class="gp-card">
          <div class="gp-date">{escape(str(row.get('target_date') or ''))}</div>
          <h3>{escape(str(row.get('game') or 'Unknown game'))}</h3>
          <div class="gp-grid">
            <div><span>Spread pick</span><b>{escape(str(row.get('spread_recommendation') or row.get('spread_pick') or 'PASS'))}</b><em class="{str(row.get('spread_result') or '').lower()}">{escape(str(row.get('spread_result') or 'PENDING'))}</em></div>
            <div><span>Total pick</span><b>{escape(str(row.get('total_recommendation') or row.get('total_pick') or 'PASS'))}</b><em class="{str(row.get('total_result') or '').lower()}">{escape(str(row.get('total_result') or 'PENDING'))}</em></div>
            <div><span>Projected</span><b>{row.get('projected_away_score','—')}–{row.get('projected_home_score','—')}</b><small>Total {row.get('projected_total','—')}</small></div>
            <div><span>Actual</span><b>{row.get('actual_away_score','—')}–{row.get('actual_home_score','—')}</b><small>Total {row.get('actual_total','—')}</small></div>
          </div>
        </article>''')
    return f'''{START}
<style>
#game-performance-view{{display:none;padding:18px 24px 48px}}
#game-performance-view.active{{display:block}}
.gp-summary{{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:12px;margin:14px 0 20px}}
.gp-metric,.gp-card{{background:#091625;border:1px solid #1d334b;border-radius:16px;padding:16px}}
.gp-metric span,.gp-grid span{{display:block;color:#8ea1b6;font-size:12px;text-transform:uppercase;letter-spacing:.08em}}
.gp-metric b{{display:block;font-size:25px;margin-top:7px;color:#eef5ff}}
.gp-cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
.gp-card h3{{margin:4px 0 14px;color:#f1f5f9}}
.gp-date{{color:#20d89b;font-size:12px}}
.gp-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.gp-grid div{{background:#07111e;border:1px solid #162a40;border-radius:10px;padding:10px}}
.gp-grid b,.gp-grid small,.gp-grid em{{display:block;margin-top:5px}}
.gp-grid em.win{{color:#20d89b}} .gp-grid em.loss{{color:#ff667d}} .gp-grid em.pass{{color:#f4bf4f}}
@media(max-width:900px){{.gp-summary{{grid-template-columns:repeat(2,1fr)}}.gp-cards{{grid-template-columns:1fr}}.gp-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
<section id="game-performance-view" data-view="game-performance" aria-label="Game Performance">
  <h2>Game Performance</h2>
  <p>Frozen pregame spreads, totals and projected scores graded against final results.</p>
  <div class="gp-summary">
    <div class="gp-metric"><span>Archived games</span><b>{int(summary.get('archived_games') or 0)}</b></div>
    <div class="gp-metric"><span>Graded games</span><b>{int(summary.get('graded_games') or 0)}</b></div>
    <div class="gp-metric"><span>Spread record</span><b>{record(spread)}</b><small>{pct(spread.get('hit_rate'))}</small></div>
    <div class="gp-metric"><span>Total record</span><b>{record(total)}</b><small>{pct(total.get('hit_rate'))}</small></div>
    <div class="gp-metric"><span>Margin MAE</span><b>{summary.get('avg_margin_error','—')}</b></div>
    <div class="gp-metric"><span>Total MAE</span><b>{summary.get('avg_total_error','—')}</b></div>
  </div>
  <div class="gp-cards">{''.join(cards) or '<div class="gp-card">No graded game cards yet.</div>'}</div>
</section>
<script id="game-performance-nav-script">
(function(){{
 const view=document.getElementById('game-performance-view');
 if(!view)return;
 const hiddenNodes=new Set();
 function allTabs(){{return [...document.querySelectorAll('button,a,[role="tab"]')];}}
 function navHost(){{
   const games=allTabs().find(x=>x.textContent.trim()==='Games');
   return games?.parentElement || document.querySelector('nav') || document.querySelector('[role="tablist"]');
 }}
 function restoreDashboard(){{
   hiddenNodes.forEach(node=>{{
     if(!node.isConnected)return;
     node.style.display=node.dataset.gpPreviousDisplay||'';
     delete node.dataset.gpPreviousDisplay;
   }});
   hiddenNodes.clear();
   view.style.display='none';
   view.classList.remove('active');
   const btn=document.querySelector('[data-wv4-tab="game-performance"]');
   if(btn){{btn.classList.remove('active');btn.setAttribute('aria-selected','false');}}
 }}
 function contentPanels(){{
   const selectors='main > section, main > .view, section.view, section[data-view], main > div[data-view]';
   return [...document.querySelectorAll(selectors)].filter(node=>
     node!==view && !node.closest('nav,[role="tablist"]') && !node.matches('button,a,[role="tab"]')
   );
 }}
 function show(){{
   restoreDashboard();
   contentPanels().forEach(node=>{{
     const visible=getComputedStyle(node).display!=='none';
     if(!visible)return;
     node.dataset.gpPreviousDisplay=node.style.display||'';
     hiddenNodes.add(node);
     node.style.display='none';
   }});
   allTabs().forEach(tab=>{{tab.classList.remove('active');tab.setAttribute('aria-selected','false');}});
   const btn=document.querySelector('[data-wv4-tab="game-performance"]');
   if(btn){{btn.classList.add('active');btn.setAttribute('aria-selected','true');}}
   view.style.display='block';
   view.classList.add('active');
   window.scrollTo(0,0);
 }}
 function ensureButton(){{
   let btn=document.querySelector('[data-wv4-tab="game-performance"]');
   if(btn)return btn;
   const games=allTabs().find(x=>x.textContent.trim()==='Games');
   const template=games || allTabs().find(x=>x.textContent.trim()==='Game Props') || allTabs()[0];
   const host=navHost();
   if(!template||!host)return null;
   btn=template.cloneNode(true);
   btn.textContent='Game Performance';
   [...btn.attributes].forEach(attr=>{{if(attr.name.startsWith('data-'))btn.removeAttribute(attr.name);}});
   btn.setAttribute('data-wv4-tab','game-performance');
   btn.setAttribute('aria-label','Game Performance results');
   btn.setAttribute('aria-selected','false');
   btn.removeAttribute('id');
   btn.removeAttribute('onclick');
   btn.removeAttribute('data-view');
   btn.removeAttribute('data-tab');
   btn.removeAttribute('data-target');
   if(btn.tagName==='A')btn.setAttribute('href','#game-performance');
   if(games && games.nextSibling)host.insertBefore(btn,games.nextSibling); else host.appendChild(btn);
   btn.addEventListener('click',e=>{{e.preventDefault();e.stopPropagation();show();}});
   return btn;
 }}
 function wireOtherTabs(){{
   allTabs().forEach(tab=>{{
     if(tab.getAttribute('data-wv4-tab')==='game-performance'||tab.dataset.gpBound)return;
     tab.dataset.gpBound='1';
     tab.addEventListener('click',()=>restoreDashboard(),{{capture:true}});
   }});
 }}
 function install(){{ensureButton();wireOtherTabs();}}
 install();
 document.addEventListener('DOMContentLoaded',install,{{once:true}});
 const observer=new MutationObserver(()=>install());
 observer.observe(document.body,{{childList:true,subtree:true}});
 setTimeout(()=>observer.disconnect(),15000);
}})();
</script>
{END}'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    payload = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    html = HTML.read_text(encoding="utf-8")
    if START in html and END in html:
        html = html.split(START)[0] + html.split(END, 1)[1]
    html = html.replace("</body>", build(payload) + "\n</body>")
    HTML.write_text(html, encoding="utf-8")
    print("Game Performance dashboard and navigation-safe routing injected")


if __name__ == "__main__":
    main()
