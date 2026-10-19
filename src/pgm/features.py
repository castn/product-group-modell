"""fastText-style features: words, character n-grams, word pairs, store.

Each feature is a string that is mapped to a bucket via FNV-1a (32 bit) over
its UTF-8 bytes. The specification is in docs/interface.md.
"""

from dataclasses import dataclass
from itertools import pairwise

from pgm.normalize import normalize

FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193


def fnv1a32(data: bytes) -> int:
    h = FNV_OFFSET
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return h


@dataclass(frozen=True)
class FeatureConfig:
    buckets: int = 1 << 16
    minn: int = 2
    maxn: int = 5
    bigrams: bool = True
    store: bool = True


# Units, price and tax markers that the receipt parser leaves on the name
# ("BANANE 0,750 KG X 1,79 EUR KG", "BREZE 4 X 0,39"). They say nothing about the
# item group but dilute the mean of the features.
SKIP_TOKENS = frozenset(
    {"X", "KG", "G", "L", "ML", "EUR", "ST", "STK", "STUECK", "AW", "A", "B"}
)
_NUMERIC = frozenset("0123456789,.%-")


def tokens(name: str) -> list[str]:
    """Words of the normalized name without pure numbers and without SKIP_TOKENS."""
    return [
        t
        for t in normalize(name).split()
        if t not in SKIP_TOKENS and not set(t) <= _NUMERIC
    ]


def feature_strings(name: str, store: str | None, cfg: FeatureConfig) -> list[str]:
    """Features in a fixed order. Duplicates are not removed (like fastText)."""
    tokens_ = tokens(name)
    features: list[str] = []
    for token in tokens_:
        word = f"<{token}>"
        features.append(word)
        for n in range(cfg.minn, cfg.maxn + 1):
            for i in range(len(word) - n + 1):
                gram = word[i : i + n]
                if gram != word:
                    features.append(gram)
    if cfg.bigrams:
        features.extend(f"{a} {b}" for a, b in pairwise(tokens_))
    if cfg.store and store and tokens_:
        store_norm = normalize(store)
        if store_norm:
            features.append(f"__store={store_norm}")
    return features


def feature_ids(name: str, store: str | None, cfg: FeatureConfig) -> list[int]:
    return [
        fnv1a32(f.encode("utf-8")) % cfg.buckets
        for f in feature_strings(name, store, cfg)
    ]
