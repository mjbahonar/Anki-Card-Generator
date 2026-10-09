# Repository instructions

- Maintain the unified V4 application: `config.toml` is the user settings file and `main.py` is the only supported launcher.
- Preserve the current shared appearance in `Styles/cards.css`; Info remains English and last.
- Maintain only `README.md` and `README_fa.md` as README languages.
- Do not delete user Excel workbooks during cleanup.
- Follow `RELEASING.md` for every release. New tags must be annotated lowercase `vMAJOR.MINOR.PATCH`, with no language suffix. Runtime version, changelog and GitHub release must agree. Never rewrite published tags.
- Keep the Anki field schema and note identity stable across dictionary toggles and ordering. Treat incompatible schema changes as major-version changes and document migration.
