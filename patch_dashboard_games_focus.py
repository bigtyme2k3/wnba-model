from __future__ import annotations

import re
from pathlib import Path

HTML = Path("docs/index.html")

BLOCKS = [
    ("<!-- WNBA_TERMINAL_UI_PATCH_START -->", "<!-- WNBA_TERMINAL_UI_PATCH_END -->"),
    ("<!-- WNBA_ALT_GRADING_STATUS_START -->", "<!-- WNBA_ALT_GRADING_STATUS_END -->"),
    ("<!-- WNBA_ALT_PENDING_DIAGNOSTICS_START -->", "<!-- WNBA_ALT_PENDING_DIAGNOSTICS_END -->"),
    ("<!-- WNBA_ALT_RECOVERY_PROGRESS_START -->", "<!-- WNBA_ALT_RECOVERY_PROGRESS_END -->"),
    ("<!-- WNBA_BUILD_BEACON_START -->", "<!-- WNBA_BUILD_BEACON_END -->"),
]

SCRIPT_IDS = [
    "game-performance-nav-script",  # retained only when part of the Game Performance tab route
]


def remove_block(html: str, start: str, end: str) -> tuple[str, int]:
    pattern = re.escape(start) + r".*?" + re.escape(end)
    return re.subn(pattern, "", html, flags=re.S)


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")

    html = HTML.read_text(encoding="utf-8")
    removed: dict[str, int] = {}

    for start, end in BLOCKS:
        html, count = remove_block(html, start, end)
        removed[start] = count

    # Backward compatibility for an older terminal block that did not have an
    # end marker. Limit removal to the known section and its immediately
    # following script so the surrounding dashboard shell remains untouched.
    html, old_terminal = re.subn(
        r"<!-- WNBA_TERMINAL_UI_PATCH -->.*?</script>",
        "",
        html,
        count=1,
        flags=re.S,
    )
    removed["legacy_terminal"] = old_terminal

    # Remove any orphaned terminal section left by a malformed historical
    # patch. This is intentionally scoped to the terminal-ui element only.
    html, orphan_terminal = re.subn(
        r'<section id="terminal-ui">.*?</section>\s*<script>.*?</script>',
        "",
        html,
        count=1,
        flags=re.S,
    )
    removed["orphan_terminal"] = orphan_terminal

    if "</body>" not in html:
        raise SystemExit("Dashboard shell invalid after Games focus cleanup")

    marker = "<!-- WNBA_GAMES_FOCUS_CLEANUP -->"
    html = html.replace(marker, "")
    html = html.replace("</body>", marker + "\n</body>", 1)
    HTML.write_text(html, encoding="utf-8")
    print({"status": "PASS", "removed": removed, "games_focus": True})


if __name__ == "__main__":
    main()
