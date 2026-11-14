---
name: nibe-registers
description: Add or fix heat-pump register metadata in extensions.json and regenerate model JSONs from CSVs.
---

# NIBE register updates

- Read README.md's register-update instructions and the relevant entries in
  `nibe/data/extensions.json`.
- CSVs are vendor source data: do not patch their existing values to fix metadata.
  Model JSONs are generated: do not hand-edit them.
- Put corrections and missing register definitions in `extensions.json`.
  Each entry has `description`, `files` (model JSON filenames), and `data`
  (register-address strings mapped to metadata).
- Reuse an existing override by extending its `files` list; do not duplicate
  overrides per model. For models with confirmed shared firmware, compare both
  address and title before sharing a correction. Do not infer missing
  register support from an address alone. Preserve existing register names.

## Generate and validate

Use the existing project environment. If conversion dependencies are missing,
create a virtualenv and install `python -m pip install -e '.[convert]'`.
Run from the repository root with that environment's Python:

```bash
python -m nibe.console_scripts.convert_csv
python -m nibe.console_scripts.convert_csv --verify
git diff --stat
git diff -- nibe/data
```

Conversion processes every CSV. Confirm both commands succeed, the intended
registers have the expected metadata, and the diff contains no unrelated changes.
If regeneration exposes existing drift, compare against the pre-change baseline
in isolation; report it rather than silently accepting deletions or losing local
work. Keep the shared overrides and their generated JSON changes together.
