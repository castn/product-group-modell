# Interface

This file is the binding specification for the Python implementation (`src/pgm/`)
and the Kotlin implementation in the app. If it contradicts the code, this file wins
and the code is adjusted.

Check: both implementations must match the golden values under `tests/golden/` exactly.

## Input and output

```kotlin
data class GroupPrediction(
    val groupId: Int,        // item group ID of the app (mapping/groups.yaml)
    val confidence: Float,   // 0..1, calibrated
    val level: Level,
)

enum class Level { SURE, SUGGESTION }

interface ProductGroupClassifier {
    val modelVersion: String
    /** null if the confidence is below the suggestion threshold or the name has no features. */
    fun classify(itemName: String, store: String? = null): GroupPrediction?
    /** The k most likely groups, sorted in descending order. */
    fun topK(itemName: String, store: String? = null, k: Int = 3): List<Pair<Int, Float>>
}
```

- `itemName`: the item name of a receipt line, as the app's parser delivers it. Price, tax marker and item number are already removed.
- `store`: name of the chain (e.g. `"Rewe"`), or `null` if unknown. It is normalized like the item name.
- There is no "other" group. Uncertain cases return `null`, and the next source (dictionary) takes over.

## Normalization

Implementation: [`src/pgm/normalize.py`](../src/pgm/normalize.py), golden values: [`tests/golden/normalize.tsv`](../tests/golden/normalize.tsv).

Steps in exactly this order:

1. Unicode normal form **NFKC** (e.g. full-width characters and ligatures like `ﬁ` → `fi`).
2. Replace according to the table (upper and lower case):
   `ä→ae ö→oe ü→ue ß→ss ẞ→SS æ→ae œ→oe ø→o` (and the upper-case letters accordingly: `Ä→AE` etc.).
3. Unicode normal form **NFKD** and remove all characters of category *Mn* (non-spacing marks). `é` becomes `e`, `İ` becomes `I`.
4. Convert **only** `a`–`z` to `A`–`Z`. No `uppercase()` with a locale, because Java and Python differ in special cases.
5. Replace every character except `A–Z 0–9 % , . - ! &` and the space with a space.
6. Collapse runs of spaces into one and remove spaces at the start and end.

The result consists of ASCII characters only. So lengths and indices are the same in Python (code points) and Kotlin (UTF-16), which matters for the character n-grams.

Kotlin notes: `java.text.Normalizer.normalize(s, Normalizer.Form.NFKC)`, accents via `Character.getType(c) == Character.NON_SPACING_MARK`. Characters outside the BMP (e.g. emoji) become a space in step 5. If Kotlin iterates over `Char` instead of code points, two spaces result, which step 6 collapses again. So the result is the same, but iterating over code points is still cleaner.

## Features

Implementation: [`src/pgm/features.py`](../src/pgm/features.py).

The normalized name is split into tokens at spaces. Features in this order:

1. For each token `T`:
   - the word `<T>`
   - all substrings of `<T>` of length `minn`…`maxn` (first all of length `minn` from left to right, then `minn+1` …), **except** the whole word `<T>` itself
2. If `bigrams`: for each adjacent token pair `"T1 T2"` (with one space)
3. If `store` and a store is given and the name has at least one token: `__store=` + normalized store

Duplicate features are kept (they count multiple times when averaging).
A name without tokens has no features, and `classify` then returns `null`.

Bucket of a feature: `fnv1a32(utf8(feature)) mod buckets`.

FNV-1a, 32 bit: offset basis `0x811C9DC5`. For each byte `h = (h xor byte) * 0x01000193 mod 2^32`.
In Kotlin, compute with `UInt` or with `Long` masked by `and 0xFFFFFFFFL`. The byte goes in **unsigned** (`b.toInt() and 0xFF`).

The parameters (`buckets`, `minn`, `maxn`, `bigrams`, `store`) are stored in the model file and not fixed in the code.

## Computation

*To be fixed together with the export format (step 9).* Planned:
average the feature vectors, multiply by the output matrix, add the bias, divide by the temperature `T`, softmax.
Everything in `Float32`.
