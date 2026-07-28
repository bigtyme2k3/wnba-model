from scrape_official_wnba_injuries import display_name, normalize_status


def run():
    assert display_name('Edwards, Aaliyah') == 'Aaliyah Edwards'
    assert display_name('Parker-Tyus, Cheyenne') == 'Cheyenne Parker-Tyus'
    assert normalize_status('Out') == 'OUT'
    assert normalize_status('Questionable') == 'QUESTIONABLE'
    assert normalize_status('Probable') == 'PROBABLE'
    print({'status': 'PASS', 'tests': 5})


if __name__ == '__main__':
    run()
