# License: Open Food Facts and the model file

## Result of the discussion with Open Food Facts

*Pending.*

## The question

The model is trained on product names and categories from Open Food Facts, Open Beauty Facts, Open Products Facts and Open Pet Food Facts. Their databases are under the **ODbL 1.0**, the individual entries under the **DbCL 1.0**. Product images are not used.

For training, the data is filtered, labelled and turned into receipt-style lines. That makes the training data a **Derivative Database**. It stays private (`data/`, not in the repository).

The model file (`pgm-*.bin`) is shipped in the app. **Is it a Produced Work in the sense of the ODbL?**

- **If yes** (our assessment), the model file and the app do not have to be under the ODbL. Two obligations remain:
  1. **§4.3 notice:** the app says that data from Open Food Facts is used under the ODbL, with a link ([text below](#notice-text-for-the-app)).
  2. **§4.6 method:** because it is a Produced Work *from a Derivative Database*, the method of making the alterations must be offered freely. That is this repository (scripts, mappings, lists, `data/raw/MANIFEST.json`). **So the repository must be public before the model is published**, in the app or as a release.
- **If no**, the model file would itself be a Derivative Database and would have to be published under the ODbL.

## Why we consider it a Produced Work

- It contains **no entries of the database**: no product names, brands, barcodes or categories in plain text. It holds 65,536 rows of 24 rounded numbers for hashed character n-grams, an output layer, our 46 class names and our list of retail chains.
- The database cannot be queried or recovered from it. One can only ask for a class for an input text. Over 100,000 product names are condensed into 1.5 million numbers, and through hashing many n-grams share the same row.
- It is the result of an analysis over the whole database, like a statistic or a map, which is the case the ODbL has in mind with a Produced Work.

Counter-argument: whether trained models are Produced Works is not settled. For large models that can reproduce entries verbatim, some take a different view. For a small model without plain text we consider it well defensible, but want it confirmed.

## Rules we follow to keep it that way

1. **No product names, brands or word lists** from Open Food Facts go into the model file, only hashed features.
2. The **app's dictionary is not extended from Open Food Facts data**; such a word list would be a Derivative Database.
3. Private labels, abbreviations, chains and test examples are **maintained by hand**, not exported from the databases.
4. **Not published:** `data/` and `dist/*.golden.tsv` (contains ~300 transformed product names; `tests/golden/` has only self-written lines).
5. Every published model is **reproducible** from the repository: data revision and checksums in the manifest, model version in the file and as a Git tag.

The repository's code is under GPL-3.0-or-later; the model files are deliberately not, and only the terms above apply to them.

## Notice text for the app

In the app's About dialog, together with the model version.

**German:**

> Die Erkennung der Warengruppen auf Kassenzetteln nutzt ein Modell, das mit Daten von Open Food Facts, Open Beauty Facts, Open Products Facts und Open Pet Food Facts erstellt wurde (https://openfoodfacts.org). Diese Daten stehen unter der Open Database License (ODbL). Wie das Modell aus den Daten erzeugt wird: https://codeberg.org/castn/product-group-modell. Modellversion ‹de-DE-2026.10.1›.

**English:**

> Item group recognition on receipts uses a model built with data from Open Food Facts, Open Beauty Facts, Open Products Facts and Open Pet Food Facts (https://openfoodfacts.org), made available under the Open Database License (ODbL). How the model is built from the data: https://codeberg.org/castn/product-group-modell. Model version ‹de-DE-2026.10.1›.
