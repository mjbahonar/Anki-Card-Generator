# Anki Card Generator

Turn your Excel list into a ready-to-import Anki deck, with dictionary meanings, examples and pronunciation. Start with words alone, or add typing, speaking, listening and gap exercises in the same workbook.

[راهنمای فارسی](README_fa.md) · [Technical guide](TECHNICAL.md) · [Release notes](CHANGELOG.md) · **v5.3.0**

## How it works

**Excel → selected dictionaries and audio → Anki deck → Anki / AnkiDroid**

The application reads your workbook, gathers content from the sources you enable, and builds cards with a shared style and dark mode. Successful dictionary results and media are cached for reuse. If a source fails, available results are still saved and issues are reported.

Norwegian and English have dedicated dictionary sources. Other languages can be used for exercises or compatible translation sources; choose the languages in `config.toml`.

## Build your first deck

Requires **Python 3.11+**. Download or clone this repository, then open a terminal in its folder.

**1. Install once**

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

**2. Add your words**

Copy `Template.xlsx` to `Input.xlsx`. Enter words below the `Word` header; the other columns can stay empty. A workbook with only a `Word` column also works.

![One-column Excel input and optional exercise columns](docs/images/excel-input-guide.png)

The German, Norwegian and French entries above illustrate the layout. Languages are configured for the run, not detected per row.

**3. Choose your settings**

Edit the existing sections in **`config.toml`**:

| Setting | What to choose |
| --- | --- |
| `input.file` | Your Excel file, such as `Input.xlsx` |
| `language.source` | Vocabulary language: `no` for Norwegian or `en` for English |
| `sources.*.enabled` | The dictionaries you want on your cards |
| `anki.deck_name` | Your deck name |
| `input.max_words` | `3` for a small trial; `0` for the full list |

The distributed configuration enables only **Lexin Bokmål–English**. For English, set the source language to `en` and enable compatible sources such as Cambridge, Oxford or Fastdic. Changing the language does not enable dictionaries automatically.

**4. Generate and import**

```powershell
python main.py --check
python main.py
```

Open the generated **`.apkg`** file from `Output` in Anki or AnkiDroid. It includes the card templates and referenced media. When updating an existing deck, keep your deck/model IDs fixed, regenerate and import the new package.

## Add more when you need it

Each Excel row becomes one card. Leave `Type` blank for vocabulary, or choose an exercise:

| Type | What you practice |
| --- | --- |
| `type` | Type the answer and compare it in Anki |
| `sentence` | Say a sample answer, then check it yourself |
| `gap` | Fill one or more `[...]` blanks |
| `listen` | Listen first, then reveal the text |

`Tag` organizes cards, `Answer` supplies exercise answers, and `Meaning` adds an optional personal meaning. Set exercise languages in `[practice]`; see the [exercise rules](TECHNICAL.md#exercise-cards) for required answers and examples.

You can also enable images, select and reorder dictionaries, and export a playable HTML preview or spreadsheet reports. All everyday settings live in `config.toml`; launch with `main.py`.

## Need help?

Run `python main.py --check` to validate your setup. For a missing browser, repeat the Chromium installation command above. Source failures are recorded in `Output/*_errors.json`.

See the [technical guide](TECHNICAL.md) for the dictionary catalog, advanced settings, audio, Anki compatibility, troubleshooting, cache maintenance and development. Version changes and migrations are in the [release notes](CHANGELOG.md).
