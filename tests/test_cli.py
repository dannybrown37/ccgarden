from typing import TYPE_CHECKING

import pytest

import ccgarden

if TYPE_CHECKING:
    from pathlib import Path


def _noop(*_args: object, **_kwargs: object) -> None:
    return None


@pytest.fixture
def opened_paths(monkeypatch, tmp_path):
    """Replace the heavy render pipeline and record browser opens."""
    opened: list[Path] = []
    monkeypatch.setattr(ccgarden, 'print_report', _noop)
    monkeypatch.setattr(ccgarden, 'load_garden_timeline', lambda _db: [])
    monkeypatch.setattr(ccgarden, 'render_timeline_svg', lambda _t: '<svg/>')
    monkeypatch.setattr(
        ccgarden, 'DEFAULT_OUTPUT_PATH', tmp_path / 'ccgarden.svg'
    )
    monkeypatch.setattr(ccgarden, '_open_in_browser', opened.append)
    return opened


@pytest.mark.parametrize(
    ('argv', 'expected_opens'),
    [
        ([], 1),
        (['--no-open'], 0),
    ],
)
def test_no_open_suppresses_the_browser(opened_paths, argv, expected_opens):
    ccgarden.main(argv)

    assert len(opened_paths) == expected_opens


@pytest.mark.usefixtures('opened_paths')
def test_svg_is_still_written_when_not_opening(tmp_path):
    ccgarden.main(['--no-open'])

    assert (tmp_path / 'ccgarden.svg').read_text() == '<svg/>'
