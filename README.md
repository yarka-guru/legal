# Legal — yarka.guru

Legal documents for yarka.guru apps at https://legal.yarka.guru/.
Texts are licensed under CC BY 4.0 (see LICENSE). No documents are published yet.

GitHub Pages builds plain Jekyll from branch `main`, path `/`, using its default
plugins. There is no theme, custom build workflow, or dependency installation.

Run the source checks locally with Python 3 (standard library only):

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_site.py
# Optionally check another source tree:
python3 scripts/check_site.py /path/to/site
```

The checker validates source links, metadata, translations, and forbidden content;
it does not render Jekyll. Dynamic Liquid links are skipped when they cannot be
resolved statically. Config lists support inline and block syntax; page metadata
uses flat plain or quoted scalars.

The first entry in `_config.yml`'s `languages` is the default language: English at
the root, Spanish under `/es/`. Keep matching source paths in each language:
`sxnts/index.md` → `/sxnts/`, `es/sxnts/index.md` → `/es/sxnts/`.
Future `sxnts/privacy.md` and `es/sxnts/privacy.md` will publish at
`/sxnts/privacy/` and `/es/sxnts/privacy/`.

Unversioned URLs always show the current version. Keep old versions at paths such
as `/sxnts/privacy/v1/` and `/es/sxnts/privacy/v1/`. Every content page needs
`layout: default`, `title`, `lang`, and `last_updated` (YYYY-MM-DD). Legal document
pages additionally use `document: true`, `version`, and `effective_date`
(YYYY-MM-DD). Publish counterparts in every configured language and record changes
in each language's changelog. Legal documents require owner approval.
