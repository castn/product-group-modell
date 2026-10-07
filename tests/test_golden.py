from pgm.golden import GOLDEN, features_tsv


def test_features_golden_is_current():
    expected = features_tsv()
    actual = (GOLDEN / "features.tsv").read_text(encoding="utf-8")
    assert actual == expected, "run uv run python -m pgm.golden"
