"""Builds the download index models.json from the published GitHub releases.

Input:   the releases of the repository (GitHub API), each with
             pgm-f<format>-<modelversion>.bin and pgm-f<format>-<modelversion>.bin.sha256
Output:  models.json, the newest model per format and market (scheme in docs/interface.md)

Considered are releases with a tag model-<modelversion> that are neither drafts nor
pre-releases and whose version has no -rc suffix. Of these, the newest per format and
market is taken; its file is downloaded and checked against size and SHA-256.
Any problem with a chosen model aborts, so the previous index stays online.

Rollback: mark the bad release as pre-release (or delete it); the workflow
.github/workflows/model-index.yml then publishes the index again.

Only the standard library, so the workflow needs no installation.

Usage:  python3 scripts/model_index.py --repo castn/product-group-modell --out site/models.json
        (GITHUB_TOKEN from the environment, optional for public repositories)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SCHEMA = 1
API = "https://api.github.com"
# Same scheme as pgm.export.model_version / file_name, without -rc (tests/test_model_index.py)
VERSION = re.compile(
    r"(?P<market>[a-z]{2}-[A-Z]{2})-(?P<year>\d{4})\.(?P<month>0[1-9]|1[0-2])\.(?P<seq>[1-9]\d*)"
)
FILE = re.compile(r"pgm-f(?P<format>[1-9]\d*)-(?P<version>.+)\.bin")


def request(url: str, token: str | None, accept: str = "application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "model-index"}
    if token and url.startswith(API):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers))


def releases(repo: str, token: str | None) -> list[dict]:
    out, page = [], 1
    while True:
        url = f"{API}/repos/{repo}/releases?per_page=100&page={page}"
        with request(url, token) as r:
            batch = json.load(r)
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def candidates(rels: list[dict]) -> list[dict]:
    """One candidate per model file in published, final model releases."""
    out = []
    for rel in rels:
        if rel["draft"] or rel["prerelease"]:
            continue
        version = rel["tag_name"].removeprefix("model-")
        v = VERSION.fullmatch(version)
        if not rel["tag_name"].startswith("model-") or not v:
            continue
        assets = {a["name"]: a for a in rel["assets"]}
        for name, asset in assets.items():
            f = FILE.fullmatch(name)
            if not f or f["version"] != version:
                continue
            out.append(
                {
                    "format": int(f["format"]),
                    "market": v["market"],
                    "version": version,
                    "tag": rel["tag_name"],
                    "order": (int(v["year"]), int(v["month"]), int(v["seq"])),
                    "asset": asset,
                    "checksum": assets.get(f"{name}.sha256"),
                }
            )
    return out


def newest(cands: list[dict]) -> list[dict]:
    """The newest candidate per format and market, sorted by market and format."""
    best: dict[tuple[int, str], dict] = {}
    for c in cands:
        key = (c["format"], c["market"])
        if key not in best or c["order"] > best[key]["order"]:
            best[key] = c
    return sorted(best.values(), key=lambda c: (c["market"], c["format"]))


def entry(c: dict, token: str | None, repo: str) -> dict:
    """Index entry for a candidate, after checking file, size and SHA-256."""
    name = c["asset"]["name"]
    if c["checksum"] is None:
        raise SystemExit(f"{c['tag']}: {name}.sha256 missing in the release")
    with request(c["checksum"]["browser_download_url"], token, "*/*") as r:
        expected, _, listed = r.read().decode().strip().partition("  ")
    if listed != name or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SystemExit(f"{c['tag']}: {name}.sha256 is not a checksum for {name}")
    with request(c["asset"]["browser_download_url"], token, "*/*") as r:
        data = r.read()
    if len(data) != c["asset"]["size"]:
        raise SystemExit(
            f"{c['tag']}: {name} has {len(data)} bytes, release says {c['asset']['size']}"
        )
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f"{c['tag']}: SHA-256 of {name} does not match {name}.sha256")
    with request(f"{API}/repos/{repo}/commits/{c['tag']}", token) as r:
        commit = json.load(r)["sha"]
    return {
        "format": c["format"],
        "market": c["market"],
        "version": c["version"],
        "url": c["asset"]["browser_download_url"],
        "size": len(data),
        "sha256": expected,
        "commit": commit,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")

    chosen = newest(candidates(releases(args.repo, token)))
    models = [entry(c, token, args.repo) for c in chosen]
    for m in models:
        print(f"f{m['format']} {m['market']}: {m['version']}", file=sys.stderr)
    if not models:
        print("no published model, empty index", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    index = {"schema": SCHEMA, "models": models}
    args.out.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
