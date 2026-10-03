from pathlib import Path

import pytest

from pgm.normalize import normalize

GOLDEN = Path(__file__).parent / "golden" / "normalize.tsv"


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append({"t": "\t", "n": "\n", "\\": "\\"}[s[i + 1]])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _cases():
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        raw, expected = line.split("\t")
        yield _unescape(raw), _unescape(expected)


@pytest.mark.parametrize(("raw", "expected"), list(_cases()))
def test_golden(raw, expected):
    assert normalize(raw) == expected


def test_idempotent():
    for raw, _ in _cases():
        once = normalize(raw)
        assert normalize(once) == once
