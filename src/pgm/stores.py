"""Detects the retail chain from a store name (mapping/stores.yaml)."""

from functools import cache
from pathlib import Path

import yaml

from pgm.normalize import normalize

STORES = Path(__file__).resolve().parent.parent.parent / "mapping" / "stores.yaml"


@cache
def _aliases() -> list[tuple[str, str]]:
    stores = yaml.safe_load(STORES.read_text())["stores"]
    pairs = [
        (normalize(a), chain) for chain, aliases in stores.items() for a in aliases
    ]
    # longer aliases first, so that "ALDI SUED" is checked before "ALDI"
    return sorted(pairs, key=lambda p: -len(p[0]))


def chain_of(name: str | None) -> str | None:
    """Chain for a store name like "REWE Markt GmbH" or "dm-drogerie markt"."""
    if not name:
        return None
    text = normalize(name.replace("-", " "))
    words = set(text.split())
    for alias, chain in _aliases():
        alias = alias.replace("-", " ")
        if alias in words or text.startswith(alias + " ") or text == alias:
            return chain
    return None
