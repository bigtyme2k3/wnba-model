from __future__ import annotations

import re
import patch_dashboard_v4_ui_freeze as freeze
import patch_dashboard_v5_current_data_health as current_health


def safe_replace_element(html: str, tag: str, element_id: str, replacement: str) -> str:
    pattern = rf'<{tag} id="{re.escape(element_id)}">.*?</{tag}>'
    html, count = re.subn(pattern, lambda _match: replacement, html, count=1, flags=re.S)
    if count:
        return html
    anchor = '</head>' if tag == 'style' else '</body>'
    return html.replace(anchor, replacement + '\n' + anchor, 1)


freeze.replace_element = safe_replace_element
freeze.main()
# Install the canonical current-data health renderer after the Data Health router exists.
current_health.main()
