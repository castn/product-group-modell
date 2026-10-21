# Integration into the app (step 11)

Guide for integrating the model into MyExpenses. It is based on the state of `ItemGroupClassifier`, `ItemGroup` and `ItemDictionary` in `kotlin/app-snapshot/`. Model specification: [interface.md](interface.md), license obligations: [license.md](license.md).

## Overview

| What | From | Where in the app |
|---|---|---|
| `Normalize.kt`, `Features.kt`, `ProductGroupModel.kt` | `kotlin/reference/src/main/kotlin/pgm/` | next to `ItemGroupClassifier`, e.g. package `…next.receipts.model` |
| Model file `pgm-f<format>-<market>-<release>.bin` (1.84 MB) | `dist/` after `scripts/export.py` | assets, e.g. `assets/item_groups/model.bin` |
| Golden values for the test | `tests/golden/` | test resources |
| new source `MODEL` | – | `ItemGroupClassifier` |
| Notice about Open Food Facts | `docs/license.md` | About dialog |

The three Kotlin files need no libraries, only `java.nio`, `java.text.Normalizer` and `java.util.zip.CRC32`.

## 1. Take over the Kotlin files

Copy the three files and only adjust the `package` line. **Change nothing else:** any deviation in normalization or features shifts the predictions. Changes belong in this repository, with new golden values, and go from there into the app.

`FeatureConfig` and `Level` are public. If the names clash in the app's package, better make them `internal` than rename them.

## 2. Model file as an asset

```
myExpenses/src/main/assets/item_groups/model.bin   ← dist/pgm-f2-de-DE-2026.10.1.bin
```

- The file name in the app stays fixed, the version is in the file (`model.version`).
- The file is read once in full (`readBytes()`). Whether the APK compresses it does not matter for that.
- A model with the wrong format or a corrupted file throws `IllegalArgumentException` on load. The app then continues without a model (section 3).

## 3. Loading

Once, in the background, and then keep it in memory. The file needs about 2 MB of heap. Loading takes a few tens of milliseconds, so not on the main thread.

```kotlin
/** Loads the model on first access; null if it is missing or does not fit. */
class ItemGroupModelProvider(private val context: Context) {

    private val model: Deferred<ProductGroupModel?> by lazy {
        CoroutineScope(Dispatchers.IO).async {
            try {
                context.assets.open(ASSET).use { ProductGroupModel.load(it.readBytes()) }
            } catch (e: Exception) {
                // Missing or incompatible file: continue without a model, do not crash
                CrashHandler.report(e)
                null
            }
        }
    }

    suspend fun get(): ProductGroupModel? = model.await()

    companion object {
        const val ASSET = "item_groups/model.bin"
    }
}
```

`CrashHandler.report(e)` is the app's existing error reporting (`util/crashreporting/CrashHandler.kt`). The provider belongs into the existing dependency injection as a singleton.

## 4. New source in `ItemGroupClassifier`

### Order

```
RULE → PRODUCT → WORDS → MODEL → DICTIONARY → MERCHANT
```

- Learned products and words of the user (`PRODUCT`, `WORDS`) always win. If the user corrects a suggestion of the model, from then on it is a learned choice. Nothing else is needed for that.
- The model goes **before** the dictionary. On real receipts that was better than after it (README, step 8): 92 % of the rows with a suggestion, 91 % of them correct, compared to 79 % and 85 % with dictionary and merchant.
- `classify` only returns something from `t_suggest` (currently 0.5), otherwise `null`. Then the dictionary takes over.

### Changes

```kotlin
enum class ItemGroupSource {
    RULE,
    PRODUCT,
    WORDS,

    /** Model from Open Food Facts data (product-group-modell), from its suggestion threshold */
    MODEL,

    DICTIONARY,
    MERCHANT
}

/**
 * @param confident false for a suggestion of the model below its confidence threshold;
 * the review screen can highlight such groups
 */
data class ItemGroupSuggestion(
    val group: ItemGroup,
    val source: ItemGroupSource,
    val confident: Boolean = true,
)

class ItemGroupClassifier(
    learned: List<LearnedItemGroup>,
    private val model: ProductGroupModel? = null,
) {
    …
    private fun classify(
        item: ReceiptItem,
        merchant: String?,
        merchantGroup: ItemGroup?,
        discountGroup: () -> ItemGroup?
    ): ItemGroupSuggestion? {
        …
        byWords(words)?.let { return ItemGroupSuggestion(it, ItemGroupSource.WORDS) }
        byModel(item.name, merchant)?.let { return it }
        byDictionary(words)?.let { return ItemGroupSuggestion(it, ItemGroupSource.DICTIONARY) }
        return merchantGroup?.let { ItemGroupSuggestion(it, ItemGroupSource.MERCHANT) }
    }

    private fun byModel(name: String, merchant: String?): ItemGroupSuggestion? {
        val prediction = model?.classify(name, merchant) ?: return null
        // Group this app version does not know: skip instead of guessing
        val group = ItemGroup.ofId(prediction.groupId) ?: return null
        return ItemGroupSuggestion(group, ItemGroupSource.MODEL, prediction.level == Level.SURE)
    }
}
```

- `merchant` is passed through from `classify(items, merchant)` to the model unchanged. The model detects the chain itself ("REWE Markt GmbH" → `REWE`). Unknown stores do no harm.
- `item.name` goes in as the parser delivers it. The app does not need to remove remnants like "0, 750 kg x 1,79 EUR/kg", the model ignores numbers and units.
- Deposit and discounts stay rules (`RULE`) and come before the model.
- The app does not need `prediction.classId` (e.g. `pflanzendrinks`) for now. Anyone who later wants to show finer groups will find them there.

### Who builds the classifier

Where `ItemGroupClassifier(learned)` is created today, first await `provider.get()` and pass in the model. Until the model is loaded, or if it is missing, the classifier works as before (`model = null`).

## 5. Review screen

- Take over groups set with `SURE` (from `t_sure`, currently 0.9) as before.
- `confident = false` (between 0.5 and 0.9) is a suggestion. Proposal: show the same group, but mark it subtly, for example with a question mark or in italics. If the user confirms, the choice is learned like any other.
- For orientation: on real receipts, suggestions from 0.9 were about 95 % correct, between 0.5 and 0.9 considerably less often.

## 6. Tests in the app

### Golden values

So that the copied files compute exactly as here:

1. Copy `tests/golden/normalize.tsv`, `features.tsv`, `tiny.pgm` and `tiny.tsv` into the test resources, e.g. `src/test/resources/item_groups/`.
2. Take over `GoldenTest.kt` and `ModelGoldenTest.kt` from `kotlin/reference/src/test/kotlin/pgm/` and read the files from the resources instead of via `System.getProperty("golden.dir")`:

```kotlin
private fun resource(name: String) =
    javaClass.getResourceAsStream("/item_groups/$name")!!.readBytes()
```

`exportedModels()` against `dist/` is dropped in the app. Instead, a test checks that the shipped asset loads:

```kotlin
@Test
fun bundledModelLoads() {
    val bytes = File("src/main/assets/item_groups/model.bin").readBytes()
    val model = ProductGroupModel.load(bytes)
    assertTrue(model.version.isNotEmpty())
    // The app must know every group of the model
    assertTrue(model.groups.all { ItemGroup.ofId(it) != null }, model.groups.toString())
}
```

### Existing tests of `ItemGroupClassifier`

They build the classifier without a model (`ItemGroupClassifier(emptyList())`) and stay green unchanged. In addition:

- a test that `MODEL` applies before `DICTIONARY` and `PRODUCT` before `MODEL`, with the small test model `tiny.pgm` or the real asset,
- optionally `labelledReceipts…` from `ItemGroupClassifierTest` additionally with the model, so that a new model version does not get worse unnoticed.

## 7. Notice in the About dialog

Required by ODbL §4.3 as soon as the model is shipped. Text (German and English) in [license.md](license.md), section "Notice text for the app". The model version comes from `model.version`.

**Beforehand:** this repository must be public (ODbL §4.6), and the link in the notice must point to it.

## 8. Shipping a new model version

1. Train here, compare against the previous version with `scripts/evaluate.py` and export with `scripts/export.py --release <release>` (scheme: [interface.md](interface.md#versions-and-file-names)).
2. Run the Kotlin test here (`./gradlew :reference:test`); it checks the model in `dist/` against its golden values.
3. Tag the version here (`git tag model-<modelversion>`, e.g. `model-de-DE-2026.10.1`).
4. Replace the file in the app as `assets/item_groups/model.bin` and add an entry to the ChangeLog.

If normalization or features change, the format version goes up. Then the three Kotlin files must be replaced in the same app version too, otherwise the new model does not load and the app works without a model.

## Key figures

| | |
|---|---|
| Size of the model file | 1.84 MB |
| Memory at runtime | about 2 MB |
| Computation time | about 0.1 ms per row on the desktop (JVM), more on a phone; a receipt with 30 rows stays in the range of a few milliseconds |
| Classes / groups | 46 fine classes on 15 groups of the app |
