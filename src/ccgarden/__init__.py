import argparse
import subprocess
import webbrowser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ccgarden.claude_stats import DEFAULT_LOG_ROOT, parse_day, print_report
from ccgarden.data import DayRange, load_garden_data, load_garden_timeline
from ccgarden.render import render_svg, render_timeline_svg

DEFAULT_DB_PATH = Path.home() / '.claude' / 'ccstats.db'
DEFAULT_OUTPUT_PATH = Path.home() / '.claude' / 'ccgarden.svg'


def _version() -> str:
    try:
        return version('ccgarden')
    except PackageNotFoundError:  # running from a source tree, not installed
        return 'unknown'


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
        '--version',
        action='version',
        version=f'ccgarden {_version()}',
    )
    parser.add_argument(
        '--no-open',
        action='store_true',
        help='write the SVG without opening it in a browser',
    )
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f'where to write the SVG (default: {DEFAULT_OUTPUT_PATH})',
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f'stats database to render from (default: {DEFAULT_DB_PATH})',
    )
    parser.add_argument(
        '--log-root',
        type=Path,
        action='append',
        dest='log_roots',
        metavar='DIR',
        help=(
            'transcript root to record from; repeatable '
            f'(default: {DEFAULT_LOG_ROOT})'
        ),
    )
    parser.add_argument(
        '--static',
        action='store_true',
        help='render one still garden instead of the animated timelapse',
    )
    parser.add_argument(
        '--since', type=parse_day, metavar='YYYY-MM-DD', help='earliest day'
    )
    parser.add_argument(
        '--until', type=parse_day, metavar='YYYY-MM-DD', help='latest day'
    )
    parser.add_argument(
        '--no-record',
        action='store_true',
        help="render the db as-is, without recording today's snapshot first",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    log_roots = args.log_roots or [DEFAULT_LOG_ROOT]
    if not args.no_record:
        # print_report also records today's snapshot -- must run before the
        # timeline is loaded, or the garden it renders is one day stale.
        print_report(log_roots, db_path=args.db)

    days = DayRange(
        since=args.since.isoformat() if args.since else None,
        until=args.until.isoformat() if args.until else None,
    )
    if args.static:
        svg = render_svg(load_garden_data(str(args.db), days=days))
    else:
        svg = render_timeline_svg(
            load_garden_timeline(str(args.db), days=days)
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    if not args.no_open:
        _open_in_browser(args.output)
    print(f'wrote {args.output}')
