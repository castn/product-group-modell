# product-group-modell

`pgm` stands for **p**roduct-**g**roup-**m**odell: that is the name of the Python and the Kotlin package, the magic `PGM1` in the file header and the model files `pgm-*.bin`.

A small model that assigns item names from receipts to an item group of the app (MyExpenses, `ItemGroup`).
It learns from Open Food Facts, Open Beauty Facts, Open Products Facts and Open Pet Food Facts, is trained in Python, and in the app is computed with the same weights by a Kotlin implementation without libraries.

```
"JA! H-Milch 1L"       ──►  milch_sahne → dairy,  confidence 1.00  →  SURE
"Bio Vollmilch 3,5%"   ──►  milch_sahne → dairy,  confidence 0.85  →  SUGGESTION
```

**Status (October 2026):** The first German version is trained, exported (1.84 MB, still under the old name `2026.10-de-1`) and recomputed in Kotlin. The guide for integrating it into the app is written, the integration itself is not done yet.

## Results so far

On 107 rows of real receipts that the app's dictionary does not know (item group level):

| Variant | with suggestion | of which correct |
|---|---:|---:|
| dictionary → merchant (in the app today) | 79 % | 85 % |
| model alone from 0.9 | 52 % | 95 % |
| **model from 0.5 → dictionary → merchant** | **94 %** | **88 %** |
| **model from 0.7 → dictionary → merchant** | **92 %** | **91 %** |
| dictionary → model from 0.5 → merchant | 95 % | 84 % |

These are few rows (±6 percentage points), and two improvements were made after looking at exactly these rows. A clean final evaluation still needs an untouched batch (goal: ≥ 1,000 rows from ≥ 5 chains).

The thresholds in the model file: `t_sure = 0.9` (SURE), `t_suggest = 0.5` (SUGGESTION), below that `null` and the app asks the dictionary.

## How it works

- **Normalization:** NFKC, spell out umlauts (`ä→AE`, `ß→SS`), remove accents, upper case, only `A–Z 0–9 % , . - ! &`. The result is ASCII, Python and Kotlin are identical char by char.
- **Features:** words, character n-grams of length 2–5, word pairs and optionally `__store=<CHAIN>` (chains from `mapping/stores.yaml`). Numbers and units do not count. Hash: FNV-1a 32 bit, `mod 2^16`.
- **Model:** fastText style (PyTorch `EmbeddingBag` + `Linear`, dim 24): average the feature vectors, output matrix, softmax with temperature.
- **Two levels:** the model learns 46 **fine classes** (`mapping/classes.yaml`), the app shows 15 **item groups** (`mapping/groups.yaml`). The mapping class → group is stored in the model file and can be changed without retraining. `deposit` stays a rule in the app, `other` is only chosen by the user.
- **Training data:** product names with a class from the category mapping, plus receipt-style variants (abbreviations, private labels, quantities, price remnants, text recognition errors, truncation). Split into training and validation per product, before augmentation.
- **Model file:** feature vectors as `int8` with a scale per row, plus classes, groups, thresholds and chain table, CRC-32 at the end.

Specified in binding form in [docs/interface.md](docs/interface.md) (normalization, features, computation, file format).

## Setup

Requirements: [uv](https://docs.astral.sh/uv/) (Python ≥ 3.12, PyTorch CPU only), for Kotlin a JDK 25.

```sh
uv sync
uv run pytest                    # normalization, features, export against tests/golden/
cd kotlin && ./gradlew test      # Kotlin against tests/golden/ and all models in dist/
```

## Pipeline

All intermediate results end up in `data/`, `models/`, `reports/` and `dist/` (not in the repo).

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

Useful options:
- `fetch.py --limit N` for a quick test run, `--only food,tax-food` for individual sources, `--revision <commit>` to resume a download.
- `train.py --dim --buckets --minn --maxn --[no-]bigrams --[no-]store --epochs --lr --seed` (defaults as in `dev4`: dim 24, 2^16 buckets, 2–5, word pairs and store on).
- `export.py --market de-DE` (default) and `--release YYYY.MM.N` give the name `pgm-f<format>-<market>-<release>.bin`; scheme in [docs/interface.md](docs/interface.md#versions-and-file-names). `--t-sure --t-suggest` set the thresholds in the file.
- `release.py` checks the model file (header, CRC, Kotlin test, clean working tree) and stores the model, checksum (`<file>.sha256`) and the release text `RELEASE.md`. The golden values from `dist/` are not included (license). At the end it prints the commands for tagging and uploading to Codeberg.
- `scripts/baseline.py` measures the app's dictionary alone. Run `cd kotlin && ./gradlew :baseline:installDist` first; it needs the app's code in `kotlin/app-snapshot/`.

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

Always change normalization or features in Python **and** Kotlin, with new golden values in `tests/golden/` (`src/pgm/golden.py`).

## Test data

Real receipts scanned with the app in `data/eval/` (photo, text recognition, expected parser result, labelling with fine class), merged into `data/eval/receipts.csv` (`receipt;merchant;name;amount;class;dictionary_seen`).

- **Personal data, never in the repo**, never for training, abbreviation lists or mapping.
- `reports/eval-*.md` contains rows from it, do not commit either.
- `dictionary_seen = ja`: receipts from which the app's dictionary was built. The remaining ones are the meaningful ones.
- As of 2026-10-03: 186 rows from 25 receipts, of which 107 rows from 15 receipts unknown to the dictionary (mostly REWE).

## Integration into the app

Guide: [docs/app-integration.md](docs/app-integration.md). Order of the sources:

```
RULE → PRODUCT → WORDS → MODEL → DICTIONARY → MERCHANT
```

- Take over `Normalize.kt`, `Features.kt`, `ProductGroupModel.kt` from `kotlin/reference/src/main/kotlin/pgm/` unchanged (only adjust `package`), model as asset `item_groups/model.bin`.
- API: `ProductGroupModel.load(bytes)`, then `classify(name, store)` → `GroupPrediction(classId, groupId, confidence, level)` or `null`, plus `topK(name, store, k)`. About 0.1 ms per row on the desktop.
- If the model is missing or does not fit, the app works as before.
- Python counterpart for recomputing: `pgm.export.read` and `pgm.export.probabilities`.

## License

Worked out in [docs/license.md](docs/license.md) (not legal advice):

- The data is under ODbL 1.0 (database) and DbCL 1.0 (contents).
- The model file counts as a **Produced Work** (working hypothesis): no entries in plain text, only hashed features.
- Because it is built from a derivative database, the method must be freely available: **this repository becomes public before the model appears in the app.**
- The app needs a notice with a link in its About dialog (text in `docs/license.md`).
- The inquiry with Open Food Facts about the classification is still pending.

Code, scripts and our own lists in this repository (`src/`, `scripts/`, `kotlin/`, `mapping/`, `augment/`, `tests/`, `docs/`) are, like the app, under the **GNU General Public License, version 3 or later** ([LICENSE](LICENSE)). The model files (`pgm-*.bin`) are not covered by it; [docs/license.md](docs/license.md) applies to them.

## Project structure

```
├── docs/            interface.md (specification), license.md, app-integration.md
├── mapping/         item groups, classes, category mapping, chains
├── augment/         abbreviations and private labels for the receipt style
├── src/pgm/         normalize, features, categories, augment, stores, model, export, evaldata, golden
├── scripts/         fetch, extract_de, mapping_report, build_dataset, train, evaluate, export, baseline
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

## Open

- Another batch of real receipts for an unbiased final evaluation and the calibration of the thresholds.
- Integration into the app per [docs/app-integration.md](docs/app-integration.md); publish the repository first.
- Script that updates `kotlin/app-snapshot/` from a checkout of the app and records repository, branch and commit in `SOURCE` (by hand so far).
- Shipped with the app or downloaded later (own versioning, update without an app release)?
- Further languages (fr/it/es/en) in **one** model under 2 MB, with its own abbreviations and private labels per language. Without real receipts in these languages there are only figures on generated data; the German result must not get worse.

## Related work

At the time of research (October 2026) there was no ready-made, open model for German receipt lines that is small enough for an app.

- [openfoodfacts/category_classifier](https://huggingface.co/openfoodfacts/category_classifier): categories for Open Food Facts, needs ingredients, nutrition facts and images, too large, archived.
- [InseeFrLab/torchTextClassifiers](https://github.com/InseeFrLab/torchTextClassifiers): fastText in PyTorch; alternative to our own trainer.
- [INSEE codif-coicop-bdf](https://github.com/InseeFrLab/codif-coicop-bdf) and the [study on scanner data](https://arxiv.org/html/2005.11233v1): fastText performed best on till data.
- [ONS ScannerAI](https://datasciencecampus.ons.gov.uk/scannerai-advancing-receipt-data-processing-with-ai/): receipts → COICOP, template for pipeline and evaluation.
- [arXiv 2606.02004](https://arxiv.org/abs/2606.02004): rules plus bag-of-words, similar to dictionary plus model here.
- [lxe/receipt-line-items-taxonomy](https://huggingface.co/datasets/lxe/receipt-line-items-taxonomy): US-English, mostly synthetic receipt lines.
