"""Assembles the files for a release of a model.

Input:   dist/pgm-f<format>-<modelversion>.bin (scripts/export.py)
         data/raw/MANIFEST.json
Output:  release/<modelversion>/
             pgm-f<format>-<modelversion>.bin          model file
             pgm-f<format>-<modelversion>.bin.sha256   checksum (sha256sum -c …)
             RELEASE.md                                text for the release page, do not upload

Checked beforehand:
- the file is readable (magic, format, CRC) and carries the model version in the header,
- the Kotlin test computes it like Python (kotlin/: ./gradlew :reference:test),
- the repository has no uncommitted changes, so that the release matches the commit.

Not included in the release: dist/*.golden.tsv (transformed product names, see
docs/license.md) and anything from data/ and reports/.

Nothing is uploaded. At the end, the commands for tag and upload are printed.

Usage:  uv run scripts/release.py --version de-DE-2026.10.1 [--skip-kotlin] [--allow-dirty]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pgm.export import FORMAT, file_name, read

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://codeberg.org/castn/product-group-modell"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def sources() -> list[dict]:
    manifest = json.loads((ROOT / "data" / "raw" / "MANIFEST.json").read_text())
    return [
        {"file": name}
        | {k: v[k] for k in ("url", "revision", "fetched", "rows") if k in v}
        for name, v in manifest.items()
    ]


def release_notes(version: str, commit: str, sources: list[dict]) -> str:
    market = version.rsplit("-", 1)[0]
    lines = [
        f"# Model {version}",
        "",
        (
            "Assigns item names from receipts to an item group "
            f"(market {market}). Description, integration and license: {REPO_URL}"
        ),
        "",
        (
            f"Format {FORMAT}: loads only with the Kotlin files for format {FORMAT} "
            f"(`kotlin/reference/`, commit `{commit}`)."
        ),
        "",
        "## Data",
        "",
        (
            "Trained with data from Open Food Facts, Open Beauty Facts, Open Products "
            "Facts and Open Pet Food Facts (https://openfoodfacts.org) under the Open "
            "Database License (ODbL 1.0), contents under DbCL 1.0. How the model is "
            f"built from the data is in the repository ({REPO_URL}, commit `{commit}`)."
        ),
        "",
        "| Source | Revision | fetched | Rows |",
        "|---|---|---|---:|",
    ]
    for src in sources:
        revision = f"`{src['revision'][:12]}`" if "revision" in src else "–"
        lines.append(
            f"| {src['url']} ({src['file']}) | {revision} | {src['fetched'][:10]} "
            f"| {src['rows']:,} |".replace(",", ".")
        )
    lines += [
        "",
        (
            "Anyone who uses the model publicly must credit Open Food Facts and the "
            "ODbL (§4.3)."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="e.g. de-DE-2026.10.1")
    parser.add_argument(
        "--skip-kotlin", action="store_true", help="do not run the Kotlin test"
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", help="allow uncommitted changes"
    )
    parser.add_argument(
        "--force", action="store_true", help="replace an existing release/<version>/"
    )
    args = parser.parse_args()
    version = args.version

    src = ROOT / "dist" / file_name(version)
    if not src.exists():
        raise SystemExit(f"{src.relative_to(ROOT)} missing (scripts/export.py)")
    model = read(src)  # checks magic, format and CRC
    if model.version != version:
        raise SystemExit(
            f"{src.name}: version in the header is {model.version!r}, export again"
        )

    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty and not args.allow_dirty:
        raise SystemExit(f"uncommitted changes:\n{dirty}\n(--allow-dirty)")
    commit = git("rev-parse", "HEAD") + ("-dirty" if dirty else "")

    if not args.skip_kotlin:
        print("Kotlin test …", file=sys.stderr)
        subprocess.run(
            ["./gradlew", "-q", ":reference:test", "--rerun-tasks"],
            cwd=ROOT / "kotlin",
            check=True,
        )

    out = ROOT / "release" / version
    if out.exists():
        if not args.force:
            raise SystemExit(f"{out.relative_to(ROOT)} already exists (--force)")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    data = src.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    shutil.copyfile(src, out / src.name)
    checksum = out / f"{src.name}.sha256"
    checksum.write_text(f"{sha256}  {src.name}\n", encoding="utf-8")

    data_sources = sources()
    (out / "RELEASE.md").write_text(
        release_notes(version, commit, data_sources), encoding="utf-8"
    )

    rel = out.relative_to(ROOT)
    print(f"→ {rel}/", file=sys.stderr)
    for f in sorted(out.iterdir()):
        print(f"   {f.name}  ({f.stat().st_size:,} bytes)", file=sys.stderr)
    revisions = sorted({s["revision"][:12] for s in data_sources if "revision" in s})
    print(
        f"""
Next steps:
  git tag -a model-{version} -m "Model {version}, raw data {", ".join(revisions)}"
  git push origin model-{version}
  Create a release for the tag at {REPO_URL}/releases/new,
  text from {rel}/RELEASE.md, attachments: {src.name}, {checksum.name}""",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
