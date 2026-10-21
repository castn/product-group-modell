"""Builds the training and validation data.

Input:   data/interim/de_labeled.parquet (scripts/mapping_report.py)
Output:  data/processed/dataset.parquet with the columns
         text, store, label, product, split ("train" or "val"), clean,
         origin ("product", "generic" or "taxonomy")

1. Products with a class, grouped by normalized name. If the same name has
   different classes, the majority wins if it has at least 80 %, otherwise the
   name is dropped.
2. Split per product (by hash of the name), before augmentation, so that
   variants of the same product do not end up in both training and validation.
3. Per product the clean name and several receipt-style variants. Rare classes
   get more variants (up to VARIANTS_MAX), so that each class has about
   TARGET_PER_CLASS rows. Plus the generic name of the product (generic_name,
   e.g. "Vollmilchschokolade"), if there is one.
4. The German category names from the taxonomies ("Feigen", "Kürbiskerne") with
   the class the category is mapped to. Open Food Facts knows almost only
   packaged goods; but loose goods appear on the receipt with exactly such
   generic names. These names take precedence over products with the same name:
   "Paprika" is a vegetable, even if many products named "Paprika" are crisps.

Usage:  uv run scripts/build_dataset.py [--seed N]
"""

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

import polars as pl

from pgm.augment import augment
from pgm.categories import load_mappers
from pgm.normalize import normalize
from pgm.stores import chain_of

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / "data" / "interim" / "de_labeled.parquet"
OUT = ROOT / "data" / "processed" / "dataset.parquet"

VAL_SHARE = 0.1
MAJORITY = 0.8
TARGET_PER_CLASS = 6000
VARIANTS_MIN, VARIANTS_MAX = 2, 30
VAL_VARIANTS = 2
TAXONOMY_VARIANTS = 12
STORE_SHARE = 0.7  # share of variants with a store, if the product has stores


def split_of(key: str) -> str:
    h = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16)
    return "val" if h % 1000 < VAL_SHARE * 1000 else "train"


def products() -> pl.DataFrame:
    df = (
        pl.read_parquet(IN)
        .filter(pl.col("label").is_not_null())
        .with_columns(
            pl.col("name_de")
            .map_elements(normalize, return_dtype=pl.String)
            .alias("key")
        )
        .filter(pl.col("key").str.len_chars() >= 3)
    )
    votes = df.group_by("key", "label").len()
    totals = votes.group_by("key").agg(pl.col("len").sum().alias("total"))
    winners = (
        votes.join(totals, on="key")
        .filter(pl.col("len") >= MAJORITY * pl.col("total"))
        .select("key", "label")
    )
    dropped = totals.height - winners.height
    print(
        f"names: {totals.height:,}, dropped as ambiguous: {dropped:,}",
        file=sys.stderr,
    )
    return (
        df.join(winners, on=["key", "label"])
        .group_by("key")
        .agg(
            pl.col("label").first(),
            pl.col("name_de").first(),
            pl.col("brands").drop_nulls().first(),
            pl.col("quantity").drop_nulls().first(),
            pl.col("generic_de").drop_nulls().first(),
            pl.col("stores_tags")
            .list.explode(keep_nulls=False, empty_as_null=False)
            .unique(),
        )
        .sort("key")
    )


def taxonomy_names() -> dict[str, tuple[str, str]]:
    """Normalized name → (German category name, class) from all taxonomies."""
    raw = ROOT / "data" / "raw"
    result: dict[str, tuple[str, str]] = {}
    conflicts: set[str] = set()
    for source, mapper in load_mappers(raw).items():
        path = max(raw.glob(f"tax-{source}-*.json"))
        for tag, entry in json.loads(path.read_text()).items():
            name = (entry.get("name") or {}).get("de")
            if not name:
                continue
            res = mapper.resolve([tag])
            key = normalize(name)
            if res.label is None or len(key) < 3:
                continue
            if key in result and result[key][1] != res.label:
                conflicts.add(key)
            result[key] = (name, res.label)
    for key in conflicts:
        del result[key]
    print(f"category names: {len(result):,}", file=sys.stderr)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    taxonomy = taxonomy_names()
    prods = products().filter(~pl.col("key").is_in(list(taxonomy)))
    per_class = Counter(prods["label"])
    variants = {
        label: max(VARIANTS_MIN, min(VARIANTS_MAX, math.ceil(TARGET_PER_CLASS / n)))
        for label, n in per_class.items()
    }

    rows = []

    def add(name, label, key, n, origin, brand=None, quantity=None, chains=()):
        split = split_of(key)
        rows.append((name, None, label, key, split, True, origin))
        for _ in range(VAL_VARIANTS if split == "val" else n):
            chain = (
                rng.choice(chains) if chains and rng.random() < STORE_SHARE else None
            )
            text = augment(
                name, label, rng, brand=brand, quantity=quantity, chain=chain
            )
            if text:
                rows.append((text, chain, label, key, split, False, origin))

    for p in prods.iter_rows(named=True):
        chains = sorted({c for t in p["stores_tags"] or [] if (c := chain_of(t))})
        add(
            p["name_de"],
            p["label"],
            p["key"],
            variants[p["label"]],
            "product",
            brand=p["brands"],
            quantity=p["quantity"],
            chains=chains,
        )
        generic = p["generic_de"]
        if generic and len(normalize(generic)) >= 3 and normalize(generic) != p["key"]:
            # same key as the product, so that both end up in the same split
            add(generic, p["label"], p["key"], 1, "generic")

    for key, (name, label) in sorted(taxonomy.items()):
        add(name, label, key, TAXONOMY_VARIANTS, "taxonomy")

    out = pl.DataFrame(
        rows,
        schema={
            "text": pl.String,
            "store": pl.String,
            "label": pl.String,
            "product": pl.String,
            "split": pl.String,
            "clean": pl.Boolean,
            "origin": pl.String,
        },
        orient="row",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(OUT, compression="zstd")
    summary = out.group_by("split", "origin").agg(
        pl.len().alias("rows"), pl.col("product").n_unique().alias("products")
    )
    print(summary, file=sys.stderr)


if __name__ == "__main__":
    main()
