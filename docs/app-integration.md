# Integration into an app

Guide for integrating the model into an Android or JVM app, written for MyExpenses. Model specification: [interface.md](interface.md), license obligations: [license.md](license.md).

## Overview

| What | From | Where in the app |
|---|---|---|
| `Normalize.kt`, `Features.kt`, `ProductGroupModel.kt` | `kotlin/reference/src/main/kotlin/pgm/` | own package, e.g. `…receipts.model` |
| Model file `pgm-f<format>-<market>-<release>.bin` (1.84 MB) | release or `dist/` after `scripts/export.py` | assets, e.g. `assets/item_groups/model.bin` |
| Golden values for the test | `tests/golden/` | test resources |
| Notice about Open Food Facts | `docs/license.md` | About dialog |

The three Kotlin files need no libraries, only `java.nio`, `java.text.Normalizer` and `java.util.zip.CRC32`.

## 1. Take over the Kotlin files

Copy the three files and only adjust the `package` line. **Change nothing else:** any deviation in normalization or features shifts the predictions. Changes belong in this repository, with new golden values, and go from there into the app.

`FeatureConfig` and `Level` are public. If the names clash in the app's package, better make them `internal` than rename them.

## 2. Model file as an asset

```
src/main/assets/item_groups/model.bin   ← pgm-f2-de-DE-2026.10.1.bin
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
                reportError(e)
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

`reportError` stands for the app's error reporting. The provider belongs into the app's dependency injection as a singleton.

## 4. Placing it next to other sources

- `classify(name, store)` only returns a group from `t_suggest` (currently 0.5), otherwise `null`, and then the app's next source takes over.
- `level` distinguishes `SURE` (from `t_sure`, currently 0.9) and `SUGGESTION`. The app can mark suggestions in the review screen.
- `store` is the merchant as the app knows it ("REWE Markt GmbH"). The model detects the chain itself, unknown stores do no harm.
- The item name goes in as the parser delivers it. The app does not need to remove remnants like "0, 750 kg x 1,79 EUR/kg".
- Skip a `groupId` the app does not know instead of guessing.
- What the user assigned themselves should take precedence over the model.
- The model belongs **before** a simple dictionary. On real receipts that was better than after it ([README](../README.md#results-so-far)).
- `classId` (e.g. `pflanzendrinks`) is finer than the group, for apps that later want to show finer groups.

## 5. Golden value tests

So that the copied files compute exactly as here:

1. Copy `tests/golden/normalize.tsv`, `features.tsv`, `tiny.bin` and `tiny.tsv` into the test resources, e.g. `src/test/resources/item_groups/`.
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

## 6. Notice in the About dialog

Required by ODbL §4.3 as soon as the model is shipped. Text (German and English) in [license.md](license.md), section "Notice text for the app". The model version comes from `model.version`.

## 7. Shipping a new model version

1. Train here, compare against the previous version with `scripts/evaluate.py` and export with `scripts/export.py --release <release>` (scheme: [interface.md](interface.md#versions-and-file-names)).
2. Check with `scripts/release.py --version <modelversion>` and assemble the release, then tag and upload.
3. Replace the file in the app as `assets/item_groups/model.bin` and add an entry to the ChangeLog.

If normalization or features change, the format version goes up. Then the three Kotlin files must be replaced in the same app version too, otherwise the new model does not load and the app works without a model.

## Key figures

| | |
|---|---|
| Size of the model file | 1.84 MB |
| Memory at runtime | about 2 MB |
| Computation time | about 0.1 ms per row on the desktop (JVM), more on a phone; a receipt with 30 rows stays in the range of a few milliseconds |
| Classes / groups | 46 fine classes on 15 groups of the app |
