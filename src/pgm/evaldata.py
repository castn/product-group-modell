"""Shared building blocks of the evaluation: real receipts and the app's dictionary."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from pgm.categories import class_groups

ROOT = Path(__file__).resolve().parent.parent.parent
DICTIONARY_BIN = (
    ROOT / "kotlin" / "baseline" / "build" / "install" / "baseline" / "bin" / "baseline"
)
RECEIPTS = ROOT / "data" / "eval" / "receipts.csv"

# Merchants of the receipts whose photo is cropped to the items (as in the app's test)
MERCHANTS = {
    "dm": "dm-drogerie markt",
    "metzger": "Metzgerei",
    "baecker": "Bäckerei",
    "baumarkt": "Baumarkt",
}
# Discount lines: assigned to the item above by a rule in the app, not the model's task
DISCOUNTS = {"Preisänderung", "Feigen 1 Euro"}


@dataclass
class Receipts:
    receipt: list[str]
    name: list[str]
    merchant: list[str]
    label: list[str | None]  # class, None for old files with group only
    group: list[str]
    # receipts that the app's dictionary was written with an eye on
    seen: list[bool]

    def subset(self, mask: list[bool]) -> "Receipts":
        def pick(values):
            return [v for v, m in zip(values, mask, strict=True) if m]

        return Receipts(*(pick(getattr(self, f)) for f in self.__dataclass_fields__))


def load_receipts(path: Path = RECEIPTS) -> Receipts:
    """Real receipts without discount lines and without unclear class ("?").

    Format receipt;merchant;name;amount;class;dictionary_seen (data/eval/receipts.csv).
    Older files receipt;name;class or receipt;name;group work too.
    """
    df = pl.read_csv(path, separator=";", infer_schema_length=0)
    if "amount" in df.columns:
        df = df.filter(
            pl.col("amount").is_null() | (pl.col("amount").cast(pl.Int64) >= 0)
        )
    df = df.filter(~pl.col("name").is_in(DISCOUNTS))
    if "class" in df.columns:
        df = df.filter(pl.col("class") != "?")
        groups = class_groups()
        labels = df["class"].to_list()
        group = [groups[c] for c in labels]
    else:
        labels = [None] * df.height
        group = df["group"].to_list()
    receipts = df["receipt"].to_list()
    if "merchant" in df.columns:
        merchants = df["merchant"].to_list()
    else:
        merchants = [MERCHANTS.get(r, r) for r in receipts]
    if "dictionary_seen" in df.columns:
        seen = [v == "ja" for v in df["dictionary_seen"]]
    else:
        seen = [True] * df.height
    return Receipts(receipts, df["name"].to_list(), merchants, labels, group, seen)


def dictionary(
    rows: list[tuple[str, str | None]],
) -> list[tuple[str | None, str | None]]:
    """Group and source per the app's ItemGroupClassifier (without learned products)."""
    if not DICTIONARY_BIN.exists():
        raise SystemExit("first: cd kotlin && ./gradlew :baseline:installDist")
    data = "".join(
        f"{name.replace(chr(9), ' ').replace(chr(10), ' ')}\t{merchant or ''}\n"
        for name, merchant in rows
    )
    out = subprocess.run(
        [str(DICTIONARY_BIN)], input=data, capture_output=True, text=True, check=True
    ).stdout
    result = []
    for line in out.splitlines():
        group, source = line.split("\t")
        result.append((group or None, source or None))
    assert len(result) == len(rows)
    return result


def metrics(expected: list, predicted: list) -> tuple[int, int, int]:
    total = len(expected)
    assigned = sum(p is not None for p in predicted)
    correct = sum(p == e for p, e in zip(predicted, expected, strict=True))
    return total, assigned, correct


def fmt(total: int, assigned: int, correct: int) -> str:
    """Table cells: rows | with suggestion (coverage) | correct | accuracy |"""
    cov = 100 * assigned / total if total else 0
    acc = 100 * correct / assigned if assigned else 0
    return f"| {total:,} | {assigned:,} ({cov:.0f} %) | {correct:,} | {acc:.0f} % |"
