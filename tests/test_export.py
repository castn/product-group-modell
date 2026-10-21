import numpy as np

from pgm.export import file_name, model_version, probabilities, quantize, read, write
from pgm.golden import GOLDEN, golden_inputs, model_tsv, tiny_model


def test_roundtrip(tmp_path):
    m = tiny_model()
    write(m, tmp_path / "m.bin")
    r = read(tmp_path / "m.bin")
    assert r.labels == m.labels and r.groups == m.groups
    assert r.aliases == m.aliases and r.chains == m.chains
    assert np.array_equal(r.embedding, m.embedding)
    assert np.array_equal(r.scales, m.scales)
    assert r.features == m.features


def test_crc_detects_corruption(tmp_path):
    path = tmp_path / "m.bin"
    write(tiny_model(), path)
    data = bytearray(path.read_bytes())
    data[100] ^= 1
    path.write_bytes(bytes(data))
    try:
        read(path)
    except ValueError as e:
        assert "CRC" in str(e)
    else:
        raise AssertionError("corrupted file not detected")


def test_quantize_error_small():
    emb = np.random.default_rng(1).normal(0, 0.3, (100, 24)).astype(np.float32)
    scales, q = quantize(emb)
    assert np.abs(q * scales[:, None] - emb).max() <= scales.max() / 2 + 1e-7


def test_probabilities_sum_to_one_or_none():
    m = tiny_model()
    p = probabilities(m, "Bio Vollmilch", "REWE")
    assert abs(float(p.sum()) - 1) < 1e-5
    assert probabilities(m, "🍓", None) is None


def test_tiny_golden_is_current():
    assert (GOLDEN / "tiny.bin").read_bytes() == _bytes(tiny_model())
    expected = model_tsv(read(GOLDEN / "tiny.bin"), golden_inputs())
    assert (GOLDEN / "tiny.tsv").read_text(encoding="utf-8") == expected


def _bytes(m) -> bytes:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        write(m, Path(d) / "m.bin")
        return (Path(d) / "m.bin").read_bytes()


def test_version_and_file_name():
    v = model_version("de-DE", "2026.10.1")
    assert v == "de-DE-2026.10.1"
    assert file_name(v) == "pgm-f2-de-DE-2026.10.1.bin"
    assert model_version("de-AT", "2026.11.2-rc1") == "de-AT-2026.11.2-rc1"
    for market, release in [
        ("de", "2026.10.1"),
        ("DE-de", "2026.10.1"),
        ("de-DE", "2026.10-1"),
        ("de-DE", "2026.13.1"),
        ("de-DE", "2026.10.0"),
    ]:
        try:
            model_version(market, release)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{market} {release} accepted")
