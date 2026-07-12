from __future__ import annotations

from pathlib import Path

PATH = Path("docs/index.html")

CSS = r"""
<style id="v4-qa-health-style">
.healthKpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}.healthKpi{background:#08101c;border:1px solid #1e2a43;border-radius:16px;padding:15px}.healthKpi .v{font-size:27px;font-weight:900;margin-top:6px}.qa-green{color:#00e39b}.qa-yellow{color:#ffd166}.qa-red{color:#ff4d67}.qa-unknown{color:#80a8ff}.qaPill{display:inline-flex;border:1px solid currentColor;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:900;text-transform:uppercase}.readyYes{color:#00e39b}.readyNo{color:#7e8ba3}.healthTableWrap{overflow:auto;border:1px solid #1e2a43;border-radius:16px;margin-top:14px}.healthTable{min-width:1050px}.issueList{margin:4px 0;padding-left:17px;color:#ff7f91}.warnList{margin:4px 0;padding-left:17px;color:#ffe09a}.qaMeta{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.qaSummary{background:#07101d;border:1px solid #1e2a43;border-radius:14px;padding:12px;margin-top:12px}.qaSummary code{white-space:pre-wrap;color:#a9b9d8}.healthEmpty{color:#7e8ba3;padding:14px 0}.issueNone{color:#6f7d94;font-size:12px}.issueCell{min-width:280px;max-width:420px}.issueGroup+.issueGroup{margin-top:6px}.issueLabel{font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:2px}@media(max-width:900px){.healthKpis{grid-template-columns:1fr 1fr}.healthKpi:last-child{grid-column:1/-1}}
</style>
"""

SCRIPT = r"""
<script id="v4-qa-health-script">
(function(){
  const esc=v=>typeof E==='function'?E(v):String(v??'');
  const arr=v=>Array.isArray(v)?v:[];
  const val=(v,d='-')=>v===undefined||v===null||v===''?d:v;
  const cls=g=>['green','yellow','red'].includes(String(g))?'qa-'+g:'qa-unknown';
  const pill=g=>`<span class="qaPill ${cls(g)}">${esc(val(g,'unknown'))}</span>`;
  const list=(items,kind)=>`<div class="issueGroup"><div class="issueLabel ${kind==='block'?'qa-red':'qa-yellow'}">${kind==='block'?'Blockers':'Warnings'}</div><ul class="${kind==='block'?'issueList':'warnList'}">${arr(items).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;
  const issues=(blockers,warnings)=>{
    const b=arr(blockers), w=arr(warnings);
    if(!b.length&&!w.length)return '<span class="issueNone mono">None</span>';
    return `${b.length?list(b,'block'):''}${w.length?list(w,'warn'):''}`;
  };
  window.health=function(){
    const v=DATA.v4||{}, s=v.summary||{}, qa=v.qa||{}, mods=arr(v.modules);
    const qac=s.qa_status_counts||{};
    const overall=qa.overall_status||'unknown';
    const output=qa.output_summary||{};
    const cards=`<div class="healthKpis">
      <div class="healthKpi"><div class="label mono">Overall QA</div><div class="v mono ${cls(overall)}">${esc(String(overall).toUpperCase())}</div></div>
      <div class="healthKpi"><div class="label mono">Production Ready</div><div class="v mono qa-green">${esc(val(s.production_ready,0))}/${esc(val(s.modules,0))}</div></div>
      <div class="healthKpi"><div class="label mono">Green / Yellow / Red</div><div class="v mono"><span class="qa-green">${esc(val(qac.green,0))}</span> / <span class="qa-yellow">${esc(val(qac.yellow,0))}</span> / <span class="qa-red">${esc(val(qac.red,0))}</span></div></div>
      <div class="healthKpi"><div class="label mono">Release Blockers</div><div class="v mono ${Number(s.release_blockers||0)?'qa-red':'qa-green'}">${esc(val(s.release_blockers,0))}</div></div>
      <div class="healthKpi"><div class="label mono">QA Completion</div><div class="v mono qa-green">${esc(val(s.completion_pct,0))}%</div></div>
    </div>`;
    const meta=`<div class="qaMeta"><span class="chip mono">Repository QA ${esc(val(qa.repository_qa_status,'unknown'))}</span><span class="chip mono">Output QA ${esc(val(qa.output_qa_status,'unknown'))}</span><span class="chip mono">Evaluated ${esc(val(output.evaluated_rows,output.decision_rows||0))}</span><span class="chip mono">Qualified ${esc(val(output.qualified_bets,0))}</span><span class="chip mono">Portfolio ${esc(val(output.portfolio_bets,0))}</span></div>`;
    const rows=mods.map(m=>`<tr>
      <td>${esc(m.id)}</td><td><b>${esc(m.name)}</b><div class="small mono">${esc(m.owner_file)}</div></td>
      <td>${esc(m.status)}</td><td>${esc(m.runtime_status)}</td><td>${pill(m.qa_grade)}</td><td class="mono">${esc(val(m.qa_score,0))}</td>
      <td class="${m.production_ready?'readyYes':'readyNo'} mono">${m.production_ready?'YES':'NO'}</td><td>${esc(m.effective_status)}</td><td class="mono">${esc(val(m.rows,0))}</td>
      <td class="issueCell">${issues(m.blockers,m.warnings)}</td>
    </tr>`).join('');
    const table=`<div class="healthTableWrap"><table class="healthTable"><thead><tr><th>ID</th><th>Module</th><th>Declared</th><th>Runtime</th><th>QA</th><th>Score</th><th>Ready</th><th>Effective</th><th>Rows</th><th>Issues</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    const blockers=arr(v.release_blockers);
    const blockerHtml=blockers.length?blockers.map(b=>`<div class="gameCard"><b class="mono qa-red">${esc(b.id)} · ${esc(b.module)}</b>${list(b.items,'block')}</div>`).join(''):'<div class="healthEmpty mono">No release blockers detected.</div>';
    return kpis()+cards+`<div class="section"><h2 class="mono">V4 QA Command Center</h2><div class="small mono">${esc(v.mission||'')}</div>${meta}<div class="qaSummary"><div class="label mono">Last QA generation</div><code class="mono">Repository: ${esc(val(qa.repository_qa_generated_at))}\nOutput: ${esc(val(qa.output_qa_generated_at))}</code></div>${table}</div><div class="section"><h2 class="mono">Release Blockers</h2>${blockerHtml}</div>`;
  };
})();
</script>
"""


def main() -> None:
    if not PATH.exists():
        raise SystemExit("docs/index.html does not exist")
    html = PATH.read_text(encoding="utf-8")
    start = html.find('<style id="v4-qa-health-style">')
    if start >= 0:
        end = html.find('</style>', start)
        if end >= 0:
            html = html[:start] + CSS.strip() + html[end + len('</style>'):]
    else:
        html = html.replace("</head>", CSS + "</head>")
    start = html.find('<script id="v4-qa-health-script">')
    if start >= 0:
        end = html.find('</script>', start)
        if end >= 0:
            html = html[:start] + SCRIPT.strip() + html[end + len('</script>'):]
    else:
        html = html.replace("</body>", SCRIPT + "</body>")
    PATH.write_text(html, encoding="utf-8")
    print("Dashboard V4 QA health integration applied")


if __name__ == "__main__":
    main()
