from __future__ import annotations

import json, re
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_s19_m04_decision_contract.json')
START = '<!-- SPRINT19_M04_CONTRACT_START -->'
END = '<!-- SPRINT19_M04_CONTRACT_END -->'


def main():
    if not HTML.exists() or not DATA.exists():
        raise SystemExit('Sprint 19 M04 inputs missing')
    data = json.loads(DATA.read_text(encoding='utf-8'))
    if data.get('status') != 'READY':
        raise SystemExit('Sprint 19 M04 decision contract not READY')
    raw = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    block = f'''\n{START}\n<script id="s19-m04-contract-script">\n(function(){{\n const D={raw};\n window.WNBA_S19_M04=D;\n window.WNBA_CANONICAL_DASHBOARD_CONTRACT=D;\n window.WNBA_CANONICAL_DASHBOARD_CONTRACT_VERSION=D.schema_version;\n}})();\n</script>\n{END}\n'''
    html = HTML.read_text(encoding='utf-8')
    html = re.sub(re.escape(START) + r'.*?' + re.escape(END), '', html, flags=re.S)
    if '</body>' not in html:
        raise SystemExit('Dashboard shell missing closing body')
    HTML.write_text(html.replace('</body>', block + '\n</body>', 1), encoding='utf-8')
    print({'status':'PASS','sprint':19,'module':'M04','target_date':data.get('target_date'),'schema_version':data.get('schema_version')})


if __name__ == '__main__':
    main()
