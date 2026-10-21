"""Exports a trained model in the app's format.

Input:   models/<name>/ (scripts/train.py)
Output:  dist/pgm-f<format>-<market>-<release>.bin          model file for the app
         dist/pgm-f<format>-<market>-<release>.golden.tsv   expected predictions for the Kotlin test

Version scheme: docs/interface.md, section "Versions and file names".

Before writing, checks how much rounding the feature vectors to int8 changes the
predictions on the validation set. The golden values contain only self-written
lines and generated validation lines, no real test data.

Usage:  uv run scripts/export.py --name dev4 --release 2026.10.1 [--market de-DE]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

from pgm.categories import class_groups
from pgm.export import (
    ExportedModel,
    file_name,
    model_version,
    now,
    probabilities,
    quantize,
    read,
    write,
)
from pgm.golden import golden_inputs, model_tsv
from pgm.model import Featurizer, load, predict_proba
from pgm.stores import table

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed" / "dataset.parquet"
MAX_BYTES = 2 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--market", default="de-DE", help="language-country, e.g. de-DE"
    )
    parser.add_argument("--release", required=True, help="YYYY.MM.N, e.g. 2026.10.1")
    parser.add_argument("--t-sure", type=float, default=0.9)
    parser.add_argument("--t-suggest", type=float, default=0.5)
    parser.add_argument(
        "--check", type=int, default=3000, help="rows for the comparison"
    )
    args = parser.parse_args()
    try:
        version = model_version(args.market, args.release)
    except ValueError as e:
        parser.error(str(e))

    model = load(ROOT / "models" / args.name)
    groups = class_groups()
    weights = model.embedding.weight.detach().numpy()
    scales, q = quantize(weights)
    chains, aliases = table()
    exported = ExportedModel(
        version=version,
        created=now(),
        features=model.cfg.features,
        dim=model.cfg.dim,
        temperature=model.cfg.temperature,
        t_sure=args.t_sure,
        t_suggest=args.t_suggest,
        labels=list(model.cfg.labels),
        groups=[groups[label] for label in model.cfg.labels],
        chains=list(chains),
        aliases=list(aliases),
        scales=scales,
        embedding=q,
        output=model.output.weight.detach().numpy().astype(np.float32),
        bias=model.output.bias.detach().numpy().astype(np.float32),
    )
    out = ROOT / "dist" / file_name(version)
    write(exported, out)
    size = out.stat().st_size
    m = read(out)
    print(f"→ {out.relative_to(ROOT)}: {size / 1e6:.2f} MB", file=sys.stderr)
    if size > MAX_BYTES:
        print("⚠ larger than 2 MiB", file=sys.stderr)

    # Rounding: comparison with the float32 model on generated validation rows
    val = (
        pl.read_parquet(DATA)
        .filter(pl.col("split") == "val")
        .sample(args.check, seed=1)
    )
    texts, stores = val["text"].to_list(), val["store"].to_list()
    if not model.cfg.features.store:
        stores = [None] * len(texts)
    full = predict_proba(model, Featurizer(model.cfg.features), texts, stores)
    same, diffs = 0, []
    for i, (text, store) in enumerate(zip(texts, stores, strict=True)):
        p = probabilities(m, text, store)
        if p is None:
            continue
        same += int(p.argmax() == full[i].argmax())
        diffs.append(float(np.abs(p - full[i]).max()))
    print(
        f"rounding: same best class for {same / len(diffs):.2%}, "
        f"largest probability deviation {max(diffs):.4f}",
        file=sys.stderr,
    )

    inputs = golden_inputs() + list(zip(texts[:300], stores[:300], strict=True))
    golden = out.with_suffix(".golden.tsv")
    golden.write_text(model_tsv(m, inputs), encoding="utf-8")
    print(f"→ {golden.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
