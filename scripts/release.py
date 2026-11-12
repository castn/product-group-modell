"""Assembles the files for a release of a model.

Input:   dist/pgm-f<format>-<modelversion>.bin (scripts/export.py)
         data/raw/MANIFEST.json
Output:  release/<modelversion>/
             pgm-f<format>-<modelversion>.bin          model file
             pgm-f<format>-<modelversion>.bin.sha256   checksum (sha256sum -c …)
             RELEASE.md                                text for the release page, do not upload
             TAG.txt                                   message for the git tag (git tag -a … -F)

Checked beforehand:
- the file is readable (magic, format, CRC) and carries the model version in the header,
- the Kotlin test computes it like Python (kotlin/: ./gradlew :reference:test),
- the repository has no uncommitted changes, so that the release matches the commit.

Not included in the release: dist/*.golden.tsv (transformed product names, see
docs/data-license.md) and anything from data/ and reports/.

Nothing is uploaded. At the end, the commands for tag and upload are printed.

Usage:  uv run scripts/release.py --version de-DE-2026.10.1 [--skip-kotlin] [--allow-dirty]
"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pgm.export import FORMAT, MARKET, ExportedModel, file_name, read

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/castn/product-group-modell"
LICENSE_DOC = "docs/data-license.md"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def sources() -> list[dict]:
    manifest = json.loads((ROOT / "data" / "raw" / "MANIFEST.json").read_text())
    return [
        {"file": name}
        | {k: v[k] for k in ("url", "revision", "fetched", "rows", "sha256") if k in v}
        for name, v in sorted(manifest.items(), key=lambda item: source_rank(item[0]))
    ]


# Prefix of the manifest key → readable name of the source, in the order of the notes
SOURCE_NAMES = {
    "food": "Open Food Facts, products",
    "tax-food": "Open Food Facts, categories",
    "beauty": "Open Beauty Facts, products",
    "tax-beauty": "Open Beauty Facts, categories",
    "products": "Open Products Facts, products",
    "tax-products": "Open Products Facts, categories",
    "petfood": "Open Pet Food Facts, products",
    "tax-petfood": "Open Pet Food Facts, categories",
}


def source_prefix(file: str) -> str:
    return file.rsplit("-", 3)[0]  # "tax-food-2026-10-03.json" → "tax-food"


def source_rank(file: str) -> tuple[int, str]:
    order = list(SOURCE_NAMES)
    prefix = source_prefix(file)
    return (order.index(prefix) if prefix in order else len(order), file)


def source_name(file: str) -> str:
    return SOURCE_NAMES.get(source_prefix(file), file)


def file_name_parts(model_file: str, market: str) -> list[str]:
    """The file name with each part explained below it, as in docs/interface.md."""
    col_format = len("pgm-")
    col_market = len(f"pgm-f{FORMAT}-")
    col_month = col_market + len(market) + 1
    col_seq = col_month + len("YYYY.MM.")
    month = model_file[col_month : col_seq - 1].replace(".", "-")
    seq = "sequence number within the month"
    if "-rc" in model_file:
        seq += ", -rc… marks a release candidate"
    parts = [
        (col_format, f"file format {FORMAT}"),
        (
            col_market,
            f"market {market} (language-country): chains, private labels, abbreviations differ per country",
        ),
        (
            col_month,
            f"month of the data snapshot ({month}, see Data), not of the build",
        ),
        (col_seq, seq),
    ]
    lines = [model_file]
    for i in reversed(range(len(parts))):
        row = [" "] * parts[i][0]
        for col, _ in parts[:i]:
            row[col] = "│"
        lines.append("".join(row) + "└ " + parts[i][1])
    return lines


def release_notes(
    version: str,
    commit: str,
    sources: list[dict],
    model: ExportedModel,
    model_file: str,
    size: int,
    sha256: str,
) -> str:
    market = MARKET.match(version).group()
    exported = datetime.fromtimestamp(model.created, UTC).strftime("%Y-%m-%d")
    sha = commit.removesuffix("-dirty")
    commit_link = f"[`{sha[:12]}`]({REPO_URL}/commit/{sha})"
    license_link = f"[{LICENSE_DOC}]({REPO_URL}/blob/{sha}/{LICENSE_DOC})"
    lines = [f"# Model {version}", ""]
    if commit.endswith("-dirty"):
        lines += [
            "> [!CAUTION]",
            "> Built from uncommitted changes (`--allow-dirty`). This model cannot be",
            "> reproduced from the repository. **Do not publish it.**",
            "",
        ]
    lines += [
        f"Assigns item names from receipts to an item group (market `{market}`).",
        f"Description, integration and license: {REPO_URL}",
        "",
        "| | |",
        "|---|---|",
        f"| Market | `{market}` |",
        f"| File format | {FORMAT} |",
        f"| Size | {size / 1e6:.2f} MB |",
        f"| Classes / groups | {len(model.labels)} / {len(set(model.groups))} |",
        f"| Thresholds | `SURE` ≥ {model.t_sure:g}, `SUGGESTION` ≥ {model.t_suggest:g} |",
        f"| Exported | {exported} |",
        f"| Commit | {commit_link} |",
        "",
        "## Files",
        "",
        f"`{model_file}` · SHA-256 `{sha256}`",
        "",
        f"Check after download: `sha256sum -c {model_file}.sha256`",
        "",
        "```",
        *file_name_parts(model_file, market),
        "```",
        "",
        "> [!IMPORTANT]",
        f"> **Format {FORMAT}** loads only with the Kotlin files for format {FORMAT}",
        "> (`kotlin/reference/` at the commit above).",
        "> With older files, the app rejects the model and works without it.",
        "",
        "## Data",
        "",
        "Trained with data from Open Food Facts, Open Beauty Facts, Open Products Facts",
        "and Open Pet Food Facts (https://openfoodfacts.org) under the",
        "Open Database License (ODbL 1.0), contents under DbCL 1.0.",
        "How the model is built from the data is in the repository at the commit above.",
        "",
        "| Source | Fetched | Rows | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for src in sources:
        name = f"[{source_name(src['file'])}]({src['url']})"
        if "revision" in src:
            name += f" @ `{src['revision'][:12]}`"
        lines.append(
            f"| {name} | {src['fetched'][:10]} | {src['rows']:,} "
            f"| `{src['sha256'][:12]}` |"
        )
    lines += [
        "",
        "> [!NOTE]",
        "> Anyone who uses the model publicly must credit Open Food Facts and the",
        f"> ODbL (§4.3). Notice text for apps: {license_link}.",
        "",
    ]
    return "\n".join(lines)


def tag_message(
    version: str,
    commit: str,
    sources: list[dict],
    model: ExportedModel,
    model_file: str,
    size: int,
    sha256: str,
) -> str:
    """Message for the annotated tag, values as git trailers (git interpret-trailers --parse)."""
    market = MARKET.match(version).group()
    month = version.removeprefix(f"{market}-")[: len("YYYY.MM")].replace(".", "-")
    exported = datetime.fromtimestamp(model.created, UTC).strftime("%Y-%m-%d")
    fetched = sorted(src["fetched"][:10] for src in sources)
    revisions = sorted({src["revision"] for src in sources if "revision" in src})
    pinned = [source_prefix(src["file"]) for src in sources if "revision" in src]
    unpinned = [source_prefix(src["file"]) for src in sources if "revision" not in src]
    lines = [
        f"Model {version}",
        "",
        f"File format {FORMAT}, market {market}, data snapshot {month}.",
    ]
    if commit.endswith("-dirty"):
        lines.append("Built from uncommitted changes (--allow-dirty), do not publish.")
    lines += [
        "",
        f"Model-File: {model_file}",
        f"Model-SHA256: {sha256}",
        f"Model-Size: {size}",
        f"Format: {FORMAT}",
        f"Classes: {len(model.labels)}",
        f"Groups: {len(set(model.groups))}",
        f"Threshold-Sure: {model.t_sure:g}",
        f"Threshold-Suggestion: {model.t_suggest:g}",
        f"Exported: {exported}",
        *(f"Data-HF-Revision: {rev}" for rev in revisions),
        f"Data-Fetched: {fetched[0]}..{fetched[-1]}",
        f"Data-Pinned: {', '.join(pinned) or '-'}",
        f"Data-Unpinned: {', '.join(unpinned) or '-'}",
        f"Python: {platform.python_version()}",
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
    facts = (version, commit, data_sources, model, src.name, len(data), sha256)
    (out / "RELEASE.md").write_text(release_notes(*facts), encoding="utf-8")
    (out / "TAG.txt").write_text(tag_message(*facts), encoding="utf-8")

    rel = out.relative_to(ROOT)
    print(f"→ {rel}/", file=sys.stderr)
    for f in sorted(out.iterdir()):
        print(f"   {f.name}  ({f.stat().st_size:,} bytes)", file=sys.stderr)
    print(
        f"""
Next steps:
  git tag -a model-{version} -F {rel}/TAG.txt
  git push origin model-{version}
  Create a release for the tag at {REPO_URL}/releases/new,
  text from {rel}/RELEASE.md, attachments: {src.name}, {checksum.name}
  Publishing the release (not as pre-release) updates models.json on GitHub Pages
  (.github/workflows/model-index.yml, docs/interface.md#download-index).""",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
