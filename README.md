# Anki Card Generator — v5.0.0 (unreleased)

Oxford is enabled for English in `[sources.oxford]`; `examples_per_definition = 3` limits examples for each main definition. It follows exact same-word entry links to collect all available parts of speech, without including compounds. It uses direct HTML requests and downloads no Oxford audio. Fastdic/Google TTS remain the audio providers.

**V5 migration:** adding Oxford changes the fixed Anki schema. Defaults now use model `1559328450` and deck `2059400450`. Import into this new deck; do not reuse a V4 model ID or expect automatic migration of review history. Existing V4 decks remain available. Keep the new IDs fixed after the first V5 import, regardless of source toggles.

[راهنمای فارسی](README_fa.md) · [Release notes](CHANGELOG.md)

Turn an Excel word list into styled Anki cards with definitions, examples, inflection tables and pronunciation. English and Norwegian share one application, one configuration file and one card style.

**Edit `config.toml`. Run `python main.py`. Import the generated `.apkg` into Anki or AnkiDroid.**

## What the application includes

- Dictionary selection and display order without editing Python or Anki templates.
- Norwegian Lexin entries with inflections, plus English dictionary sources and configurable translation.
- Headword pronunciation with provider priority, fallback and cached downloads.
- Excel, CSV, Anki packages, playable HTML previews and JSON reports.
- A shared card style with dark mode and an English About block at the bottom.
- Source error handling, recovery saves and stable Anki note identities.

## Install and run

Requires Python **3.11+**. No Selenium, ChromeDriver or `.env` configuration is needed.

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python main.py --check
python main.py
```

Put words in `New Words.xlsx`, one per row in the first column, without a header. The default settings create a new V5 deck, with Lexin first, Google translation to Persian and Dict.com. Source failures are reported while available results are saved.

Generated files appear in `Output`. Start with `input.max_words = 3` for a small trial; set it to `0` to process the entire list.

## All user settings are in config.toml

| Section | Settings |
| --- | --- |
| `language` | Input language (`no` or `en`, etc.) and translation target (`fa`, etc.) |
| `input` | Excel file, sheet name/index, header, column name/index, duplicate removal and word limit |
| `sources.*` | Enable/disable each dictionary; section order controls display order |
| `audio` | Enable audio, provider priority, US/UK accent, media directory, caching and optional copy to Anki media |
| `output` | Directory, filename prefix, selected formats and recovery autosave interval |
| `anki` | Deck name, deck ID and model ID |
| `style` | Shared CSS file (`Styles/cards.css`) |
| `runtime` | Network timeout, translation retry policy, delay, headless browser and keep-awake |
| `info` | English footer text and link, or disable it |

Relative paths are resolved from the configuration file's directory, regardless of the working directory. Sheet/column indices start at **0**. A column name requires `header = true`.

### Switching to English

In the same file, set `language.source = "en"`, select the desired input workbook, and enable sources such as `fastdic`, `cambridge`, `faraazin` or `b_amooz`. Set the audio priority to `["fastdic", "google_tts"]` if desired. Lexin is automatically skipped for English. To make a separate deck, set a different `deck_id` and `deck_name`; the unified V5 `model_id` can stay the same.

For example, change the existing settings to these values:

```toml
[language]
source = "en"
translation_target = "fa"

[sources.fastdic]
enabled = true
examples_per_definition = 3

[sources.faraazin]
enabled = true

[sources.cambridge]
enabled = true
examples_per_definition = 3
```

Edit the existing sections rather than adding duplicate TOML sections. Dictionary sources are opt-in: changing the language does not automatically enable every compatible provider.

### Dictionary catalog

| Source | Supported input | Content |
| --- | --- | --- |
| `lexin` | Norwegian | First exact Bokmål headword: explanations, inflections, examples, idioms and compounds |
| `google_translate` | Configurable | Translation to `language.translation_target` |
| `dict_com` | Norwegian / English | Translations and phrases in the other language |
| `fastdic`, `faraazin`, `b_amooz` | English | Persian meanings |
| `dictionary_com`, `cambridge` | English | English definitions |
| `oxford` | English | Oxford Learner's main definitions and examples; no Oxford audio |
| `thesaurus` | English | Synonyms / antonyms |
| `google_dictionary` | English | Google's dictionary result |
| `images` | Configurable | Downloaded image results; `count` controls the limit |

Fastdic and Cambridge keep their definitions and show up to `examples_per_definition` examples per definition (default: 3). Set it to 0 for definitions only. Site advertisements and navigation controls are excluded.

Sources incompatible with the selected language are skipped. Availability depends on the websites; markup changes or service restrictions are recorded as source warnings. Google Translate can return HTTP 429; retries are bounded and its failure does not stop other sources. Legacy providers have adapters, but not every provider has been live-tested in V4; see the release notes.

### Output and audio

Choose any subset of `xlsx`, `csv`, `apkg`, `html` and `json`. The HTML preview includes playable audio. JSON includes source errors; a separate `*_errors.json` is written when issues occur. Recovery CSV files save progress every `autosave_every` words; set it to `0` to disable. Ctrl+C saves partial results.

For example, `formats = ["apkg", "html"]` creates just an Anki package and a preview. The input filename, sheet and word column are independent of the chosen output formats.

Only the input headword's pronunciation is downloaded. Provider priority is independent of the visible dictionary list. Norwegian defaults to Lexin with Google TTS fallback; English can use Fastdic with a selected US/UK accent and Google TTS fallback. Cached audio is reused. Anki packages include only referenced media and the font, rather than the entire media directory. Lexin/Google audio is synthesized speech.

### Anki identity and previous versions


After the first V5 import, keep the deck/model IDs fixed. Disabling or reordering sources does not change the schema. Note GUIDs depend on the model, deck, language and normalized word, so changing definitions or audio does not create a new note. Use a new deck ID when you want an independent deck.

## Development

`main.py` runs the pipeline, `app_config.py` validates settings, `sources.py` contains the source catalog/adapters, `lexin_scraper.py` handles Lexin, and `anki_exporter.py` builds Anki cards. Imports do not start browsers or read input files. Browser resources are created on demand and closed after processing.

```powershell
python -m unittest test_v4 test_lexin_scraper -v
```

`main.py` is the only application entry point. Obsolete V3 launchers, styles, screenshots and documentation have been removed. Only the English and Persian README files are maintained.

| File | Purpose |
| --- | --- |
| `config.toml` | The only file you edit for everyday settings |
| `main.py` | The only file you run |
| `app_config.py` | Configuration validation |
| `sources.py` | Dictionary and audio adapters |
| `lexin_scraper.py` | Lexin-specific extraction |
| `anki_exporter.py` | Stable Anki model and package generation |
| `console_report.py` | Console progress and final run summary |
| `Styles/cards.css` | The shared card style |
| `test_v4.py`, `test_lexin_scraper.py` | Automated tests |

Release tags now follow `vMAJOR.MINOR.PATCH`, without language suffixes. Historical tags are preserved. See [the release policy](RELEASING.md).

## Troubleshooting

Images use `sources.images.priority = ["google", "commons"]`: try Google first, then Wikimedia Commons when Google is unavailable or fewer images were downloaded. Set `enabled = true` and `count = 3` to enable images; `["commons"]` skips Google. Images are stored locally and bundled into Anki, with Commons attribution/license text. Results are automatic and may need review for ambiguous words.

Dict.com currently uses the English–Norwegian pair: English input returns Norwegian meanings, not Persian. Disable it for an English–Persian deck; use Fastdic for Persian meanings and Cambridge for English definitions.

Each word shows `OK`, `EMPTY` or `FAIL` for each source, its elapsed time and audio status. The final console report lists per-source totals, words saved, audio coverage, issues and output paths. Failed sources remain empty and are hidden on cards; available sources are still exported. Detailed errors are saved in `*_errors.json`. Interrupted or unexpectedly stopped runs save available rows with a `_partial` suffix. Export/report failures return exit code 1; interruption returns 2; completed runs (including source warnings) return 0.

| Symptom | What to check |
| --- | --- |
| A dictionary is missing | Its `enabled` setting, language compatibility and the run's `*_errors.json` report |
| Google translation is empty | HTTP 429 or another source error; wait before retrying or disable this source |
| Browser unavailable | Run `python -m playwright install chromium` in the same Python environment |
| Wrong words or input error | `input.file`, `sheet`, `header` and `word_column`; run `python main.py --check` |
| A source stops returning content | The site's availability or changed markup; other sources can still complete |

V4 live checks covered Lexin, Dict.com, Fastdic and Cambridge. Faraazin was also enabled in a later three-word test, but both its `www` and bare hostnames failed DNS resolution in the test environment. This does not establish geographic blocking. Try another network or DNS resolver before attributing the issue to location; no Faraazin content was retrieved.
