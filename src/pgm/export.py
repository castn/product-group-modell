"""File format of the model for the app (step 9) and reference computation without PyTorch.

The format is described in docs/interface.md. All numbers little endian.

    magic          4 B    "PGM1"
    format         u16    version of the format and of the feature rules (2)
    version        str16  model version, e.g. "2026.10-de-1"
    created        i64    Unix time in seconds
    buckets        u32
    dim            u16
    minn, maxn     u8, u8
    flags          u16    bit 0: word pairs, bit 1: store feature
    temperature    f32
    t_sure         f32    from this confidence: SURE
    t_suggest      f32    from this confidence: SUGGESTION, below it null
    n_labels       u16
    labels         n_labels × (str8 class, str8 group)
    n_chains       u16
    chains         n_chains × str8 (normalized chain name)
    n_aliases      u16
    aliases        n_aliases × (str8 alias normalized, u16 index of the chain)
    scales         buckets × f32        scale per row of the feature vectors
    embedding      buckets × dim × i8   feature vectors, value = q × scale
    output         n_labels × dim × f32
    bias           n_labels × f32
    crc32          u32    over all preceding bytes

str8/str16: length as u8/u16, then UTF-8 (always ASCII here).
"""

import io
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pgm.features import FeatureConfig, feature_ids
from pgm.stores import lookup

MAGIC = b"PGM1"
FORMAT = 2


@dataclass
class ExportedModel:
    version: str
    created: int
    features: FeatureConfig
    dim: int
    temperature: float
    t_sure: float
    t_suggest: float
    labels: list[str]
    groups: list[str]
    chains: list[str]
    aliases: list[tuple[str, int]]  # (alias, index in chains), longest first
    scales: np.ndarray  # (buckets,) float32
    embedding: np.ndarray  # (buckets, dim) int8
    output: np.ndarray  # (labels, dim) float32
    bias: np.ndarray  # (labels,) float32


def quantize(embedding: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Round to int8 per row: value ≈ q × scale, scale = max|row| / 127."""
    emb = embedding.astype(np.float32)
    scales = (np.abs(emb).max(axis=1) / 127.0).astype(np.float32)
    safe = np.where(scales > 0, scales, 1.0).astype(np.float32)
    q = np.clip(np.rint(emb / safe[:, None]), -127, 127).astype(np.int8)
    return scales, q


def _str(b: io.BytesIO, s: str, width: str) -> None:
    data = s.encode("utf-8")
    b.write(struct.pack("<" + width, len(data)))
    b.write(data)


def write(m: ExportedModel, path: Path) -> None:
    b = io.BytesIO()
    b.write(MAGIC)
    b.write(struct.pack("<H", FORMAT))
    _str(b, m.version, "H")
    b.write(struct.pack("<q", m.created))
    f = m.features
    flags = (1 if f.bigrams else 0) | (2 if f.store else 0)
    b.write(struct.pack("<IHBBH", f.buckets, m.dim, f.minn, f.maxn, flags))
    b.write(struct.pack("<fff", m.temperature, m.t_sure, m.t_suggest))
    b.write(struct.pack("<H", len(m.labels)))
    for label, group in zip(m.labels, m.groups, strict=True):
        _str(b, label, "B")
        _str(b, group, "B")
    b.write(struct.pack("<H", len(m.chains)))
    for chain in m.chains:
        _str(b, chain, "B")
    b.write(struct.pack("<H", len(m.aliases)))
    for alias, index in m.aliases:
        _str(b, alias, "B")
        b.write(struct.pack("<H", index))
    b.write(m.scales.astype("<f4").tobytes())
    b.write(m.embedding.astype(np.int8).tobytes())
    b.write(m.output.astype("<f4").tobytes())
    b.write(m.bias.astype("<f4").tobytes())
    data = b.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data + struct.pack("<I", zlib.crc32(data)))


def read(path: Path) -> ExportedModel:
    data = path.read_bytes()
    body, (crc,) = data[:-4], struct.unpack("<I", data[-4:])
    if zlib.crc32(body) != crc:
        raise ValueError(f"{path}: CRC does not match")
    r = io.BytesIO(body)

    def unpack(fmt: str):
        size = struct.calcsize("<" + fmt)
        return struct.unpack("<" + fmt, r.read(size))

    def string(width: str) -> str:
        (n,) = unpack(width)
        return r.read(n).decode("utf-8")

    if r.read(4) != MAGIC:
        raise ValueError(f"{path}: not a PGM model")
    (fmt,) = unpack("H")
    if fmt != FORMAT:
        raise ValueError(f"{path}: format {fmt} not supported")
    version = string("H")
    (created,) = unpack("q")
    buckets, dim, minn, maxn, flags = unpack("IHBBH")
    temperature, t_sure, t_suggest = unpack("fff")
    (n_labels,) = unpack("H")
    labels, groups = [], []
    for _ in range(n_labels):
        labels.append(string("B"))
        groups.append(string("B"))
    (n_chains,) = unpack("H")
    chains = [string("B") for _ in range(n_chains)]
    (n_aliases,) = unpack("H")
    aliases = []
    for _ in range(n_aliases):
        alias = string("B")
        (index,) = unpack("H")
        aliases.append((alias, index))
    scales = np.frombuffer(r.read(4 * buckets), dtype="<f4").copy()
    embedding = np.frombuffer(r.read(buckets * dim), dtype=np.int8).reshape(
        buckets, dim
    )
    output = np.frombuffer(r.read(4 * n_labels * dim), dtype="<f4").reshape(
        n_labels, dim
    )
    bias = np.frombuffer(r.read(4 * n_labels), dtype="<f4").copy()
    if r.read(1):
        raise ValueError(f"{path}: data after the end")
    features = FeatureConfig(
        buckets=buckets,
        minn=minn,
        maxn=maxn,
        bigrams=bool(flags & 1),
        store=bool(flags & 2),
    )
    return ExportedModel(
        version, created, features, dim, temperature, t_sure, t_suggest, labels, groups,
        chains, aliases, scales, embedding.copy(), output.copy(), bias,
    )  # fmt: skip


def chain_of(m: ExportedModel, store: str | None) -> str | None:
    """Like pgm.stores.chain_of, but with the table from the model file."""
    return lookup(m.chains, m.aliases, store)


def probabilities(m: ExportedModel, name: str, store: str | None) -> np.ndarray | None:
    """Reference computation per docs/interface.md in float32; None without features."""
    ids = feature_ids(name, chain_of(m, store), m.features)
    if not ids:
        return None
    h = np.zeros(m.dim, dtype=np.float32)
    for i in ids:
        h += m.embedding[i].astype(np.float32) * m.scales[i]
    h /= np.float32(len(ids))
    logits = m.output @ h + m.bias
    z = logits / np.float32(m.temperature)
    z = z - z.max()
    e = np.exp(z, dtype=np.float32)
    return (e / e.sum()).astype(np.float32)


def now() -> int:
    return int(time.time())
