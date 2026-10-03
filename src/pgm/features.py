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


def feature_strings(name: str, store: str | None, cfg: FeatureConfig) -> list[str]:
    """Features in a fixed order. Duplicates are not removed (like fastText)."""
    tokens = normalize(name).split()
    features: list[str] = []
    for token in tokens:
        word = f"<{token}>"
        features.append(word)
        for n in range(cfg.minn, cfg.maxn + 1):
            for i in range(len(word) - n + 1):
                gram = word[i : i + n]
                if gram != word:
                    features.append(gram)
    if cfg.bigrams:
        features.extend(f"{a} {b}" for a, b in pairwise(tokens))
    if cfg.store and store and tokens:
        store_norm = normalize(store)
        if store_norm:
            features.append(f"__store={store_norm}")
    return features


def feature_ids(name: str, store: str | None, cfg: FeatureConfig) -> list[int]:
    return [
        fnv1a32(f.encode("utf-8")) % cfg.buckets
        for f in feature_strings(name, store, cfg)
    ]
