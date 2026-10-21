"""Generates receipt-style lines from clean product names.

Tills print abbreviated names in upper case with private label and quantity, and
text recognition confuses characters and spaces. Each transformation has a
probability in AugmentConfig, so that its influence can be measured.

Work is done on the normalized name (pgm.normalize): upper and lower case,
umlauts and accents do not matter to the model anyway.
"""

import random
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pgm.normalize import normalize

AUGMENT = Path(__file__).resolve().parent.parent.parent / "augment"

FILLER = {
    "MIT",
    "UND",
    "DER",
    "DIE",
    "DAS",
    "IN",
    "AUS",
    "VON",
    "AM",
    "IM",
    "&",
    "A",
    "LA",
    "DE",
}
VOWELS = set("AEIOU")
# Text recognition confusions, in both directions
OCR_SWAPS = [
    ("O", "0"),
    ("I", "1"),
    ("L", "1"),
    ("S", "5"),
    ("B", "8"),
    ("E", "F"),
    ("U", "V"),
    ("G", "6"),
    ("Z", "2"),
    ("C", "E"),
    ("N", "M"),
    ("H", "N"),
]
UNITS = ["G", "KG", "ML", "L", "ST", "STK"]


@dataclass(frozen=True)
class AugmentConfig:
    brand: float = 0.25  # prepend brand
    private_label: float = 0.25  # prepend the chain's private label
    filler: float = 0.6  # per filler word: drop
    abbrev: float = 0.5  # per word from the abbreviation list
    truncate_word: float = 0.3  # per long word: shorten
    drop_vowels: float = 0.08  # per word: drop vowels
    join_dots: float = 0.1  # join words with a dot ("GRUENL.SCH.")
    quantity: float = 0.35  # append quantity
    price_tail: float = 0.2  # append remnant of weight, count and price
    truncate_line: float = 0.5  # cut to line width
    ocr_char: float = 0.012  # per character: confusion
    ocr_space: float = 0.08  # insert or delete a space


DEFAULT_CONFIG = AugmentConfig()


@cache
def _private_labels() -> dict[str, list[tuple[str, frozenset[str]]]]:
    result: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for line in (
        (AUGMENT / "private_labels.tsv").read_text(encoding="utf-8").splitlines()
    ):
        if not line or line.startswith("#"):
            continue
        chain, label, classes = (line.split("\t") + [""])[:3]
        allowed = frozenset(c for c in classes.split(",") if c)
        result.setdefault(chain, []).append((normalize(label), allowed))
    return result


@cache
def _abbreviations() -> dict[str, list[str]]:
    result = {}
    for line in (AUGMENT / "abbrev_de.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            word, abbrevs = line.split("\t")
            result[normalize(word)] = abbrevs.split(",")
    return result


# Non-food classes; private labels without a class list apply to all other (food) classes
NON_FOOD = {
    "tabak",
    "koerperpflege",
    "gesundheit",
    "putz_waschmittel",
    "haushaltswaren",
    "tierbedarf",
    "baby",
    "non_food",
}

_QUANTITY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KG|G|ML|CL|L|STK|ST|STUECK)\b")


def receipt_quantity(quantity: str | None, rng: random.Random) -> str:
    """Receipt-style quantity ("500G", "1,5L", "6X0,33L") from the quantity field or random."""
    if quantity:
        m = _QUANTITY.search(normalize(quantity))
        if m:
            number, unit = m.groups()
            return f"{number}{'ST' if unit.startswith('ST') else unit}"
    number = rng.choice(
        ["100", "125", "150", "200", "250", "400", "500", "750", "1", "1,5", "6X0,5"]
    )
    unit = rng.choice(UNITS)
    return f"{number}{unit}"


def _price(rng: random.Random) -> str:
    euros = rng.choice([0, 0, 1, 1, 2, 3, 4, 5, 9])
    cents = f"{rng.randrange(100):02d}"
    sep = rng.choice([",", ",", ", ", "."])  # text recognition: "0, 99"
    return f"{euros}{sep}{cents}"


def price_tail(rng: random.Random) -> str:
    """Remnants the receipt parser leaves on the name (weight, count, price)."""
    n = rng.randint(2, 6)
    weight = f"0,{rng.randint(100, 999)}"
    patterns = [
        f"{weight} kg x {_price(rng)} EUR/kg",
        f"{weight} kg x {_price(rng)} EUR/kg X",
        f"{_price(rng)} € x {n}",
        f"{_price(rng)} € X {n}",
        f"{n} x €{_price(rng)} €",
        f"1,00 Stück x {_price(rng)}",
        f"{n} Stk x {_price(rng)}",
        f"{_price(rng)} AW",
        f"{_price(rng)} A",
        "EUR",
        f"{rng.randint(100000, 999999)} 1 {_price(rng)}",
    ]
    return rng.choice(patterns)


def _shorten(word: str, rng: random.Random, cfg: AugmentConfig) -> str:
    if len(word) < 4 or word.isdigit():
        return word
    abbrevs = _abbreviations().get(word.rstrip("."))
    if abbrevs and rng.random() < cfg.abbrev:
        return rng.choice(abbrevs)
    if len(word) > 6 and rng.random() < cfg.truncate_word:
        cut = word[: rng.randint(3, min(8, len(word) - 1))]
        return cut + "." if rng.random() < 0.5 else cut
    if len(word) > 4 and rng.random() < cfg.drop_vowels:
        return word[0] + "".join(c for c in word[1:] if c not in VOWELS)
    return word


def _ocr(text: str, rng: random.Random, cfg: AugmentConfig) -> str:
    chars = list(text)
    for i, c in enumerate(chars):
        if rng.random() < cfg.ocr_char:
            options = [b for a, b in OCR_SWAPS if a == c] + [
                a for a, b in OCR_SWAPS if b == c
            ]
            if options:
                chars[i] = rng.choice(options)
    text = "".join(chars)
    if rng.random() < cfg.ocr_space and len(text) > 4:
        # space in the middle of a word ("SPITZPAPR IKA")
        i = rng.randint(2, len(text) - 2)
        text = text[:i] + " " + text[i:]
    if rng.random() < cfg.ocr_space and " " in text:
        # missing space ("STRUDELMIT")
        spaces = [i for i, c in enumerate(text) if c == " "]
        i = rng.choice(spaces)
        text = text[:i] + text[i + 1 :]
    return text


def augment(
    name: str,
    label: str,
    rng: random.Random,
    *,
    brand: str | None = None,
    quantity: str | None = None,
    chain: str | None = None,
    cfg: AugmentConfig | None = None,
) -> str:
    cfg = cfg or DEFAULT_CONFIG
    tokens = normalize(name).split()
    if not tokens:
        return ""

    prefix = None
    labels = [
        lbl
        for lbl, allowed in _private_labels().get(chain or "", [])
        if (label in allowed if allowed else label not in NON_FOOD)
    ]
    if labels and rng.random() < cfg.private_label:
        prefix = rng.choice(labels)
    elif brand and rng.random() < cfg.brand:
        brand_norm = normalize(brand.split(",")[0])
        if brand_norm and brand_norm.split()[0] not in tokens:
            prefix = brand_norm[: rng.randint(3, 10)].strip()

    tokens = [
        t for t in tokens if not (t in FILLER and rng.random() < cfg.filler)
    ] or tokens
    tokens = [_shorten(t, rng, cfg) for t in tokens]
    if prefix:
        tokens.insert(0, prefix)

    if len(tokens) > 1 and rng.random() < cfg.join_dots:
        i = rng.randrange(len(tokens) - 1)
        left = tokens[i] if tokens[i].endswith(".") else tokens[i] + "."
        tokens[i : i + 2] = [left + tokens[i + 1]]

    text = " ".join(tokens)
    if rng.random() < cfg.quantity:
        text = f"{text} {receipt_quantity(quantity, rng)}"
    if rng.random() < cfg.truncate_line:
        text = text[: rng.randint(14, 30)].rstrip()
    if rng.random() < cfg.price_tail:
        text = f"{text} {price_tail(rng)}"
    return _ocr(text, rng, cfg)
