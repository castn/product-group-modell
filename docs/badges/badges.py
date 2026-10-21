# /// script
# requires-python = ">=3.12"
# dependencies = ["anybadge>=1.14"]
# ///
"""Generates the badges for README.md as local SVG files.

Output:  docs/badges/*.svg (committed, referenced from README.md)

anybadge is declared inline above, so uv installs it in a temporary
environment for this script only; it is not a dependency of the project.
Change the values below (model size, status) and run the script again.

Usage:  uv run docs/badges/badges.py
"""

from pathlib import Path

import anybadge

OUT = Path(__file__).resolve().parent.parent / "docs" / "badges"

# file name → (label, value, color)
BADGES = {
    "license": ("license", "GPL-3.0-or-later", "#007ec6"),
    "python": ("python", "≥ 3.12", "#3776ab"),
    "kotlin": ("kotlin", "no dependencies", "#7f52ff"),
    "model": ("model", "< 2.0 MB", "#4c1"),
    "status": ("status", "pre-integration", "#fe7d37"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (label, value, color) in BADGES.items():
        path = OUT / f"{name}.svg"
        anybadge.Badge(label, value, default_color=color).write_badge(
            path, overwrite=True
        )
        print(path.relative_to(OUT.parent.parent))


if __name__ == "__main__":
    main()
