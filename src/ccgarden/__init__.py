import argparse
import subprocess
import webbrowser
from pathlib import Path

from ccgarden.claude_stats import DEFAULT_LOG_ROOT, print_report
from ccgarden.data import load_garden_timeline
from ccgarden.render import render_timeline_svg

DEFAULT_DB_PATH = Path.home() / '.claude' / 'ccstats.db'
DEFAULT_OUTPUT_PATH = Path.home() / '.claude' / 'ccgarden.svg'


def _is_wsl() -> bool:
    try:
        return 'microsoft' in Path('/proc/version').read_text().lower()
    except OSError:
        return False


def _open_in_browser(path: Path) -> None:
    if _is_wsl():
        windows_path = subprocess.run(  # noqa: S603
            ['wslpath', '-w', str(path)],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        # explorer.exe always exits 1 on success, so don't check the code.
        subprocess.run(  # noqa: S603
            ['explorer.exe', windows_path],  # noqa: S607
            check=False,
        )
    else:
        webbrowser.open(path.as_uri())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ccgarden',
        description='Grow a garden from local Claude Code session history.',
    )
    parser.add_argument(
        '--no-open',
        action='store_true',
        help='write the SVG without opening it in a browser',
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    # print_report also records today's snapshot -- must run before the
    # timeline is loaded, or the garden it renders is one day stale.
    print_report([DEFAULT_LOG_ROOT], db_path=DEFAULT_DB_PATH)
    timeline = load_garden_timeline(str(DEFAULT_DB_PATH))
    svg = render_timeline_svg(timeline)
    DEFAULT_OUTPUT_PATH.write_text(svg)
    if not args.no_open:
        _open_in_browser(DEFAULT_OUTPUT_PATH)
    print(f'wrote {DEFAULT_OUTPUT_PATH}')
