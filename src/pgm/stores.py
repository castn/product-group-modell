"""Detects the retail chain from a store name (mapping/stores.yaml).

The table is also written into the model file (pgm.export); the app computes
with the same lookup (docs/interface.md, section Store).
"""

from functools import cache
from pathlib import Path

import yaml

from pgm.normalize import normalize

STORES = Path(__file__).resolve().parent.parent.parent / "mapping" / "stores.yaml"


@cache
def table() -> tuple[tuple[str, ...], tuple[tuple[str, int], ...]]:
    """Chains (sorted) and aliases (normalized, "-" as a space, longest first)."""
    stores = yaml.safe_load(STORES.read_text())["stores"]
    chains = tuple(sorted(stores))
    aliases = {
        (normalize(alias.replace("-", " ")), chains.index(chain))
        for chain, names in stores.items()
        for alias in names
    }
    return chains, tuple(sorted(aliases, key=lambda a: (-len(a[0]), a[0])))


def lookup(chains, aliases, name: str | None) -> str | None:
    """First alias that is a word of the name or that the name starts with."""
    if not name:
        return None
    text = normalize(name.replace("-", " "))
    words = set(text.split())
    for alias, index in aliases:
        if alias in words or text == alias or text.startswith(alias + " "):
            return chains[index]
    return None


def chain_of(name: str | None) -> str | None:
    """Chain for a store name like "REWE Markt GmbH" or "dm-drogerie markt"."""
    chains, aliases = table()
    return lookup(chains, aliases, name)
