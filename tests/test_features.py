from pgm.features import FeatureConfig, feature_ids, feature_strings, fnv1a32


def test_fnv1a32_reference_vectors():
    # Test vectors from the FNV reference (http://www.isthe.com/chongo/tech/comp/fnv/)
    assert fnv1a32(b"") == 0x811C9DC5
    assert fnv1a32(b"a") == 0xE40C292C
    assert fnv1a32(b"foobar") == 0xBF9CF968


def test_feature_strings_order():
    cfg = FeatureConfig(minn=2, maxn=3, bigrams=True, store=True)
    assert feature_strings("Ja! Eis", "Rewe", cfg) == [
        "<JA!>",
        "<J",
        "JA",
        "A!",
        "!>",
        "<JA",
        "JA!",
        "A!>",
        "<EIS>",
        "<E",
        "EI",
        "IS",
        "S>",
        "<EI",
        "EIS",
        "IS>",
        "JA! EIS",
        "__store=REWE",
    ]


def test_full_word_not_repeated_as_ngram():
    cfg = FeatureConfig(minn=2, maxn=5, bigrams=False, store=False)
    assert feature_strings("Ei", None, cfg) == ["<EI>", "<E", "EI", "I>", "<EI", "EI>"]


def test_empty_name_has_no_features():
    cfg = FeatureConfig()
    assert feature_strings("🍓", "Rewe", cfg) == []
    assert feature_ids("", None, cfg) == []


def test_ids_in_range():
    cfg = FeatureConfig(buckets=1000)
    assert all(0 <= i < 1000 for i in feature_ids("Bio Vollmilch 3,5% 1L", "Lidl", cfg))
