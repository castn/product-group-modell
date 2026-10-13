"""fastText-style model: averaged feature vectors, one linear layer.

The computation is deliberately simple enough to be rebuilt in Kotlin without
libraries (docs/interface.md, section Computation):

    h      = mean of the rows of E for the feature IDs           (dim)
    logits = W · h + b                                            (classes)
    p      = softmax(logits / T)
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from pgm.features import FeatureConfig, feature_strings, fnv1a32


@dataclass(frozen=True)
class ModelConfig:
    features: FeatureConfig
    dim: int
    labels: tuple[str, ...]
    temperature: float = 1.0


class FastText(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.embedding = nn.EmbeddingBag(cfg.features.buckets, cfg.dim, mode="mean")
        self.output = nn.Linear(cfg.dim, len(cfg.labels))
        nn.init.uniform_(self.embedding.weight, -1.0 / cfg.dim, 1.0 / cfg.dim)
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    def forward(self, ids: torch.Tensor, offsets: torch.Tensor) -> torch.Tensor:
        return self.output(self.embedding(ids, offsets))


class Featurizer:
    """Feature IDs with a cache per feature; many character n-grams repeat."""

    def __init__(self, cfg: FeatureConfig):
        self.cfg = cfg
        self._cache: dict[str, int] = {}

    def ids(self, text: str, store: str | None) -> list[int]:
        result = []
        for f in feature_strings(text, store, self.cfg):
            i = self._cache.get(f)
            if i is None:
                i = fnv1a32(f.encode("utf-8")) % self.cfg.buckets
                self._cache[f] = i
            result.append(i)
        return result

    def batch(self, texts, stores) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Flat ID list, offsets and mask of the rows with at least one feature."""
        flat: list[int] = []
        offsets = []
        has = []
        for text, store in zip(texts, stores, strict=True):
            ids = self.ids(text, store)
            offsets.append(len(flat))
            flat.extend(ids)
            has.append(bool(ids))
        return (
            np.asarray(flat, dtype=np.int64),
            np.asarray(offsets, dtype=np.int64),
            np.asarray(has, dtype=bool),
        )


def predict_proba(
    model: FastText, featurizer: Featurizer, texts, stores, batch_size: int = 4096
) -> np.ndarray:
    """Probabilities per class; rows without features get all zeros."""
    model.eval()
    out = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            t = texts[start : start + batch_size]
            s = stores[start : start + batch_size]
            flat, offsets, has = featurizer.batch(t, s)
            probs = np.zeros((len(t), len(model.cfg.labels)), dtype=np.float32)
            if flat.size:
                logits = model(torch.from_numpy(flat), torch.from_numpy(offsets))
                p = torch.softmax(logits / model.cfg.temperature, dim=1).numpy()
                probs[has] = p[has]
            out.append(probs)
    return np.concatenate(out) if out else np.zeros((0, len(model.cfg.labels)))


def save(model: FastText, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path / "weights.pt")
    cfg = asdict(model.cfg)
    (path / "config.json").write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    )


def load(path: Path) -> FastText:
    raw = json.loads((path / "config.json").read_text())
    cfg = ModelConfig(
        features=FeatureConfig(**raw["features"]),
        dim=raw["dim"],
        labels=tuple(raw["labels"]),
        temperature=raw["temperature"],
    )
    model = FastText(cfg)
    model.load_state_dict(torch.load(path / "weights.pt"))
    return model
