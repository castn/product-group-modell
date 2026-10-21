"""Golden values for checking the Kotlin implementation.

tests/golden/normalize.tsv is written by hand (specification).
tests/golden/features.tsv is generated here from the Python implementation;
tests/test_golden.py checks that the file is up to date.

tests/golden/tiny.bin is a small model with random weights (no data
from Open Food Facts) in the app's format, tests/golden/tiny.tsv the predictions
of the reference computation for it. For real models, scripts/export.py writes
such a file next to the .bin.

Format: tab-separated, escapes \\t \\n \\\\ as in normalize.tsv.
"""

from pathlib import Path

import numpy as np

from pgm.export import ExportedModel, chain_of, probabilities, quantize, read, write
from pgm.features import FeatureConfig, feature_ids
from pgm.stores import table

GOLDEN = Path(__file__).resolve().parent.parent.parent / "tests" / "golden"

CONFIGS = {
    "default": FeatureConfig(),
    "small": FeatureConfig(buckets=1000, minn=3, maxn=4, bigrams=False, store=False),
}

# Receipt-style names in addition to the inputs from normalize.tsv.
# Made up, not taken from the test data (data/eval).
EXTRA = [
    ("JA! H-MILCH 1,5% 1L", "REWE Markt GmbH"),
    ("K-CLASSIC TOIL.PAP. 8X", "Kaufland"),
    ("dmBio Chiasamen 200g", "dm-drogerie markt"),
    ("Balea Duschgel Kokos 300m1", "dm"),
    ("RIESL.QBA TROCK.0,75L", None),
    ("Kart offeln festk. 2,5KG", "ALDI SÜD"),
    ("G&G ROTE L1NSEN", "Edeka"),
    ("Brot Krusti 500g", ""),
]


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append({"t": "\t", "n": "\n", "\\": "\\"}[s[i + 1]])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def normalize_cases() -> list[tuple[str, str]]:
    rows = []
    for line in (GOLDEN / "normalize.tsv").read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            raw, expected = line.split("\t")
            rows.append((unescape(raw), unescape(expected)))
    return rows


def features_tsv() -> str:
    inputs = golden_inputs()
    lines = [
        "# config\tname\tstore (empty = null)\tids (comma-separated)",
        "# configs: " + "; ".join(f"{k}={v}" for k, v in CONFIGS.items()),
    ]
    for config_name, cfg in CONFIGS.items():
        for name, store in inputs:
            ids = ",".join(str(i) for i in feature_ids(name, store, cfg))
            lines.append(f"{config_name}\t{escape(name)}\t{escape(store or '')}\t{ids}")
    return "\n".join(lines) + "\n"


def model_tsv(
    m: ExportedModel, inputs: list[tuple[str, str | None]], k: int = 3
) -> str:
    """Expected predictions: store → chain, best k classes with probability.

    The margin column is the gap between the best two probabilities. With a very
    small gap, rounding can change the order; tests therefore check the order only
    from margin >= 1e-4, the values always with a tolerance.
    """
    header = (
        f"# model {m.version}; columns: name, store (empty = null), chain, "
        "margin, k × class=probability (empty if no features)"
    )
    lines = [header]
    for name, store in inputs:
        p = probabilities(m, name, store)
        chain = chain_of(m, store) or ""
        if p is None:
            lines.append(f"{escape(name)}\t{escape(store or '')}\t{chain}\t\t")
            continue
        order = np.argsort(-p, kind="stable")[:k]
        margin = float(p[order[0]] - p[order[1]]) if len(order) > 1 else 1.0
        top = ",".join(f"{m.labels[i]}={p[i]:.8f}" for i in order)
        lines.append(
            f"{escape(name)}\t{escape(store or '')}\t{chain}\t{margin:.8f}\t{top}"
        )
    return "\n".join(lines) + "\n"


def tiny_model() -> ExportedModel:
    """Small, deterministic model with random weights for the tests."""
    rng = np.random.default_rng(0)
    features = FeatureConfig(buckets=2048, minn=2, maxn=4, bigrams=True, store=True)
    dim = 8
    labels = [
        "obst",
        "gemuese",
        "kaese",
        "milch_sahne",
        "putz_waschmittel",
        "wein_sekt",
    ]
    groups = ["produce", "produce", "dairy", "dairy", "household", "alcohol"]
    scales, q = quantize(rng.normal(0, 0.5, (features.buckets, dim)))
    scales[7] = 0.0  # row of all zeros, as for unused buckets
    q[7] = 0
    chains, aliases = table()
    return ExportedModel(
        version="tiny-1",
        created=0,
        features=features,
        dim=dim,
        temperature=1.3,
        t_sure=0.9,
        t_suggest=0.5,
        labels=labels,
        groups=groups,
        chains=list(chains),
        aliases=list(aliases),
        scales=scales,
        embedding=q,
        output=rng.normal(0, 1.0, (len(labels), dim)).astype(np.float32),
        bias=rng.normal(0, 0.1, len(labels)).astype(np.float32),
    )


def golden_inputs() -> list[tuple[str, str | None]]:
    return [(raw, None) for raw, _ in normalize_cases()] + EXTRA


if __name__ == "__main__":
    (GOLDEN / "features.tsv").write_text(features_tsv(), encoding="utf-8")
    write(tiny_model(), GOLDEN / "tiny.bin")
    tiny = read(GOLDEN / "tiny.bin")
    (GOLDEN / "tiny.tsv").write_text(model_tsv(tiny, golden_inputs()), encoding="utf-8")
