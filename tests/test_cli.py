import pytest

import ccgarden


def _noop(*_args: object, **_kwargs: object) -> None:
    return None


@pytest.fixture
def calls(monkeypatch, tmp_path):
    """Replace the heavy render pipeline and record what it was asked for."""
    recorded: dict[str, object] = {'opened': [], 'reports': []}

    def _report(roots, **kwargs) -> None:
        recorded['reports'].append((roots, kwargs))

    def _timeline(db_path, **kwargs) -> list:
        recorded['timeline_db'] = db_path
        recorded['days'] = kwargs.get('days')
        return []

    def _static(db_path, **kwargs) -> list:
        recorded['static_db'] = db_path
        recorded['days'] = kwargs.get('days')
        return []

    monkeypatch.setattr(ccgarden, 'print_report', _report)
    monkeypatch.setattr(ccgarden, 'load_garden_timeline', _timeline)
    monkeypatch.setattr(ccgarden, 'load_garden_data', _static)
    monkeypatch.setattr(ccgarden, 'render_timeline_svg', lambda _t: '<svg/>')
    monkeypatch.setattr(ccgarden, 'render_svg', lambda _g: '<static/>')
    monkeypatch.setattr(
        ccgarden, 'DEFAULT_OUTPUT_PATH', tmp_path / 'ccgarden.svg'
    )
    monkeypatch.setattr(
        ccgarden, '_open_in_browser', recorded['opened'].append
    )
    return recorded


@pytest.mark.parametrize(
    ('argv', 'expected_opens'),
    [
        ([], 1),
        (['--no-open'], 0),
    ],
)
def test_no_open_suppresses_the_browser(calls, argv, expected_opens):
    ccgarden.main(argv)

    assert len(calls['opened']) == expected_opens


def test_svg_is_still_written_when_not_opening(calls, tmp_path):
    del calls
    ccgarden.main(['--no-open'])

    assert (tmp_path / 'ccgarden.svg').read_text() == '<svg/>'


def test_output_flag_redirects_the_svg(calls, tmp_path):
    del calls
    target = tmp_path / 'nested' / 'garden.svg'

    ccgarden.main(['--no-open', '--output', str(target)])

    assert target.read_text() == '<svg/>'


def test_static_flag_renders_the_still_garden(calls, tmp_path):
    target = tmp_path / 'still.svg'

    ccgarden.main(['--no-open', '--static', '--output', str(target)])

    assert target.read_text() == '<static/>'
    assert 'static_db' in calls


def test_db_flag_selects_the_database(calls, tmp_path):
    ccgarden.main(['--no-open', '--db', str(tmp_path / 'other.db')])

    assert calls['timeline_db'] == str(tmp_path / 'other.db')


def test_since_and_until_become_a_day_range(calls):
    ccgarden.main(
        ['--no-open', '--since', '2026-01-01', '--until', '2026-02-01']
    )

    assert calls['days'] == ccgarden.DayRange(
        since='2026-01-01', until='2026-02-01'
    )


def test_days_default_to_the_whole_history(calls):
    ccgarden.main(['--no-open'])

    assert calls['days'] == ccgarden.DayRange(since=None, until=None)


def test_no_record_skips_the_snapshot(calls):
    ccgarden.main(['--no-open', '--no-record'])

    assert calls['reports'] == []


def test_recording_is_the_default(calls):
    ccgarden.main(['--no-open'])

    assert len(calls['reports']) == 1


def test_log_root_is_repeatable(calls, tmp_path):
    ccgarden.main(
        [
            '--no-open',
            '--log-root',
            str(tmp_path / 'a'),
            '--log-root',
            str(tmp_path / 'b'),
        ]
    )

    roots, _kwargs = calls['reports'][0]
    assert roots == [tmp_path / 'a', tmp_path / 'b']


def test_version_flag_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exit_info:
        ccgarden.main(['--version'])

    assert exit_info.value.code == 0
    assert 'ccgarden' in capsys.readouterr().out
