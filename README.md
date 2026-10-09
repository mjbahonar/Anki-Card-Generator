# Anki Card Generator — V4.0

[راهنمای فارسی](README_fa.md) · [Release notes](CHANGELOG.md)

Turn an Excel word list into styled Anki cards with definitions, examples, inflection tables and pronunciation. English and Norwegian share one application, one configuration file and one card style.

**Edit `config.toml`. Run `python main.py`. Import the generated `.apkg` into Anki or AnkiDroid.**

## What V4 includes

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

Put words in `New Words.xlsx`, one per row in the first column, without a header. The default settings create a new V4 deck, with Lexin first, Google translation to Persian and Dict.com. Source failures are reported while available results are saved.

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

In the same file, set `language.source = "en"`, select the desired input workbook, and enable sources such as `fastdic`, `cambridge`, `faraazin` or `b_amooz`. Set the audio priority to `["fastdic", "google_tts"]` if desired. Lexin is automatically skipped for English. To make a separate deck, set a different `deck_id` and `deck_name`; the unified V4 `model_id` can stay the same.

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

V4 has a new, fixed field schema and a new default model/deck ID. **Do not reuse a V3 model ID.** The initial V4 import creates a new deck; automatic migration of V3 notes is not included. The old editions remain available through Git tags (`v3.4`, `v3.4N`, `V3.5N`, `V3.6N`).

After the first V4 import, keep the deck/model IDs fixed. Disabling or reordering sources does not change the schema. Note GUIDs depend on the model, deck, language and normalized word, so changing definitions or audio does not create a new note. Use a new deck ID when you want an independent deck.

## Development

`main.py` runs the pipeline, `app_config.py` validates settings, `sources.py` contains the source catalog/adapters, `lexin_scraper.py` handles Lexin, and `anki_exporter.py` builds Anki cards. Imports do not start browsers or read input files. Browser resources are created on demand and closed after processing.

```powershell
python -m unittest test_v4 test_lexin_scraper -v
```

The old `main_script.py` and `main_script(word_by_word).py` filenames are small compatibility entry points that run the same V4 application and configuration.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| A dictionary is missing | Its `enabled` setting, language compatibility and the run's `*_errors.json` report |
| Google translation is empty | HTTP 429 or another source error; wait before retrying or disable this source |
| Browser unavailable | Run `python -m playwright install chromium` in the same Python environment |
| Wrong words or input error | `input.file`, `sheet`, `header` and `word_column`; run `python main.py --check` |
| A source stops returning content | The site's availability or changed markup; other sources can still complete |

V4 live checks covered Lexin, Dict.com, Fastdic and Cambridge. Faraazin is available in the source catalog but was disabled in the published English test preview, so that preview does not establish whether Faraazin is currently working.
