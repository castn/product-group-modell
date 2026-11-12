import importlib.util
from pathlib import Path

from pgm.export import FORMAT, file_name, model_version

spec = importlib.util.spec_from_file_location(
    "model_index", Path(__file__).parent.parent / "scripts" / "model_index.py"
)
mi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mi)


def release(version, *, draft=False, prerelease=False, files=None):
    name = file_name(version)
    files = [name, f"{name}.sha256"] if files is None else files
    return {
        "tag_name": f"model-{version}",
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": n, "size": 1, "browser_download_url": n} for n in files],
    }


def test_scheme_matches_export():
    version = model_version("de-DE", "2026.10.1")
    assert mi.VERSION.fullmatch(version)
    f = mi.FILE.fullmatch(file_name(version))
    assert int(f["format"]) == FORMAT and f["version"] == version
    assert not mi.VERSION.fullmatch(model_version("de-DE", "2026.10.1-rc1"))


def test_newest_per_format_and_market():
    rels = [
        release("de-DE-2026.09.1"),
        release("de-DE-2026.10.2"),
        release("de-DE-2026.10.10"),  # numeric, not lexical
        release("de-DE-2026.11.1", prerelease=True),  # rollback
        release("de-DE-2026.12.1", draft=True),
        release("de-DE-2026.12.1-rc1"),
        release("at-AT-2026.10.1"),
        {"tag_name": "v1.0", "draft": False, "prerelease": False, "assets": []},
    ]
    chosen = mi.newest(mi.candidates(rels))
    assert [(c["market"], c["version"]) for c in chosen] == [
        ("at-AT", "at-AT-2026.10.1"),
        ("de-DE", "de-DE-2026.10.10"),
    ]
    assert chosen[1]["checksum"]["name"] == f"{file_name('de-DE-2026.10.10')}.sha256"


def test_formats_side_by_side():
    v = "de-DE-2026.12.1"
    rel = release(v, files=[f"pgm-f2-{v}.bin", f"pgm-f3-{v}.bin", "other.bin"])
    older = release("de-DE-2026.10.1", files=["pgm-f2-de-DE-2026.10.1.bin"])
    chosen = mi.newest(mi.candidates([older, rel]))
    assert [(c["format"], c["version"]) for c in chosen] == [(2, v), (3, v)]
    assert chosen[0]["checksum"] is None  # entry() aborts on it
