import webbrowser
from pathlib import Path

from ccgarden.data import load_garden_data
from ccgarden.render import render_svg

DEFAULT_DB_PATH = Path.home() / '.claude' / 'ccstats.db'
DEFAULT_OUTPUT_PATH = Path.home() / '.claude' / 'ccgarden.svg'


def main() -> None:
    garden = load_garden_data(str(DEFAULT_DB_PATH))
    svg = render_svg(garden)
    DEFAULT_OUTPUT_PATH.write_text(svg)
    webbrowser.open(DEFAULT_OUTPUT_PATH.as_uri())
    print(f'wrote {DEFAULT_OUTPUT_PATH}')
