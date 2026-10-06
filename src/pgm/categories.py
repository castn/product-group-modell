"""Assigns an item group to products based on their categories.

Rules and mapping: mapping/off_to_group.yaml.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
MAPPING = ROOT / "mapping"

DROP = "_drop"
DEFAULT = "_default"
WEAK = "~"


def model_groups() -> list[str]:
    """Target labels of the model, in the order of groups.yaml."""
    groups = yaml.safe_load((MAPPING / "groups.yaml").read_text())["groups"]
    return [g["id"] for g in groups if g["model"]]


@dataclass(frozen=True)
class Resolution:
    group: str | None
    # "mapped", "default", "unmapped", "conflict" or "drop"
    reason: str
    # the decisive categories (on conflict, all involved)
    tags: tuple[str, ...] = ()


class Taxonomy:
    def __init__(self, path: Path):
        self._parents = {
            tag: tuple(entry.get("parents", []))
            for tag, entry in json.loads(path.read_text()).items()
        }
        self.ancestors = cache(self._ancestors)

    def _ancestors(self, tag: str) -> frozenset[str]:
        result: set[str] = set()
        for parent in self._parents.get(tag, ()):
            result.add(parent)
            result |= self.ancestors(parent)
        return frozenset(result)


class CategoryMapper:
    def __init__(
        self,
        mapping: dict[str, str | None],
        taxonomy: Taxonomy,
        groups: list[str] | None = None,
    ):
        valid = set(groups if groups is not None else model_groups()) | {DROP}
        unknown = {
            g for g in mapping.values() if g is not None and g.lstrip(WEAK) not in valid
        }
        if unknown:
            raise ValueError(f"unknown groups in the mapping: {sorted(unknown)}")
        self.default = mapping.get(DEFAULT)
        entries = {t: g for t, g in mapping.items() if t != DEFAULT}
        # group without "~"; weak mappings only count when no strong one is present
        self.mapping = {t: g.lstrip(WEAK) if g else g for t, g in entries.items()}
        self.weak = {t for t, g in entries.items() if g and g.startswith(WEAK)}
        self.taxonomy = taxonomy

    def resolve(self, tags: list[str]) -> Resolution:
        expanded = set(tags)
        for tag in tags:
            expanded |= self.taxonomy.ancestors(tag)
        if any(self.mapping.get(t) == DROP for t in expanded):
            return Resolution(None, "drop")
        mapped = {t: self.mapping[t] for t in expanded if self.mapping.get(t)}
        if not mapped:
            if self.default:
                return Resolution(self.default, "default")
            return Resolution(None, "unmapped")
        # most specific: no other mapped category lies below it
        below = set()
        for tag in mapped:
            below |= self.taxonomy.ancestors(tag)
        leaves = sorted(t for t in mapped if t not in below)
        strong = [t for t in leaves if t not in self.weak]
        if strong:
            leaves = strong
        groups = {mapped[t] for t in leaves}
        if len(groups) == 1:
            return Resolution(groups.pop(), "mapped", tuple(leaves))
        return Resolution(None, "conflict", tuple(leaves))


def load_mappers(
    raw_dir: Path, taxonomy_date: str | None = None
) -> dict[str, CategoryMapper]:
    """One CategoryMapper per source (food, beauty, products) with the newest taxonomy."""
    mapping = yaml.safe_load((MAPPING / "off_to_group.yaml").read_text())
    mappers = {}
    for source, entries in mapping.items():
        pattern = f"tax-{source}-{taxonomy_date or '*'}.json"
        candidates = sorted(raw_dir.glob(pattern))
        if not candidates:
            raise SystemExit(f"no taxonomy {pattern}, run scripts/fetch.py first")
        mappers[source] = CategoryMapper(entries, Taxonomy(candidates[-1]))
    return mappers
