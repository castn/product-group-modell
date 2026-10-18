"""Evaluates a model on the real receipts (steps 7 and 8).

Input:   models/<name>/ (scripts/train.py), data/eval/receipts.csv
Output:  reports/eval-<name>.md (contains rows of the test data, do not commit)

Compared at the level of the app's item group, each for all rows and only for
the receipts the dictionary does not know (dictionary_seen = nein):
- the app's dictionary alone and with the merchant as fallback,
- the model alone from various thresholds,
- two orders in the app: model → dictionary → merchant and
  dictionary → model → merchant.

Coverage = share with a suggestion, accuracy = share correct among the suggestions.

Usage:  uv run scripts/evaluate.py --name dev2
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from pgm.categories import class_groups
from pgm.evaldata import Receipts, dictionary, fmt, load_receipts, metrics
from pgm.model import Featurizer, load, predict_proba
from pgm.stores import chain_of

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS = [0.0, 0.3, 0.5, 0.7, 0.9]


def table(rec: Receipts, probs: np.ndarray, labels, dict_result) -> list[str]:
    classes = class_groups()
    conf = probs.max(1)
    pred_class = [labels[i] for i in probs.argmax(1)]
    pred_group = [classes[c] for c in pred_class]
    has = probs.sum(1) > 0
    dict_only = [g if s == "DICTIONARY" else None for g, s in dict_result]
    merchant = [g if s == "MERCHANT" else None for g, s in dict_result]

    def model_at(t):
        return [
            g if h and c >= t else None
            for g, c, h in zip(pred_group, conf, has, strict=True)
        ]

    def chain(*sources):
        return [next((x for x in xs if x), None) for xs in zip(*sources, strict=True)]

    lines = [
        "| Variant | Rows | with suggestion | correct | Accuracy |",
        "|---|---:|---:|---:|---:|",
        "| Dictionary " + fmt(*metrics(rec.group, dict_only)),
        "| Dictionary → merchant "
        + fmt(*metrics(rec.group, chain(dict_only, merchant))),
    ]
    for t in THRESHOLDS:
        lines.append(f"| Model from {t:.1f} " + fmt(*metrics(rec.group, model_at(t))))
    for t in THRESHOLDS:
        lines.append(
            f"| Model from {t:.1f} → dictionary → merchant "
            + fmt(*metrics(rec.group, chain(model_at(t), dict_only, merchant)))
        )
    for t in THRESHOLDS:
        lines.append(
            f"| Dictionary → model from {t:.1f} → merchant "
            + fmt(*metrics(rec.group, chain(dict_only, model_at(t), merchant)))
        )
    if rec.label and rec.label[0] is not None:
        top1 = np.mean([p == e for p, e in zip(pred_class, rec.label, strict=True)])
        index = {label: i for i, label in enumerate(labels)}
        top3 = np.mean(
            [
                index[e] in np.argsort(-p)[:3]
                for p, e in zip(probs, rec.label, strict=True)
            ]
        )
        lines += [
            "",
            f"Model, class correct: {top1:.0%}, among the best three: {top3:.0%}",
        ]
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    model = load(ROOT / "models" / args.name)
    labels = model.cfg.labels
    classes = class_groups()
    rec = load_receipts()
    stores = [chain_of(m) for m in rec.merchant]
    if not model.cfg.features.store:
        stores = [None] * len(stores)
    probs = predict_proba(model, Featurizer(model.cfg.features), rec.name, stores)
    dict_result = dictionary(list(zip(rec.name, rec.merchant, strict=True)))

    lines = [f"# Evaluation of `{args.name}` on real receipts", ""]
    new = [not s for s in rec.seen]
    for title, mask in [
        ("New receipts only (the dictionary does not know them)", new),
        ("All receipts", [True] * len(new)),
    ]:
        sub = rec.subset(mask)
        idx = np.flatnonzero(mask)
        n_receipts = len(set(sub.receipt))
        lines += ["", f"## {title}: {len(sub.name)} rows, {n_receipts} receipts", ""]
        lines += table(sub, probs[idx], labels, [dict_result[i] for i in idx])

    lines += ["", "## Rows where the model or the dictionary is wrong", ""]
    lines += [
        "| Receipt | new | Name | expected | Model | Confidence | Dictionary |",
        "|---|---|---|---|---|---:|---|",
    ]
    for i, name in enumerate(rec.name):
        c = labels[int(probs[i].argmax())]
        g, s = dict_result[i]
        if classes[c] == rec.group[i] and g == rec.group[i]:
            continue
        mark = "" if classes[c] == rec.group[i] else " ✗"
        dmark = "" if g == rec.group[i] or g is None else " ✗"
        lines.append(
            f"| {rec.receipt[i]} | {'' if rec.seen[i] else 'yes'} | {name} "
            f"| {rec.label[i] or rec.group[i]} | {c}{mark} | {probs[i].max():.2f} "
            f"| {g or '–'}{dmark} ({s or '–'}) |"
        )
    out = ROOT / "reports" / f"eval-{args.name}.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"→ {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
