"""Assigns a fine class to products based on their categories.

Rules and mapping: mapping/off_to_class.yaml. The app's item group follows
from the class (mapping/classes.yaml).
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
STRONG = "+"


def model_groups() -> list[str]:
    """Item groups of the app that the model covers, in the order of groups.yaml."""
    groups = yaml.safe_load((MAPPING / "groups.yaml").read_text())["groups"]
    return [g["id"] for g in groups if g["model"]]


def class_groups() -> dict[str, str]:
    """Classes of the model → item group of the app, in the order of classes.yaml."""
    classes = yaml.safe_load((MAPPING / "classes.yaml").read_text())["classes"]
    groups = set(model_groups())
    result = {}
    for c in classes:
        if c["group"] not in groups:
            raise ValueError(f"class {c['id']}: unknown group {c['group']}")
        if c["id"] in result:
            raise ValueError(f"class {c['id']} duplicated")
        result[c["id"]] = c["group"]
    return result


@dataclass(frozen=True)
class Resolution:
    label: str | None
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
        self.known = frozenset(self._parents)
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
        labels: list[str] | None = None,
    ):
        valid = set(labels if labels is not None else class_groups()) | {DROP}
        unknown = {
            g
            for g in mapping.values()
            if g is not None and g.lstrip(WEAK + STRONG) not in valid
        }
        if unknown:
            raise ValueError(f"unknown classes in the mapping: {sorted(unknown)}")
        self.default = mapping.get(DEFAULT)
        entries = {t: g for t, g in mapping.items() if t != DEFAULT}
        # class without prefix; rank: "+" preferred 2, normal 1, "~" weak 0
        self.mapping = {
            t: g.lstrip(WEAK + STRONG) if g else g for t, g in entries.items()
        }
        self.rank = {
            t: 2 if g.startswith(STRONG) else 0 if g.startswith(WEAK) else 1
            for t, g in entries.items()
            if g
        }
        self.weak = {t for t, r in self.rank.items() if r == 0}
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
        # only the most specific categories with the highest rank count
        top = max(self.rank[t] for t in leaves)
        leaves = [t for t in leaves if self.rank[t] == top]
        labels = {mapped[t] for t in leaves}
        if len(labels) == 1:
            return Resolution(labels.pop(), "mapped", tuple(leaves))
        return Resolution(None, "conflict", tuple(leaves))


def load_mappers(
    raw_dir: Path, taxonomy_date: str | None = None
) -> dict[str, CategoryMapper]:
    """One CategoryMapper per source with the newest taxonomy."""
    mapping = yaml.safe_load((MAPPING / "off_to_class.yaml").read_text())
    mappers = {}
    for source, entries in mapping.items():
        pattern = f"tax-{source}-{taxonomy_date or '*'}.json"
        candidates = sorted(raw_dir.glob(pattern))
        if not candidates:
            raise SystemExit(f"no taxonomy {pattern}, run scripts/fetch.py first")
        mappers[source] = CategoryMapper(entries, Taxonomy(candidates[-1]))
    return mappers
