# Interface

This file is the binding specification for the Python implementation (`src/pgm/`)
and the Kotlin implementation in the app. If it contradicts the code, this file wins
and the code is adjusted.

Check: both implementations must match the golden values under `tests/golden/` exactly.

## Input and output

Reference: [`kotlin/reference/src/main/kotlin/pgm/ProductGroupModel.kt`](../kotlin/reference/src/main/kotlin/pgm/ProductGroupModel.kt).

```kotlin
data class GroupPrediction(
    val classId: String,     // fine class of the model, e.g. "pflanzendrinks" (mapping/classes.yaml)
    val groupId: String,     // ItemGroup.id of the app, e.g. "dairy" (mapping/groups.yaml)
    val confidence: Float,   // 0..1, probability of the best class
    val level: Level,
)

enum class Level { SURE, SUGGESTION }

class ProductGroupModel {
    val version: String
    /** null if the confidence is below the suggestion threshold or the name has no features */
    fun classify(itemName: String, store: String? = null): GroupPrediction?
    /** The k most likely classes, descending */
    fun topK(itemName: String, store: String? = null, k: Int = 3): List<Pair<String, Float>>
    companion object { fun load(data: ByteArray): ProductGroupModel }
}
```

- `itemName`: the item name of a receipt line, as the app's parser delivers it. Price, tax marker and item number are already removed.
- `store`: name of the merchant as the app knows it (e.g. `"REWE Markt GmbH"`), or `null`. The model detects the chain from it (section Store).
- The model predicts fine classes; the app's group for each class is stored in the model file. `deposit` stays a rule in the app, `other` is only chosen by the user.
- Uncertain cases return `null`, and the next source takes over.
- Order in `ItemGroupClassifier`: `RULE`, `PRODUCT`, `WORDS`, then **`MODEL` from `t_suggest`**, then `DICTIONARY`, then `MERCHANT`. On real receipts the model does better before the dictionary than after it (README, step 8).

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

The normalized name is split into tokens at spaces. Left out are tokens that consist only of `0–9 , . % -` (numbers, prices, weights), and the tokens `X KG G L ML EUR ST STK STUECK AW A B` (units, price and tax markers that the receipt parser leaves on the name, e.g. "BANANE 0, 750 kg x 1,79 EUR/kg"). Quantities with the unit in one word like `500G` stay.

Features in this order:

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

## Store

The model file contains the chains and their aliases from `mapping/stores.yaml` (aliases normalized, `-` as a space, longest first, alphabetical for equal length).

1. `text = normalize(store with "-" replaced by " ")`
2. The first alias that is a word of `text`, equals `text`, or that `text` starts with (`text.startsWith(alias + " ")`) determines the chain.
3. Otherwise no chain, hence no store feature.

The chain (e.g. `REWE`) goes in as the feature `__store=REWE`.

## Computation

Reference in Python: `pgm.export.probabilities`; in Kotlin `ProductGroupModel.probabilities`. Everything in `Float32`, in this order:

1. `ids` = feature IDs (section Features) with the chain as the store. Empty → `null`.
2. `h[d] = Σ_i (embedding[id_i][d] × scale[id_i])` over the features in their order, then `h[d] /= number of features`. `embedding` is `int8`, the product is formed as `Float32`.
3. `z[k] = (bias[k] + Σ_d output[k][d] × h[d]) / T`
4. `p[k] = exp(z[k] − max z) / Σ exp(z − max z)`
5. Best class = largest `p`, on a tie the lower class number. `SURE` from `t_sure`, `SUGGESTION` from `t_suggest`, otherwise `null`.

Differences between Python and Kotlin due to summation order are below `1e-5`; the golden values check the probabilities with this tolerance, and the order of the best classes when they are more than `1e-4` apart.

## File format

Implementation: [`src/pgm/export.py`](../src/pgm/export.py) (write, read) and `ProductGroupModel.load` (Kotlin). All numbers little endian; `str8`/`str16` = length as `u8`/`u16`, then UTF-8.

| Field | Type | Content |
|---|---|---|
| magic | 4 bytes | `PGM1` |
| format | u16 | Version of the format **and of the rules for normalization and features**, currently 2. If a rule changes, the version goes up, and old models are rejected instead of being computed wrongly. (1 → 2: numbers and units no longer become features.) |
| version | str16 | Model version, e.g. `2026.10-de-1` |
| created | i64 | Unix time in seconds |
| buckets | u32 | Number of feature rows |
| dim | u16 | Length of a feature vector |
| minn, maxn | u8, u8 | Length of the character n-grams |
| flags | u16 | Bit 0: word pairs, bit 1: store feature |
| temperature | f32 | Temperature `T` |
| t_sure, t_suggest | f32, f32 | Thresholds for `SURE` and `SUGGESTION` |
| n_labels | u16 | Number of classes |
| labels | n_labels × (str8, str8) | Class and app group |
| n_chains | u16 | Number of chains |
| chains | n_chains × str8 | Chain names (normalized) |
| n_aliases | u16 | Number of aliases |
| aliases | n_aliases × (str8, u16) | Alias (normalized) and index of the chain |
| scales | buckets × f32 | Scale per feature row |
| embedding | buckets × dim × i8 | Feature vectors, value = q × scale |
| output | n_labels × dim × f32 | Output matrix, row by row per class |
| bias | n_labels × f32 | Bias per class |
| crc32 | u32 | CRC-32 (like `java.util.zip.CRC32`) over all preceding bytes |

Size with 2^16 buckets, dim 24 and 46 classes: 1.84 MB.
