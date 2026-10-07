"""Golden values for checking the Kotlin implementation.

tests/golden/normalize.tsv is written by hand (specification).
tests/golden/features.tsv is generated here from the Python implementation;
tests/test_golden.py checks that the file is up to date.

Format: tab-separated, escapes \\t \\n \\\\ as in normalize.tsv.
"""

from pathlib import Path

from pgm.features import FeatureConfig, feature_ids

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
    inputs = [(raw, None) for raw, _ in normalize_cases()] + EXTRA
    lines = [
        "# config\tname\tstore (empty = null)\tids (comma-separated)",
        "# configs: " + "; ".join(f"{k}={v}" for k, v in CONFIGS.items()),
    ]
    for config_name, cfg in CONFIGS.items():
        for name, store in inputs:
            ids = ",".join(str(i) for i in feature_ids(name, store, cfg))
            lines.append(f"{config_name}\t{escape(name)}\t{escape(store or '')}\t{ids}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    (GOLDEN / "features.tsv").write_text(features_tsv(), encoding="utf-8")
