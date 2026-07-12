from __future__ import annotations

import json
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_alt_streaks.json")

CSS = r"""
<style id="v4-alt-streaks-style">
.altFilters{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.altFilter{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}.altFilter.a{border-color:#00e39b;color:#fff;background:#103127}.altTableWrap{overflow:auto;border:1px solid #1e2a43;border-radius:18px}.altTable{min-width:1080px}.altPlayer{font-weight:900}.altStat{font-weight:900;color:#00e39b}.altStreak{font-size:22px;font-weight:900;color:#00e39b}.altStrong{color:#00e39b;font-weight:900}.altMid{color:#ffd166;font-weight:900}.altWeak{color:#ff4d67;font-weight:900}.altBook{font-size:11px;color:#7e8ba3}.altPolicy{margin-top:10px;color:#7e8ba3;font-size:11px}.altEmpty{padding:36px;text-align:center;color:#7e8ba3}.altCount{margin-left:auto;color:#7e8ba3;font-size:12px;align-self:center}
</style>
"""

SCRIPT = r"""
<script id="v4-alt-streaks-script">
(function(){
  const esc=v=>typeof E==='function'?E(v):String(v??'');
  const arr=v=>Array.isArray(v)?v:[];
  const val=(v,d='-')=>v===undefined||v===null||v===''?d:v;
  let altStat='ALL', altOdds='ALL';
  window.setAltStat=function(v){altStat=v;render('alt')};
  window.setAltOdds=function(v){altOdds=v;render('alt')};
  function oddsBand(o){const n=Number(o);if(!Number.isFinite(n))return'NONE';if(n<=-500)return'-500+';if(n<=-300)return'-300';if(n<=-150)return'-150';return'OTHER'}
  function pctClass(p){p=Number(p||0);return p>=.8?'altStrong':p>=.6?'altMid':'altWeak'}
  function buttons(values,current,fn){return values.map(v=>`<button class="altFilter ${current===v?'a':''}" onclick="${fn}('${v}')">${esc(v)}</button>`).join('')}
  window.altStreaks=function(){
    const payload=DATA.alt_streaks||{}, all=arr(payload.rows);
    const stats=['ALL',...new Set(all.map(r=>r.stat).filter(Boolean))];
    const odds=['ALL','-150','-300','-500+'];
    let rows=all.filter(r=>(altStat==='ALL'||r.stat===altStat)&&(altOdds==='ALL'||oddsBand(r.best_odds)===altOdds));
    const body=rows.map(r=>`<tr><td><div class="altPlayer">${esc(r.player)}</div><div class="small mono">${esc(val(r.team))}</div></td><td class="altStat mono">${esc(r.stat)}</td><td class="mono"><b>${esc(r.side==='UNDER'?'U':'O')} ${esc(r.alt_line)}</b><div class="small mono">${esc(r.line_type)}</div></td><td><div class="altStreak mono">${esc(r.streak)}</div><div class="small mono">straight</div></td><td class="${pctClass(r.last10_pct)} mono">${esc(r.last10_hits)}/${esc(r.last10_games)}<div class="small">${Math.round(Number(r.last10_pct||0)*100)}%</div></td><td class="${pctClass(r.season_pct)} mono">${r.season_hits===null||r.season_hits===undefined?'—':`${esc(r.season_hits)}/${esc(r.season_games)}`}<div class="small">${r.season_pct===null||r.season_pct===undefined?'':Math.round(Number(r.season_pct)*100)+'%'}</div></td><td class="mono">${esc(val(r.average))}</td><td class="mono">${esc(val(r.opponent_rank))}<div class="small">${esc(val(r.opponent_label,''))}</div></td><td class="mono"><b>${esc(val(r.best_odds))}</b><div class="altBook">${esc(val(r.best_book))}</div></td></tr>`).join('');
    return `<div class="section"><div class="row"><div><h2 class="mono">ALT Streaks</h2><div class="small mono">Alternate and standard lines on active streaks of 3+ games.</div></div><div class="altCount mono">${rows.length} rows</div></div><div class="label mono">Stat Type</div><div class="altFilters">${buttons(stats,altStat,'setAltStat')}</div><div class="label mono">Odds Tier</div><div class="altFilters">${buttons(odds,altOdds,'setAltOdds')}</div><div class="altTableWrap"><table class="altTable"><thead><tr><th>Player</th><th>Stat</th><th>Line</th><th>Streak</th><th>L10</th><th>Season</th><th>Avg</th><th>Opp Rank</th><th>Best Odds</th></tr></thead><tbody>${body||`<tr><td colspan="9"><div class="altEmpty mono">No qualifying streak rows with verified history and supplied lines.</div></td></tr>`}</tbody></table></div><div class="altPolicy mono">${esc(val(payload.data_policy,'Real history and sportsbook lines only.'))}</div></div>`;
  };
  const oldRender=window.render;
  window.render=function(view){
    if(view==='alt'){
      document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('a',b.dataset.view==='alt'));
      const root=document.getElementById('root');if(root)root.innerHTML=window.altStreaks();return;
    }
    return oldRender(view);
  };
  function addTab(){
    const tabs=document.getElementById('tabs');if(!tabs||tabs.querySelector('[data-view="alt"]'))return;
    const button=document.createElement('button');button.className='tab';button.dataset.view='alt';button.textContent='ALT Streaks';button.onclick=()=>window.render('alt');
    const props=[...tabs.querySelectorAll('.tab')].find(x=>x.textContent.trim()==='Player Props');
    if(props&&props.nextSibling)tabs.insertBefore(button,props.nextSibling);else tabs.appendChild(button);
  }
  addTab();
})();
</script>
"""


def replace_block(html: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = html.find(start_marker)
    if start < 0:
        return html
    end = html.find(end_marker, start)
    if end < 0:
        return html
    return html[:start] + replacement.strip() + html[end + len(end_marker):]


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    payload = {}
    try:
        payload = json.load(DATA.open(encoding="utf-8")) if DATA.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding="utf-8")
    data_script = f'<script id="v4-alt-streaks-data">DATA.alt_streaks={json.dumps(payload, separators=(",", ":"), ensure_ascii=False)};</script>'
    if 'id="v4-alt-streaks-data"' in html:
        html = replace_block(html, '<script id="v4-alt-streaks-data">', '</script>', data_script)
    else:
        html = html.replace("</body>", data_script + "</body>")
    if 'id="v4-alt-streaks-style"' in html:
        html = replace_block(html, '<style id="v4-alt-streaks-style">', '</style>', CSS)
    else:
        html = html.replace("</head>", CSS + "</head>")
    if 'id="v4-alt-streaks-script"' in html:
        html = replace_block(html, '<script id="v4-alt-streaks-script">', '</script>', SCRIPT)
    else:
        html = html.replace("</body>", SCRIPT + "</body>")
    HTML.write_text(html, encoding="utf-8")
    print(f"ALT Streaks tab applied with {len(payload.get('rows', [])) if isinstance(payload, dict) else 0} rows")


if __name__ == "__main__":
    main()
