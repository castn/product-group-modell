import json

import pytest

from pgm.categories import CategoryMapper, Taxonomy

GROUPS = ["produce", "pantry", "drugstore"]


@pytest.fixture
def taxonomy(tmp_path):
    #   food ─┬─ fruits ─── apples
    #         ├─ jams ───── apple-jams (also under fruits)
    #         └─ meals
    path = tmp_path / "tax.json"
    path.write_text(
        json.dumps(
            {
                "en:food": {},
                "en:fruits": {"parents": ["en:food"]},
                "en:apples": {"parents": ["en:fruits"]},
                "en:jams": {"parents": ["en:food"]},
                "en:apple-jams": {"parents": ["en:jams", "en:fruits"]},
                "en:meals": {"parents": ["en:food"]},
            }
        )
    )
    return Taxonomy(path)


def test_most_specific_wins(taxonomy):
    m = CategoryMapper({"en:food": "pantry", "en:fruits": "produce"}, taxonomy, GROUPS)
    assert m.resolve(["en:apples"]).group == "produce"


def test_conflict_between_branches(taxonomy):
    m = CategoryMapper({"en:fruits": "produce", "en:jams": "pantry"}, taxonomy, GROUPS)
    res = m.resolve(["en:apple-jams"])
    assert (res.group, res.reason) == (None, "conflict")
    assert res.tags == ("en:fruits", "en:jams")


def test_weak_yields_to_strong(taxonomy):
    m = CategoryMapper({"en:fruits": "~produce", "en:jams": "pantry"}, taxonomy, GROUPS)
    assert m.resolve(["en:apple-jams"]).group == "pantry"
    assert m.resolve(["en:apples"]).group == "produce"


def test_specific_entry_resolves_conflict(taxonomy):
    m = CategoryMapper(
        {"en:fruits": "produce", "en:jams": "pantry", "en:apple-jams": "pantry"},
        taxonomy,
        GROUPS,
    )
    assert m.resolve(["en:apple-jams"]).group == "pantry"


def test_null_ignored_drop_and_default(taxonomy):
    m = CategoryMapper(
        {"_default": "drugstore", "en:food": None, "en:meals": "_drop"},
        taxonomy,
        GROUPS,
    )
    assert m.resolve(["en:apples"]).reason == "default"
    assert m.resolve(["en:meals"]).reason == "drop"


def test_unknown_group_rejected(taxonomy):
    with pytest.raises(ValueError, match="unknown groups"):
        CategoryMapper({"en:food": "lebensmittel"}, taxonomy, GROUPS)
