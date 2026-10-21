"""Trains the model and evaluates it.

Input:   data/processed/dataset.parquet (scripts/build_dataset.py)
Output:  models/<name>/ (weights and configuration)
         reports/train-<name>.md

Evaluated on
- the validation set (products that do not occur in training), separately for
  clean names and receipt-style variants,
- the real receipts (data/eval/item-groups.csv), alone and together with the
  app's dictionary: model from a threshold, otherwise dictionary (+ merchant).

The temperature T is chosen on the validation set so that the confidence matches
the hit rate (only roughly here).

Usage:  uv run scripts/train.py --name dev [--dim 24] [--epochs 5] …
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl
import torch
from torch import nn

from pgm.categories import class_groups
from pgm.evaldata import dictionary, fmt, load_receipts, metrics
from pgm.features import FeatureConfig
from pgm.model import FastText, Featurizer, ModelConfig, predict_proba, save
from pgm.stores import chain_of

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed" / "dataset.parquet"
THRESHOLDS = [0.0, 0.5, 0.7, 0.8, 0.9, 0.95]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def featurize_all(featurizer: Featurizer, texts, stores):
    flat, offsets, has = featurizer.batch(texts, stores)
    lengths = np.diff(np.append(offsets, flat.size))
    return flat.astype(np.int32), offsets, lengths, has


def train(args) -> tuple[FastText, Featurizer, pl.DataFrame]:
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    classes = class_groups()
    labels = tuple(classes)
    index = {label: i for i, label in enumerate(labels)}

    df = pl.read_parquet(DATA)
    tr = df.filter(pl.col("split") == "train")
    va = df.filter(pl.col("split") == "val")
    stores_tr = tr["store"].to_list() if args.store else [None] * tr.height

    fcfg = FeatureConfig(
        buckets=args.buckets,
        minn=args.minn,
        maxn=args.maxn,
        bigrams=args.bigrams,
        store=args.store,
    )
    featurizer = Featurizer(fcfg)
    t0 = time.time()
    flat, offsets, lengths, has = featurize_all(
        featurizer, tr["text"].to_list(), stores_tr
    )
    y = np.array([index[label] for label in tr["label"]], dtype=np.int64)
    rows = np.flatnonzero(has)
    log(f"features: {tr.height:,} rows in {time.time() - t0:.0f} s")

    model = FastText(ModelConfig(features=fcfg, dim=args.dim, labels=labels))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.CrossEntropyLoss()
    steps = args.epochs * ((rows.size + args.batch - 1) // args.batch)
    scheduler = torch.optim.lr_scheduler.LinearLR(
        optimizer, 1.0, 0.05, total_iters=steps
    )

    for epoch in range(args.epochs):
        model.train()
        t0 = time.time()
        order = rng.permutation(rows)
        total = 0.0
        for start in range(0, order.size, args.batch):
            batch = order[start : start + args.batch]
            parts = [flat[offsets[i] : offsets[i] + lengths[i]] for i in batch]
            ids = torch.from_numpy(np.concatenate(parts).astype(np.int64))
            offs = torch.from_numpy(
                np.concatenate(([0], np.cumsum(lengths[batch])[:-1]))
            )
            optimizer.zero_grad()
            loss = loss_fn(model(ids, offs), torch.from_numpy(y[batch]))
            loss.backward()
            optimizer.step()
            scheduler.step()
            total += loss.item() * batch.size
        acc = accuracy(model, featurizer, va, args.store, index)
        log(
            f"epoch {epoch + 1}: loss {total / rows.size:.3f}, "
            f"validation {acc:.1%}, {time.time() - t0:.0f} s"
        )
    return model, featurizer, va


def accuracy(model, featurizer, df: pl.DataFrame, use_store: bool, index) -> float:
    stores = df["store"].to_list() if use_store else [None] * df.height
    probs = predict_proba(model, featurizer, df["text"].to_list(), stores)
    y = np.array([index[label] for label in df["label"]])
    return float((probs.argmax(1) == y).mean())


def fit_temperature(
    model, featurizer, va: pl.DataFrame, use_store: bool, index
) -> float:
    """T with the lowest negative log-likelihood on the validation set (grid search)."""
    stores = va["store"].to_list() if use_store else [None] * va.height
    flat, offsets, has = featurizer.batch(va["text"].to_list(), stores)
    y = torch.tensor([index[label] for label in va["label"]])[torch.from_numpy(has)]
    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(flat), torch.from_numpy(offsets))[
            torch.from_numpy(has)
        ]
    best = min(
        (nn.functional.cross_entropy(logits / t, y).item(), t)
        for t in np.arange(0.5, 3.01, 0.05)
    )
    return float(round(best[1], 2))


def report(args, model: FastText, featurizer: Featurizer, va: pl.DataFrame) -> str:
    classes = class_groups()
    labels = model.cfg.labels
    index = {label: i for i, label in enumerate(labels)}
    lines = [f"# Training `{args.name}`", ""]
    lines += [
        f"Parameter: `{vars(args)}`",
        f"Temperature T = {model.cfg.temperature}",
        "",
    ]

    lines += ["## Validation (products missing from training)", ""]
    lines += [
        "| Data | Rows | class correct | group correct |",
        "|---|---:|---:|---:|",
    ]
    for title, part in [
        ("clean names", va.filter(pl.col("clean"))),
        ("receipt style (generated)", va.filter(~pl.col("clean"))),
    ]:
        stores = part["store"].to_list() if args.store else [None] * part.height
        probs = predict_proba(model, featurizer, part["text"].to_list(), stores)
        pred = [labels[i] for i in probs.argmax(1)]
        exp = part["label"].to_list()
        cls_ok = np.mean([p == e for p, e in zip(pred, exp, strict=True)])
        grp_ok = np.mean(
            [classes[p] == classes[e] for p, e in zip(pred, exp, strict=True)]
        )
        lines.append(f"| {title} | {part.height:,} | {cls_ok:.1%} | {grp_ok:.1%} |")

    rec = load_receipts()
    stores = (
        [chain_of(m) for m in rec.merchant] if args.store else [None] * len(rec.name)
    )
    probs = predict_proba(model, featurizer, rec.name, stores)
    best = probs.argmax(1)
    conf = probs.max(1)
    pred_class = [labels[i] for i in best]
    pred_group = [classes[c] for c in pred_class]
    dict_result = dictionary(list(zip(rec.name, rec.merchant, strict=True)))
    dict_only = [g if s == "DICTIONARY" else None for g, s in dict_result]
    dict_merchant = [g for g, _ in dict_result]

    lines += ["", "## Real receipts", ""]
    if rec.label[0] is not None:
        top1 = np.mean([p == e for p, e in zip(pred_class, rec.label, strict=True)])
        top3 = np.mean(
            [
                index[e] in np.argsort(-p)[:3]
                for p, e in zip(probs, rec.label, strict=True)
            ]
        )
        lines += [f"Class correct: {top1:.0%} (among the best three: {top3:.0%})", ""]
    lines += [
        "Comparison at item group level. Coverage = share with a suggestion,",
        "accuracy = share correct among the suggestions.",
        "",
        "| Variant | Rows | with suggestion | correct | Accuracy |",
        "|---|---:|---:|---:|---:|",
        "| Dictionary " + fmt(*metrics(rec.group, dict_only)),
        "| Dictionary + merchant " + fmt(*metrics(rec.group, dict_merchant)),
    ]
    for t in THRESHOLDS:
        model_only = [
            g if c >= t else None for g, c in zip(pred_group, conf, strict=True)
        ]
        lines.append(f"| Model from {t:.2f} " + fmt(*metrics(rec.group, model_only)))
    for t in THRESHOLDS[1:]:
        combined = [
            g if c >= t else d
            for g, c, d in zip(pred_group, conf, dict_merchant, strict=True)
        ]
        lines.append(
            f"| Model from {t:.2f}, else dictionary + merchant "
            + fmt(*metrics(rec.group, combined))
        )

    lines += ["", "### Individual rows", ""]
    lines += [
        "| Receipt | Name | expected | Model | Confidence | Dictionary |",
        "|---|---|---|---|---:|---|",
    ]
    for i, name in enumerate(rec.name):
        expected = rec.label[i] or rec.group[i]
        mark = "" if pred_class[i] == expected or pred_group[i] == expected else " ✗"
        lines.append(
            f"| {rec.receipt[i]} | {name} | {expected} | {pred_class[i]}{mark} "
            f"| {conf[i]:.2f} | {dict_merchant[i] or '–'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="dev")
    parser.add_argument("--dim", type=int, default=24)
    parser.add_argument("--buckets", type=int, default=1 << 16)
    parser.add_argument("--minn", type=int, default=2)
    parser.add_argument("--maxn", type=int, default=5)
    parser.add_argument(
        "--bigrams", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--store", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    torch.set_num_threads(8)
    model, featurizer, va = train(args)
    index = {label: i for i, label in enumerate(model.cfg.labels)}
    temperature = fit_temperature(model, featurizer, va, args.store, index)
    model.cfg = ModelConfig(
        features=model.cfg.features,
        dim=model.cfg.dim,
        labels=model.cfg.labels,
        temperature=temperature,
    )
    save(model, ROOT / "models" / args.name)
    out = ROOT / "reports" / f"train-{args.name}.md"
    out.write_text(report(args, model, featurizer, va))
    log(f"→ models/{args.name}/, {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
