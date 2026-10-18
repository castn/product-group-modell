import random

from pgm.augment import AugmentConfig, augment, receipt_quantity
from pgm.normalize import normalize
from pgm.stores import chain_of

OFF = AugmentConfig(
    brand=0, private_label=0, filler=0, abbrev=0, truncate_word=0, drop_vowels=0,
    join_dots=0, quantity=0, price_tail=0, truncate_line=0, ocr_char=0,
    ocr_space=0,
)  # fmt: skip


def test_everything_off_gives_normalized_name():
    rng = random.Random(0)
    assert augment("Bio Vollmilch 3,5%", "milch_sahne", rng, cfg=OFF) == normalize(
        "Bio Vollmilch 3,5%"
    )


def test_deterministic_for_same_seed():
    def run():
        rng = random.Random(42)
        return [
            augment("Haferflocken kernig", "muesli_flocken", rng) for _ in range(20)
        ]

    assert run() == run()


def test_private_label_only_for_fitting_class():
    cfg = AugmentConfig(**{**OFF.__dict__, "private_label": 1.0})
    rng = random.Random(0)
    # Balea (dm) only for personal care; for dish soap only Denkmit remains
    lines = {
        augment("Spülmittel", "putz_waschmittel", rng, chain="DM", cfg=cfg)
        for _ in range(30)
    }
    assert lines == {"DENKMIT SPUELMITTEL"}


def test_quantity_from_field():
    rng = random.Random(0)
    assert receipt_quantity("500 g", rng) == "500G"
    assert receipt_quantity("1,5 l", rng) == "1,5L"
    assert receipt_quantity("10 Stück", rng) == "10ST"


def test_empty_name():
    assert augment("🍓", "obst", random.Random(0)) == ""


def test_chain_of():
    assert chain_of("REWE Markt GmbH") == "REWE"
    assert chain_of("dm-drogerie markt") == "DM"
    assert chain_of("ALDI SÜD") == "ALDI"
    assert chain_of("aldi-sud") == "ALDI"
    assert chain_of("Bäckerei Müller") is None
    assert chain_of(None) is None
