"""Normalization of item names.

The specification is in docs/interface.md. The Kotlin implementation must give
exactly the same results; this is checked via tests/golden/normalize.tsv.

The result contains only the characters A–Z, 0–9, ``% , . - ! &`` and single
spaces. From here on, Python and Kotlin strings (UTF-16) are identical char by char.
"""

import re
import unicodedata

# Replace before decomposition, otherwise "Ä" would become just "A".
_SPECIAL = str.maketrans(
    {
        "ä": "ae",
        "Ä": "AE",
        "ö": "oe",
        "Ö": "OE",
        "ü": "ue",
        "Ü": "UE",
        "ß": "ss",
        "ẞ": "SS",
        "æ": "ae",
        "Æ": "AE",
        "œ": "oe",
        "Œ": "OE",
        "ø": "o",
        "Ø": "O",
    }
)

_DISALLOWED = re.compile(r"[^A-Z0-9%,.\-!& ]")
_SPACES = re.compile(r" +")


def _ascii_upper(text: str) -> str:
    # Deliberately only a–z: str.upper() and Kotlin's uppercase() differ for
    # exotic characters, which are dropped here anyway.
    return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in text)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_SPECIAL)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = _ascii_upper(text)
    text = _DISALLOWED.sub(" ", text)
    return _SPACES.sub(" ", text).strip()
