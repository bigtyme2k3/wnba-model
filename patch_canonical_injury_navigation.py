from pathlib import Path

SOURCE = Path('patch_dashboard_v4_consolidated_navigation.py')
HTML = Path('docs/index.html')

NAV_OLD = "['market','Market Intelligence'],['mission','Mission Control']"
NAV_NEW = "['market','Market Intelligence'],['injuries','Injuries'],['mission','Mission Control']"
ROUTE_OLD = "else if(view==='market')html=invoke('Market Intelligence',[window.marketIntelligence]);else if(view==='mission')"
ROUTE_NEW = "else if(view==='market')html=invoke('Market Intelligence',[window.marketIntelligence]);else if(view==='injuries')html=invoke('Injury Intelligence',[window.injuryIntelligence]);else if(view==='mission')"


def patch(path: Path) -> bool:
    text = path.read_text(encoding='utf-8')
    original = text
    if NAV_NEW not in text:
        if NAV_OLD not in text:
            raise RuntimeError(f'Canonical NAV anchor missing in {path}')
        text = text.replace(NAV_OLD, NAV_NEW)
    if ROUTE_NEW not in text:
        if ROUTE_OLD not in text:
            raise RuntimeError(f'Canonical route anchor missing in {path}')
        text = text.replace(ROUTE_OLD, ROUTE_NEW)
    text = text.replace("version:'2.4'", "version:'2.5'")
    if text != original:
        path.write_text(text, encoding='utf-8')
        return True
    return False


def main():
    changed = {'source': patch(SOURCE)}
    if HTML.exists():
        changed['html'] = patch(HTML)
    print(changed)


if __name__ == '__main__':
    main()
