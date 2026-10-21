# License: Open Food Facts and the model file

As of: October 2026. This is an assessment for development purposes, **not legal advice**. Before the first release in the app, the assessment should be confirmed with Open Food Facts (section "Open").

## Summary

- We classify the model file (`dist/pgm-*.bin`) as a **Produced Work** in the sense of the ODbL. It does not itself have to be under the ODbL. The app's license is not affected.
- Whoever publishes it (i.e. ships it in the app) must do two things:
  1. **Notice** in the app that data from Open Food Facts was used under the ODbL, with a link (§4.3 and the Open Food Facts terms of use).
  2. **Disclose the path from the original to our training data** (§4.6): the model is built from a derivative database (filtered, labelled, transformed). It is enough to offer the method freely on the internet. For us, that is this repository with scripts, mappings, lists and manifest. **So the repository must be public before the model appears in the app.**
- The raw data and all intermediate results in `data/` are not published. As long as that stays so, no further obligations arise from them.

## Sources and their licenses

| Source | used | License |
|---|---|---|
| Open Food Facts (database) | product names, categories, brands, countries, stores, quantity | database: ODbL 1.0, individual contents: DbCL 1.0 |
| Open Beauty Facts, Open Products Facts, Open Pet Food Facts | the same fields | like Open Food Facts |
| Category taxonomies (`categories.json` of the four projects) | parent relations, German category names | part of the database exports; we treat them like the database (ODbL) |
| Product images | **not used** | CC BY-SA |

The Open Food Facts terms of use require, on reuse, "to mention the license and attribute authorship to Open Food Facts, with a link to https://openfoodfacts.org". Derivative works should be shared under the same conditions.

## ODbL terms (excerpt)

- **Derivative Database:** a database based on the database, including as a translation, adaptation, arrangement or modification of its contents or structure.
- **Produced Work:** a work resulting from using the whole database or a substantial part of its contents, e.g. via queries.
- **Publicly:** towards persons other than oneself or persons under one's own control. An app in a store is public.
- **§4.3:** Whoever publicly uses a Produced Work must include a notice that makes users aware that contents come from the database and are available under this license. Example from the license: "Contains information from [DATABASE NAME], made available under the Open Database License (ODbL)."
- **§4.4:** A derivative database that is used publicly must be under the ODbL (or a compatible license).
- **§4.6:** "If You Publicly Use a Derivative Database or a Produced Work from a Derivative Database, You must also offer to recipients … a copy in a machine readable form of: a. The entire Derivative Database; or b. A file containing all of the alterations made to the Database or the method of making the alterations to the Database (such as an algorithm) … free of charge if distributed over the internet."

## Classification of our artefacts

| Artefact | Classification | public? | Consequence |
|---|---|---|---|
| `data/raw/*` (column extracts) | part of the database or Derivative Database | no | none |
| `data/interim/*`, `data/processed/*` (filtered, labelled, in receipt style) | Derivative Database | no | none, as long as not published |
| `models/*` (PyTorch weights) | Produced Work | no | none |
| `dist/pgm-*.bin` (model file for the app) | **Produced Work from a Derivative Database** | yes, with the app | notice (§4.3), disclose the method (§4.6) |
| `dist/pgm-*.golden.tsv` | contains ~300 transformed product names from Open Food Facts | no | do not ship with the app; `tests/golden/` is enough for tests |
| `mapping/off_to_class.yaml` | names about 370 category tags (insubstantial part) and our mapping | yes (repository) | unproblematic; part of the disclosed method |
| `mapping/classes.yaml`, `stores.yaml`, `augment/*`, `tests/golden/*` | written by us, no contents from Open Food Facts | yes | none |
| `data/eval/*` (real receipts) | no Open Food Facts data; personal data | no | never publish |

### Why the model file is a Produced Work (working hypothesis)

- It contains **no entries of the database**: no product names, brands, barcodes or categories in plain text. It contains 65,536 rows of 24 rounded numbers each for hashed character n-grams, an output layer, our 46 class names and our list of retail chains.
- The database cannot be queried or recovered from it. One can only ask for a class for an input text. Over 100,000 product names are condensed into 1.5 million numbers, and through hashing many character n-grams share the same row.
- It is the result of an analysis over the whole database, like a statistic or a map. This is the case the ODbL has in mind with the Produced Work.

Counter-argument: whether trained models are Produced Works is not conclusively settled. For large models that can reproduce entries verbatim, some take a different view. For our small model without plain text, we consider the classification well defensible. We should still get it confirmed.

## Design rules that safeguard the classification

1. **No product names, brands or word lists** from Open Food Facts go into the model file, only hashed features.
2. The **app's dictionary is not extended from Open Food Facts data**. A word list from the database would rather be a Derivative Database and would have to be published under the ODbL.
3. Private labels, abbreviations, chains and test examples are **maintained by hand**, not exported from fields like `brands` or `stores`.
4. `data/` and `dist/*.golden.tsv` are not published.
5. Every published model version must be reproducible from the state of the repository: manifest with revision and checksums (`data/raw/MANIFEST.json`), model version in the file and as a Git tag.

## License of this repository

Code, scripts and our own lists (`src/`, `scripts/`, `kotlin/`, `mapping/`, `augment/`, `tests/`, `docs/`) are under **GPL-3.0-or-later** ([LICENSE](../LICENSE)), like MyExpenses. So the Kotlin files can be taken into the app without further questions.

The **model files** (`pgm-*.bin`) are deliberately not under the GPL. On distribution, the GPL requires the preferred form for making modifications; for trained weights that would strictly speaking be the training data, which is not published (`data/`). For the model files the classification above applies: Produced Work, notice per §4.3, method disclosed via this repository per §4.6.

## Notice text for the app

In the About dialog (step 11), together with the model version. The store description does not need it, but it would not hurt.

**German:**

> Die Erkennung der Warengruppen auf Kassenzetteln nutzt ein Modell, das mit Daten von Open Food Facts, Open Beauty Facts, Open Products Facts und Open Pet Food Facts erstellt wurde (https://openfoodfacts.org). Diese Daten stehen unter der Open Database License (ODbL). Wie das Modell aus den Daten erzeugt wird: ‹Link zum Repository›. Modellversion ‹de-DE-2026.10.1›.

**English:**

> Item group recognition on receipts uses a model built with data from Open Food Facts, Open Beauty Facts, Open Products Facts and Open Pet Food Facts (https://openfoodfacts.org), made available under the Open Database License (ODbL). How the model is built from the data: ‹link to repository›. Model version ‹de-DE-2026.10.1›.

## Before the first release

- [x] License for code and own lists: GPL-3.0-or-later like the app (section "License of this repository").
- [ ] Make the repository public.
- [ ] Model version as a Git tag; in the tag text the revision of the raw data from the manifest.
- [ ] Notice text in the About dialog with link to the repository and model version.
- [ ] Do not take `dist/*.golden.tsv` into the app.
- [ ] Ask Open Food Facts about the classification (see below) and note the answer here.

## Open

- **Inquiry with Open Food Facts**, via the contact options on openfoodfacts.org. Suggested question: "We train a small classification model (hashed character n-grams, no product names in the model) on product names and categories and ship it in an open-source app. Do you share the classification as a Produced Work with a notice per §4.3 and disclosure of the method per §4.6 via a public repository?"
- The **taxonomies** are also in the Open Food Facts code repository, which itself is under the AGPL. But we load them from the data exports and only use names and parent relations as data, not the code. This should be clarified in the inquiry as well.
