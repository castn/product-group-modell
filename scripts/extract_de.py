"""Extracts the German products from the raw data to data/interim/de.parquet.

A product is included if it has a German name: an entry with lang = "de",
or the main name ("main") if the main language is German.

- Food: additionally sold in DE, AT or CH, so that it looks like the German
  assortment and not like translated foreign products.
- Beauty, Products and Petfood: no country filter, because there are too few
  products there.

Duplicates are not removed here yet; that only happens after normalization,
so that spelling variants fall together.

Usage:  uv run scripts/extract_de.py
"""

import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "interim" / "de.parquet"

DACH = ["en:germany", "en:austria", "en:switzerland"]


def latest(source: str) -> Path:
    """Newest complete file of a source per the manifest (without --limit runs)."""
    manifest = json.loads((RAW / "MANIFEST.json").read_text())
    names = sorted(
        n for n in manifest if n.startswith(f"{source}-") and "-limit" not in n
    )
    if not names:
        raise SystemExit(f"no raw data for {source}, run scripts/fetch.py first")
    return RAW / names[-1]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    selects = []
    for source in ("food", "beauty", "products", "petfood"):
        path = latest(source)
        country_filter = (
            f"AND list_has_any(countries_tags, {DACH})" if source == "food" else ""
        )
        selects.append(f"""
            SELECT
                '{source}' AS source,
                code,
                list_filter(product_name,
                    x -> x.lang = 'de' OR (x.lang = 'main' AND t.lang = 'de')
                )[1].text AS name_de,
                list_filter(generic_name,
                    x -> x.lang = 'de' OR (x.lang = 'main' AND t.lang = 'de')
                )[1].text AS generic_de,
                brands,
                brands_tags,
                categories_tags,
                list_has_any(countries_tags, {DACH}) AS dach,
                stores_tags,
                quantity,
                coalesce(unique_scans_n, 0) AS scans
            FROM '{path}' t
            WHERE trim(coalesce(name_de, '')) <> '' {country_filter}
        """)
    con = duckdb.connect()
    con.sql(f"""
        COPY ({" UNION ALL ".join(selects)})
        TO '{OUT}' (FORMAT parquet, COMPRESSION zstd)
    """)
    for source, n in con.sql(
        f"SELECT source, count(*) FROM '{OUT}' GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"{source:9s} {n:>8,}", file=sys.stderr)


if __name__ == "__main__":
    main()
