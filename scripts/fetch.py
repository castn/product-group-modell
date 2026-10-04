"""Downloads the raw data from Open Food/Beauty/Products Facts to data/raw/.

- Food and Beauty: Parquet files from Hugging Face (openfoodfacts/product-database),
  pinned to a fixed revision. The files are downloaded in full to data/raw/cache/
  (food: about 7.8 GB, resumable) and then reduced locally with DuckDB to the
  columns needed. Reading columns directly over HTTP fails because of the
  number of range requests: Hugging Face answers anonymous clients with HTTP 429.
- Products: JSONL export from static.openproductsfacts.org (not on Hugging Face),
  streamed and converted to the same schema.

There is no filtering by language or country (step 10 needs all languages),
only entries without a product name or without a category are dropped.

Usage:  uv run scripts/fetch.py [--limit N] [--only food,beauty,products]
"""

import argparse
import datetime as dt
import gzip
import hashlib
import http.client
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import duckdb
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CACHE = RAW / "cache"
MANIFEST = RAW / "MANIFEST.json"

HF_REPO = "openfoodfacts/product-database"
HF_API = f"https://huggingface.co/api/datasets/{HF_REPO}"
OPF_JSONL = (
    "https://static.openproductsfacts.org/data/openproductsfacts-products.jsonl.gz"
)

COLUMNS = [
    "code",
    "lang",
    "product_name",  # list of {lang, text}
    "generic_name",  # list of {lang, text}
    "brands",
    "brands_tags",
    "categories_tags",
    "countries_tags",
    "stores_tags",
    "quantity",
    "unique_scans_n",
    "obsolete",
]


def hf_revision() -> str:
    with urllib.request.urlopen(HF_API) as resp:
        return json.load(resp)["sha"]


def _open_with_retry(req: urllib.request.Request, attempts: int = 10):
    """On HTTP 429, waits until the rate limit window has been reset."""
    for _ in range(attempts - 1):
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            # Hugging Face: 'ratelimit: "resolvers";r=0;t=33' (t = seconds until reset)
            m = re.search(r"t=(\d+)", e.headers.get("ratelimit", ""))
            wait = int(m.group(1)) if m else int(e.headers.get("Retry-After", 60))
            print(f"  HTTP 429, waiting {wait + 5} s", file=sys.stderr)
            time.sleep(wait + 5)
    return urllib.request.urlopen(req)


def hf_file_info(revision: str, path: str) -> dict:
    """Size and SHA-256 of an LFS file in the given revision."""
    with urllib.request.urlopen(f"{HF_API}/tree/{revision}") as resp:
        entry = next(e for e in json.load(resp) if e["path"] == path)
    return {"size": entry["lfs"]["size"], "sha256": entry["lfs"]["oid"]}


def download(url: str, out: Path, size: int, sha: str, attempts: int = 20) -> None:
    """Downloads url to out and checks size and SHA-256.

    If the connection drops (even without an error message), the download
    resumes at the last position via Range.
    """
    if out.exists():
        return
    part = out.with_suffix(out.suffix + ".part")
    for _ in range(attempts):
        done = part.stat().st_size if part.exists() else 0
        if done >= size:
            break
        req = urllib.request.Request(url, headers={"Range": f"bytes={done}-"})
        try:
            with _open_with_retry(req) as resp:
                if done and resp.status != 206:
                    done = 0  # server cannot resume, start over
                with part.open("ab" if done else "wb") as f:
                    last = done / 1e9
                    while chunk := resp.read(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        if done / 1e9 - last >= 0.1:
                            last = done / 1e9
                            print(
                                f"  {last:.1f} / {size / 1e9:.1f} GB", file=sys.stderr
                            )
        except (OSError, http.client.HTTPException) as e:
            print(f"  connection lost ({e}), resuming", file=sys.stderr)
            time.sleep(10)
    if part.stat().st_size != size:
        raise SystemExit(f"{part}: {part.stat().st_size} instead of {size} bytes")
    print("  checking SHA-256", file=sys.stderr)
    if sha256(part) != sha:
        part.unlink()
        raise SystemExit(f"{part}: SHA-256 does not match, file deleted")
    part.rename(out)


def fetch_hf(split: str, revision: str, out: Path, limit: int | None) -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    src = CACHE / f"{split}-{revision[:12]}.parquet"
    url = (
        f"https://huggingface.co/datasets/{HF_REPO}/resolve/{revision}/{split}.parquet"
    )
    info = hf_file_info(revision, f"{split}.parquet")
    download(url, src, info["size"], info["sha256"])
    con = duckdb.connect()
    limit_sql = f"LIMIT {limit}" if limit else ""
    con.sql(f"""
        COPY (
            SELECT {", ".join(COLUMNS)}
            FROM '{src}'
            WHERE len(product_name) > 0
              AND len(categories_tags) > 0
              AND coalesce(obsolete, false) = false
            {limit_sql}
        ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    return con.sql(f"SELECT count(*) FROM '{out}'").fetchone()[0]


def _lang_texts(obj: dict, field: str) -> list[dict]:
    """product_name_de, product_name_fr, … → [{lang, text}] as in the HF schema."""
    result = []
    main = obj.get(field)
    if main and obj.get("lang"):
        result.append({"lang": "main", "text": main})
    prefix = field + "_"
    for key, value in obj.items():
        if key.startswith(prefix) and isinstance(value, str) and value.strip():
            lang = key[len(prefix) :]
            if 2 <= len(lang) <= 3 and lang.isalpha():
                result.append({"lang": lang, "text": value})
    return result


def fetch_opf(out: Path, limit: int | None) -> int:
    rows = []
    with (
        urllib.request.urlopen(OPF_JSONL) as resp,
        gzip.open(resp, "rt", encoding="utf-8") as lines,
    ):
        for line in lines:
            obj = json.loads(line)
            names = _lang_texts(obj, "product_name")
            cats = obj.get("categories_tags") or []
            if not names or not cats or obj.get("obsolete"):
                continue
            rows.append(
                {
                    "code": str(obj.get("code") or obj.get("_id") or ""),
                    "lang": obj.get("lang"),
                    "product_name": names,
                    "generic_name": _lang_texts(obj, "generic_name"),
                    "brands": obj.get("brands"),
                    "brands_tags": obj.get("brands_tags") or [],
                    "categories_tags": cats,
                    "countries_tags": obj.get("countries_tags") or [],
                    "stores_tags": obj.get("stores_tags") or [],
                    "quantity": obj.get("quantity"),
                    "unique_scans_n": obj.get("unique_scans_n"),
                    "obsolete": False,
                }
            )
            if limit and len(rows) >= limit:
                break
    struct = pl.List(pl.Struct({"lang": pl.String, "text": pl.String}))
    schema = {
        "code": pl.String,
        "lang": pl.String,
        "product_name": struct,
        "generic_name": struct,
        "brands": pl.String,
        "brands_tags": pl.List(pl.String),
        "categories_tags": pl.List(pl.String),
        "countries_tags": pl.List(pl.String),
        "stores_tags": pl.List(pl.String),
        "quantity": pl.String,
        "unique_scans_n": pl.Int64,
        "obsolete": pl.Boolean,
    }
    pl.DataFrame(rows, schema=schema).write_parquet(out, compression="zstd")
    return len(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only N rows per source (test)")
    parser.add_argument("--only", default="food,beauty,products")
    parser.add_argument(
        "--revision",
        help="revision (commit) on Hugging Face; default: current state. "
        "To resume a download, pass the same revision.",
    )
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.UTC).date().isoformat()
    suffix = f"-limit{args.limit}" if args.limit else ""
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    sources = args.only.split(",")
    revision = args.revision
    if revision is None and {"food", "beauty"} & set(sources):
        revision = hf_revision()

    for source in sources:
        out = RAW / f"{source}-{today}{suffix}.parquet"
        print(f"[{source}] → {out.relative_to(ROOT)}", file=sys.stderr)
        if source in ("food", "beauty"):
            n = fetch_hf(source, revision, out, args.limit)
            origin = {
                "url": f"https://huggingface.co/datasets/{HF_REPO}",
                "revision": revision,
                "file": f"{source}.parquet",
            }
        elif source == "products":
            n = fetch_opf(out, args.limit)
            origin = {"url": OPF_JSONL}
        else:
            raise SystemExit(f"unknown source: {source}")
        manifest[out.name] = {
            **origin,
            "fetched": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "rows": n,
            "bytes": out.stat().st_size,
            "sha256": sha256(out),
            "license": "ODbL 1.0 (database), DbCL 1.0 (contents)",
        }
        print(
            f"[{source}] {n:,} rows, {out.stat().st_size / 1e6:.1f} MB",
            file=sys.stderr,
        )
        # write after every source so that a later error loses nothing
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
