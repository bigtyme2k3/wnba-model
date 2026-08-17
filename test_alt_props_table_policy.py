from pathlib import Path


SOURCE=Path('patch_dashboard_alt_props_table.py').read_text(encoding='utf-8')


def test_alt_rows_are_gated_by_target_date_not_game_label():
    assert "sourceTarget!==currentTarget" in SOURCE
    assert "gs.some(g=>g.game===r.game)" not in SOURCE
    assert "row_gate:'target-date-artifact'" in SOURCE
