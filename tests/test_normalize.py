import pytest

from pgm.golden import normalize_cases
from pgm.normalize import normalize


@pytest.mark.parametrize(("raw", "expected"), normalize_cases())
def test_golden(raw, expected):
    assert normalize(raw) == expected


def test_idempotent():
    for raw, _ in normalize_cases():
        once = normalize(raw)
        assert normalize(once) == once
