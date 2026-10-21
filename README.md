<div align="center">

# Product Group Modell · pgm

**A tiny model that sorts receipt lines into item groups — trained in Python, computed in plain Kotlin.**

[![License: GPL-3.0-or-later](docs/badges/license.svg)](LICENSE)
![Python ≥ 3.12](docs/badges/python.svg)
![Kotlin without dependencies](docs/badges/kotlin.svg)
![Model size under 2 MB](docs/badges/model.svg)
![Status: pre-integration](docs/badges/status.svg)

</div>

```
"JA! H-Milch 1L"       -->  milch_sahne -> dairy,  confidence 1.00  ->  SURE
"Bio Vollmilch 3,5%"   -->  milch_sahne -> dairy,  confidence 0.85  ->  SUGGESTION
```

The model assigns item names from receipts to an item group of the app [MyExpenses](https://github.com/mtotschnig/MyExpenses).
It learns from **Open Food Facts**, **Open Beauty Facts**, **Open Products Facts** and **Open Pet Food Facts**, is trained in Python, and in the app is computed with the same weights by a Kotlin implementation without libraries.

## Contents

- [Results so far](#results-so-far)
- [How it works](#how-it-works)
- [Setup](#setup)
- [Pipeline](#pipeline)
- [Test data](#test-data)
- [Integration into the app](#integration-into-the-app)
- [Open](#open)
- [Project structure](#project-structure)
- [License](#license)
- [Related work](#related-work)

## Results so far

On 107 rows of real receipts that the app's dictionary does not know (item group level):

| Variant | with suggestion | of which correct |
|---|---:|---:|
| dictionary → merchant (in the app today) | 79 % | 85 % |
| model alone from 0.9 | 52 % | 95 % |
| **model from 0.5 → dictionary → merchant** | **94 %** | **88 %** |
| **model from 0.7 → dictionary → merchant** | **92 %** | **91 %** |
| dictionary → model from 0.5 → merchant | 95 % | 84 % |

> [!CAUTION]
> These are few rows (±6 percentage points), and two improvements were made after looking at exactly these rows. A clean final evaluation still needs an untouched batch (goal: ≥ 1,000 rows from ≥ 5 chains).

Thresholds stored in the model file:

| Confidence | Level |
|---|---|
| ≥ `t_sure = 0.9` | `SURE` |
| ≥ `t_suggest = 0.5` | `SUGGESTION` |
| below | `null` — the app asks the dictionary |

## How it works

| | |
|---|---|
| **Normalization** | Every name is brought into one spelling before features are built, so that `Müller`, `MÜLLER` and `MUELLER` all become `MUELLER`:<br>1. **NFKC** (Unicode Normalization Form KC): typographic variants become plain characters (`ﬁ→fi`, full-width `Ａ→A`, `²→2`).<br>2. **Spell out umlauts** (`ä→AE`, `ö→OE`, `ü→UE`, `ß→SS`): receipt printers often write them this way already, and simply removing the dots would turn `Ä` into `A`.<br>3. **Remove remaining accents** (`é→E`), **upper case**, keep only `A–Z 0–9 % , . - ! &`.<br>The result is ASCII, so Python and Kotlin produce identical text char by char. |
| **Features** | The normalized name is cut into small pieces, and the model looks only at those pieces:<br>• **Words**, e.g. `<VOLLMILCH>` (`<` `>` mark the word boundaries).<br>• **Character n-grams** of length 2–5: every run of n consecutive characters. With n = 4, `VOLLMILCH` gives `<VOL VOLL OLLM LLMI LMIL MILC ILCH LCH>`. `MILC`, `ILCH` and `LCH>` also come from `MILCH`, so unknown, abbreviated or misread words still share features with known ones.<br>• **Word pairs**, e.g. `BIO VOLLMILCH`.<br>• Optionally the **chain**, `__store=<CHAIN>` (from `mapping/stores.yaml`).<br>Pure numbers and units (`KG`, `EUR`, `X` …) are skipped. Each piece is hashed (FNV-1a 32 bit, `mod 2^16`) into one of 65,536 slots, so no word list is stored. |
| **Model** | A fastText-style classifier, small enough for a phone (PyTorch `EmbeddingBag` + `Linear`):<br>1. Each feature slot has a **vector of 24 numbers** that was learned in training.<br>2. The vectors of all features of a name are **averaged** into one vector that describes the whole name.<br>3. An **output matrix** turns it into one score per class.<br>4. **Softmax** turns the scores into probabilities that add up to 1; a temperature `T` stored in the file makes them less or more extreme. The highest probability is the `confidence`.<br>No neural network library is needed for this; the Kotlin version is a few plain loops (`ProductGroupModel.kt`). |
| **Two levels** | The model learns 46 **fine classes** (`mapping/classes.yaml`), e.g. `milch_sahne`; the app shows 15 coarser **item groups** (`mapping/groups.yaml`), e.g. `dairy`. Fine classes are easier to learn cleanly (milk and cheese look different on a receipt) and allow the groups to be rearranged later: the table class → group is stored in the model file and can be changed **without retraining**.<br>Two groups are not predicted: `deposit` (Pfand) stays a rule in the app, `other` is only chosen by the user. |
| **Training data** | There are no large sets of labelled receipt lines, so they are generated:<br>1. **Product names** from Open Food Facts & co. get a class via the category mapping (`mapping/off_to_class.yaml`).<br>2. Each name is turned into **receipt-style variants**: abbreviations, private labels, quantities, price remnants, text recognition errors, truncation. From `Bio Vollmilch 3,5% Fett`, for example:<br>`GUT&GUENSTIG BIO V-MILCH 3,5% FETT`, `BI0 VOLLMILCH 3,5% FETT 1L`, `GUT & GUE BIO VOLLM. 3 EUR`<br>3. Training and validation are **split per product, before** the variants are made, so the validation never contains a variant of a product the model was trained on. |
| **Model file** | One binary file of ~2 MB with everything the app needs:<br>• **Feature vectors** as `int8` (one byte per number instead of four) with a scale factor per row. This makes the vectors 4× smaller than as 32-bit floats.<br>• **Classes, groups, thresholds and chain table**, so these can change without an app update.<br>• A **format version** in the header: if the rules for normalization or features change, old files are rejected instead of being computed wrongly.<br>• A **CRC-32** checksum at the end that detects a damaged file. |

Specified in binding form in [docs/interface.md](docs/interface.md) (normalization, features, computation, file format).

## Setup

Requirements: [uv](https://docs.astral.sh/uv/) (Python ≥ 3.12, PyTorch CPU only), for Kotlin a JDK 25.

```sh
uv sync
uv run pytest                    # normalization, features, export against tests/golden/
cd kotlin && ./gradlew test      # Kotlin against tests/golden/ and all models in dist/
```

### Golden value tests

The model is computed twice: in Python for training and in Kotlin in the app. Both must give the same answer for every receipt line. A small difference would not crash anything, but the app would quietly give worse suggestions. So Python writes inputs and their exact expected outputs (the **golden values**) into files, and the tests on both sides compare against them:

| File | Input → expected output |
|---|---|
| `tests/golden/normalize.tsv` | name → normalized text, e.g. `JA! H-Milch 1L` → `JA! H-MILCH 1L` (written by hand, it is the specification) |
| `tests/golden/features.tsv` | name + store → feature IDs (generated from Python) |
| `tests/golden/tiny.bin` + `tiny.tsv` | a small model with random weights → its probabilities per name |
| `dist/*.golden.tsv` | for each exported real model: its predictions (written by `scripts/export.py`) |

Probabilities may differ by up to `1e-5`, because Python and Kotlin add floating-point numbers in a slightly different order.

If normalization or features change, update Python and Kotlin together, regenerate the golden values with `uv run python -m pgm.golden`, and make both test suites pass again.

## Pipeline

The pipeline turns the open product databases into a model file for the app, in eight steps. Each step is one script that reads the output of the step before and writes its own, so a step can be repeated without starting over (e.g. retrain with other settings without downloading again).

| # | Script | What it does | Output |
|---|---|---|---|
| 1 | `fetch.py` | Downloads the four product databases and their category taxonomies, pinned to a fixed revision. Only entries without a name or category are dropped. | `data/raw/` |
| 2 | `extract_de.py` | Keeps products with a German name. Food must also be sold in DE, AT or CH, so it looks like the German assortment. | `data/interim/de.parquet` |
| 3 | `mapping_report.py` | Gives each product a fine class via `mapping/off_to_class.yaml` and reports unmapped categories and conflicts: the work list for improving the mapping. | `data/interim/de_labeled.parquet`, `reports/mapping.md` |
| 4 | `build_dataset.py` | Removes duplicate names, splits into training and validation per product, and generates the receipt-style variants. Rare classes get more variants. Also adds the German category names (`Feigen`, `Kürbiskerne`), because loose goods appear on receipts with exactly such generic names. | `data/processed/dataset.parquet` |
| 5 | `train.py` | Trains the model, chooses the temperature `T` so that confidence roughly matches the hit rate, and reports on validation set and real receipts. | `models/<name>/`, `reports/train-<name>.md` |
| 6 | `evaluate.py` | Compares on the real receipts: dictionary alone, model alone at various thresholds, and both orders of model and dictionary. This produces the table in [Results so far](#results-so-far). | `reports/eval-<name>.md` (do not commit) |
| 7 | `export.py` | Writes the binary model file, after checking how much rounding to `int8` changes the predictions, plus golden values for the Kotlin test. | `dist/pgm-f<format>-<market>-<release>.bin`, `.golden.tsv` |
| 8 | `release.py` | Checks the file (header, CRC, Kotlin test, clean working tree) and prepares model, checksum and release text for upload. Uploads nothing itself. | `release/<version>/` |

Steps 1–3 are only needed when the raw data or the mapping changes; experiments usually start at step 4 or 5. All results end up in `data/`, `models/`, `reports/`, `dist/` and `release/` (not in the repo).

```sh
uv run scripts/fetch.py               # raw data + taxonomies → data/raw/ (food about 7.8 GB, resumable)
uv run scripts/extract_de.py          # German products → data/interim/de.parquet
uv run scripts/mapping_report.py      # assign classes → data/interim/de_labeled.parquet, reports/mapping.md
uv run scripts/build_dataset.py       # training/validation in receipt style → data/processed/dataset.parquet
uv run scripts/train.py --name dev5   # → models/dev5/, reports/train-dev5.md
uv run scripts/evaluate.py --name dev5    # real receipts → reports/eval-dev5.md
uv run scripts/export.py --name dev5 --release 2026.11.1     # → dist/pgm-f2-de-DE-2026.11.1.bin + .golden.tsv
uv run scripts/release.py --version de-DE-2026.11.1          # check and prepare for upload → release/de-DE-2026.11.1/
```

<details>
<summary><b>Useful options</b></summary>

- `fetch.py --limit N` for a quick test run, `--only food,tax-food` for individual sources, `--revision <commit>` to resume a download.
- `train.py --dim --buckets --minn --maxn --[no-]bigrams --[no-]store --epochs --lr --seed` (defaults as in `dev4`: dim 24, 2^16 buckets, 2–5, word pairs and store on).
- `export.py --market de-DE` (default) and `--release YYYY.MM.N` give the name `pgm-f<format>-<market>-<release>.bin`; scheme in [docs/interface.md](docs/interface.md#versions-and-file-names). `--t-sure --t-suggest` set the thresholds in the file.
- `release.py` checks the model file (header, CRC, Kotlin test, clean working tree) and stores the model, checksum (`<file>.sha256`) and the release text `RELEASE.md`. The golden values from `dist/` are not included (license). At the end it prints the commands for tagging and uploading to Codeberg.
- `scripts/baseline.py` measures the app's dictionary alone. Run `cd kotlin && ./gradlew :baseline:installDist` first; it needs the app's code in `kotlin/app-snapshot/`.

</details>

Which raw data was used is recorded with URL, revision and checksum in [data/raw/MANIFEST.json](data/raw/MANIFEST.json).

### What is maintained by hand

| File | Content |
|---|---|
| `mapping/groups.yaml` | item groups of the app; the IDs are stored in its database and never change |
| `mapping/classes.yaml` | fine classes → item group |
| `mapping/off_to_class.yaml` | categories of the taxonomies → class (`~` weak, `+` preferred, `null` ignore, `_drop` drop) |
| `mapping/stores.yaml` | retail chains and their spellings for the store feature |
| `augment/abbrev_de.tsv` | abbreviations observed on receipts |
| `augment/private_labels.tsv` | private labels and their chains |

After changes to the mapping, `reports/mapping.md` shows coverage, conflicts and unmapped categories (current state: 82 % of German food products with a class, 3 % conflicts; scarce are `tabak`, `putz_waschmittel`, `haushaltswaren`).

> [!WARNING]
> Always change normalization or features in Python **and** Kotlin, with new golden values (see [Golden value tests](#golden-value-tests)).

## Test data

The training data is generated (see [How it works](#how-it-works)), so it can only show how well the model learns its own invented receipt lines. Whether it works on **real** receipts can only be measured on real receipts. That is what `data/eval/` is for: receipts scanned with the app, each name labelled by hand with the correct fine class.

**Files per receipt** (`<merchant>-<date>-<time>.*`):

| File | Content |
|---|---|
| `.jpg` | photo of the receipt |
| `.json` | text recognition output |
| `.expected.json` | what the app's receipt parser should make of it |
| `.item-groups.csv` | the hand labelling: correct fine class per item |

All receipts are merged into one table, `data/eval/receipts.csv`, which `scripts/evaluate.py` and `scripts/baseline.py` read (`scripts/train.py` also scores the finished model on it in its report, but never trains on it):

| Column | Meaning | Example |
|---|---|---|
| `receipt` | file name without extension | `backshoo-20261003-1442` |
| `merchant` | shop as the app recognized it | `Backshoo` |
| `name` | item name as printed | `Strudel mit Kirschen` |
| `amount` | price in cents | `300` |
| `class` | correct fine class | `kuchen_gebaeck` |
| `dictionary_seen` | `ja` if the app's dictionary was built with this receipt in view | `ja` |

**Why `dictionary_seen` matters:** the app's dictionary was partly written while looking at some of these receipts, so it naturally knows their items. Comparing the model with the dictionary on those rows would be unfair to the model. The meaningful comparison uses only the rows with `dictionary_seen` ≠ `ja`. This is where the 107 rows in [Results so far](#results-so-far) come from.

**Current size** (2026-10-03): 186 rows from 25 receipts, of which 107 rows from 15 receipts unknown to the dictionary (mostly REWE). That is too few and too one-sided for a final verdict, hence the goal of ≥ 1,000 rows from ≥ 5 chains.

> [!CAUTION]
> Receipts are **personal data** (where and when someone shopped, what they bought).
> - Never in the repo: `data/**` and `reports/*` are in `.gitignore`. `reports/eval-*.md` quotes rows from it, so do not commit those either.
> - Never for training, abbreviation lists or mapping. Anything learned from these receipts would also make the evaluation look better than it is.

## Integration into the app

The app already suggests item groups without the model, from several **sources** that are asked in order; the first one that knows the item wins. The model becomes one more source in this chain:

```
RULE → PRODUCT → WORDS → MODEL → DICTIONARY → MERCHANT
```

| Source | Where the group comes from |
|---|---|
| `RULE` | fixed rules: deposit, and a discount takes the group of its item |
| `PRODUCT` | the user chose a group for the same product before |
| `WORDS` | words from products the user assigned before |
| **`MODEL`** | **this model, if its confidence is at least `t_suggest` (0.5)** |
| `DICTIONARY` | the app's built-in word list |
| `MERCHANT` | the kind of shop, e.g. a drugstore, for items no other source knows |

The user's own choices always come first. The model sits **before** the dictionary because on real receipts that order was more accurate ([Results so far](#results-so-far)). Below the threshold it returns `null` and the dictionary gets its turn as before.

**What the app needs** (step by step in [docs/app-integration.md](docs/app-integration.md)):

1. **Three Kotlin files** from `kotlin/reference/src/main/kotlin/pgm/`: `Normalize.kt`, `Features.kt`, `ProductGroupModel.kt`. Copy them unchanged, only adjust the `package` line. They need no libraries. Any deviation would shift the predictions, so changes are made here and copied over.
2. **The model file** as the asset `item_groups/model.bin`. The name stays fixed; the version is stored inside the file.
3. **Load once in the background** and keep it in memory (about 2 MB). If the file is missing, damaged or of the wrong format, loading fails and the app simply works as before without a model.
4. **Call it per item:**
   ```kotlin
   val model = ProductGroupModel.load(bytes)
   model.classify("JA! H-Milch 1L", store = "REWE Markt GmbH")
   // → GroupPrediction(classId = "milch_sahne", groupId = "dairy", confidence = 1.0, level = SURE)  or null
   ```
   The name goes in as the receipt parser delivers it, prices and units included. The store is optional; the model detects the chain itself. `level` tells `SURE` (≥ 0.9) from `SUGGESTION`, so the app can mark less certain suggestions in the review screen. `topK(name, store, k)` returns the k most likely classes. About 0.1 ms per item on the desktop.
5. **Golden value tests** from `tests/golden/`, so that the copied files are checked to compute exactly like Python.
6. **A notice in the About dialog**, required by the data license (text in [docs/license.md](docs/license.md)).

For recomputing a prediction in Python: `pgm.export.read` and `pgm.export.probabilities`.

## Open

- [ ] Another batch of real receipts for an unbiased final evaluation and the calibration of the thresholds.
- [ ] Integration into the app per [docs/app-integration.md](docs/app-integration.md); publish the repository first.
- [ ] Script that updates `kotlin/app-snapshot/` from a checkout of the app and records repository, branch and commit in `SOURCE` (by hand so far).
- [ ] Decide: shipped with the app or downloaded later (own versioning, update without an app release)?
- [ ] Further languages (fr/it/es/en) in **one** model under 2 MB, with its own abbreviations and private labels per language. Without real receipts in these languages there are only figures on generated data; the German result must not get worse.

## Project structure

```
├── docs/            interface.md (specification), license.md, app-integration.md; badges/ (scripts/badges.py)
├── mapping/         item groups, classes, category mapping, chains
├── augment/         abbreviations and private labels for the receipt style
├── src/pgm/         normalize, features, categories, augment, stores, model, export, evaldata, golden
├── scripts/         fetch, extract_de, mapping_report, build_dataset, train, evaluate, export, release, baseline
├── tests/           pytest; golden/ with golden values and mini model tiny.bin
├── kotlin/
│   ├── reference/   Kotlin reference (goes into the app as is) + golden value tests
│   ├── baseline/    the app's dictionary as a command-line tool for baseline.py
│   └── app-snapshot/  fixed copy of the classifier from the app, origin in SOURCE
├── data/            raw, intermediate, training and test data (only MANIFEST.json in the repo)
├── models/          trained models (not in the repo)
├── reports/         generated reports (not in the repo)
├── dist/            exported model files (not in the repo)
└── release/         finished releases for upload (scripts/release.py, not in the repo)
```

## License

| What | License |
|---|---|
| This repository | **GNU General Public License, version 3 or later** ([LICENSE](LICENSE)), like the app |
| Model files (`pgm-*.bin`) | not covered by the GPL; **under clarification with Open Food Facts**, see [docs/license.md](docs/license.md) |
| Source data | ODbL 1.0 (database) and DbCL 1.0 (contents) |

## Related work

At the time of research (October 2026) there was no ready-made, open model for German receipt lines that is small enough for an app.

| Project | Notes |
|---|---|
| [openfoodfacts/category_classifier](https://huggingface.co/openfoodfacts/category_classifier) | categories for Open Food Facts, needs ingredients, nutrition facts and images, too large, archived |
| [InseeFrLab/torchTextClassifiers](https://github.com/InseeFrLab/torchTextClassifiers) | fastText in PyTorch; alternative to our own trainer |
| [INSEE codif-coicop-bdf](https://github.com/InseeFrLab/codif-coicop-bdf) + [study on scanner data](https://arxiv.org/html/2005.11233v1) | fastText performed best on till data |
| [ONS ScannerAI](https://datasciencecampus.ons.gov.uk/scannerai-advancing-receipt-data-processing-with-ai/) | receipts → COICOP, template for pipeline and evaluation |
| [arXiv 2606.02004](https://arxiv.org/abs/2606.02004) | rules plus bag-of-words, similar to dictionary plus model here |
| [lxe/receipt-line-items-taxonomy](https://huggingface.co/datasets/lxe/receipt-line-items-taxonomy) | US-English, mostly synthetic receipt lines |
