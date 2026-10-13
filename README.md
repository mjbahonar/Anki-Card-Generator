# Anki Card Generator

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

Put words in `New Words.xlsx`, one per row in the first column, without a header. The default settings enable only Lexin Bokmål–English. All other source sections remain available with enabled = false. Source failures are reported while available results are saved.

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

`runtime.source_timeout_seconds = 30` sets a shared time budget for each word/source, including retries, multiple entry pages and inflection waits. Each network operation uses the remaining budget; after it expires the source is skipped and processing continues. `0` disables this budget. `runtime.timeout_seconds = 30` separately limits an individual network operation and also applies to audio requests. Cleanup and local processing may add a little time beyond the network budget.

### Switching to English

In the same file, set `language.source = "en"`, select the desired input workbook, and enable sources such as `oxford`, `fastdic`, `cambridge`, `faraazin` or `b_amooz`. Set the audio priority to `["fastdic", "google_tts"]` if desired. Lexin is automatically skipped for English. To make a separate deck, set a different `deck_id` and `deck_name`; the shared `model_id` can stay the same.

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
| `lexin` | Norwegian | First exact Bokmål/Nynorsk headword: explanations, inflections, examples, idioms and compounds |
| `google_translate` | Configurable | Translation to `language.translation_target` |
| `dict_com` | Norwegian / English | Translations and phrases in the other language |
| `fastdic`, `faraazin`, `b_amooz` | English | Persian meanings |
| `dictionary_com`, `cambridge` | English | English definitions |
| `oxford` | English | Oxford Learner's main definitions and examples; no Oxford audio |
| `bokmalsordboka` | Norwegian | Bokmål articles and expanded inflection tables |
| `nynorskordboka` | Norwegian | Nynorsk articles and expanded inflection tables |
| `thesaurus` | English | Synonyms / antonyms |
| `google_dictionary` | English | Google's dictionary result |
| `images` | Configurable | Downloaded image results; `count` controls the limit |

Fastdic, Cambridge and Oxford keep their definitions and show up to `examples_per_definition` examples per definition (default: 3). Set it to 0 for definitions only. Site advertisements and navigation controls are excluded.

Sources incompatible with the selected language are skipped. Availability depends on the websites; markup changes or service restrictions are recorded as source warnings. Google Translate can return HTTP 429; retries are bounded and its failure does not stop other sources.

Oxford collects all available parts of speech for the exact headword. Bokmålsordboka and Nynorskordboka include expanded inflection tables and preserve bold/italic emphasis. Nynorsk spelling may differ from Bokmål, so some input words may have no exact Nynorsk entry.

### Output and audio

Choose any subset of `xlsx`, `csv`, `apkg`, `html` and `json`. The HTML preview includes playable audio. JSON includes source errors; a separate `*_errors.json` is written when issues occur. Recovery CSV files save progress every `autosave_every` words; set it to `0` to disable. Ctrl+C saves partial results.

For example, `formats = ["apkg", "html"]` creates just an Anki package and a preview. The input filename, sheet and word column are independent of the chosen output formats.

Only the input headword's pronunciation is downloaded. Provider priority is independent of the visible dictionary list. Norwegian defaults to Lexin with Google TTS fallback; English can use Fastdic with a selected US/UK accent and Google TTS fallback. Cached audio is reused. Anki packages include only referenced media and the font, rather than the entire media directory. Lexin/Google audio is synthesized speech.

### Anki identity

After the first import, keep the deck/model IDs fixed. Disabling or reordering sources does not change the schema. Note GUIDs depend on the model, deck, language and normalized word, so changing definitions or audio does not create a new note. Use a new deck ID when you want an independent deck.

## Development

`main.py` runs the pipeline, `app_config.py` validates settings, `sources.py` contains the source catalog/adapters, `lexin_scraper.py` handles Lexin, and `anki_exporter.py` builds Anki cards. Imports do not start browsers or read input files. Browser resources are created on demand and closed after processing.

```powershell
python -m unittest test_v4 test_lexin_scraper -v
```

`main.py` is the application entry point. Use `config.toml` for everyday settings.

| File | Purpose |
| --- | --- |
| `config.toml` | The only file you edit for everyday settings |
| `main.py` | The only file you run |
| `app_config.py` | Configuration validation |
| `sources.py` | Dictionary and audio adapters |
| `lexin_scraper.py`, `oxford_scraper.py`, `ordbokene_scraper.py` | Dictionary-specific extraction |
| `image_sources.py` | Google/Commons image downloading |
| `anki_exporter.py` | Stable Anki model and package generation |
| `console_report.py` | Console progress and final run summary |
| `Styles/cards.css` | The shared card style |
| `test_v4.py`, `test_lexin_scraper.py` | Automated tests |

See [release notes](CHANGELOG.md) for version changes and migration details, and [the release policy](RELEASING.md) for publishing conventions.

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

Lexin supports `variant = "bokmal"`, `"nynorsk"` or `"both"` in `[sources.lexin]`. With no variant, `nn` input uses Nynorsk and other Norwegian input uses Bokmål. Both entries share the existing Lexin field, preserving the Anki schema and note identity. Audio follows the input variety (or Nynorsk when explicitly selected).


### Mixed exercise cards

Excel may contain four adjacent columns starting at `input.word_column`: **input | type | tags | answer**. Existing one-column workbooks continue to work; blank type means `normal`. Type names are case-insensitive. Comma-separated input tags are merged with the automatic type tag; whitespace within a tag becomes an underscore. Each `[cards.<type>]` section allows editing `title`, `instruction`, `tag`, and `audio`. Leave the normal title/instruction blank to retain the vocabulary front.

| Type | Input | Answer column | Audio |
| --- | --- | --- | --- |
| `normal` or blank | Dictionary headword | Optional, unused | Existing vocabulary pronunciation; default Lexin then gTTS |
| `type` | Meaning/prompt, e.g. house | Required: hus | Answer on back; native Anki typing comparison |
| `sentence` | Prompt sentence | Required: sample translation | Sample answer on back; self-assessed speaking |
| `gap` | Sentence containing `[…]` or `[...]` | Required: missing text | Completed sentence on back; recall then reveal |
| `listen` | Sentence in the practised language | Optional: translation in question language | Front audio, hidden text; text and repeat audio on back |

Unknown types, missing required answers, and gaps without the marker are skipped with Excel row numbers and a saved error report. Listening cards with disabled/failed audio are skipped. Blank optional columns never invalidate a normal card. Duplicate checking includes exercise type and language pair; answer edits keep exercise identity stable. First duplicate wins. Change the question/type/language pair to create a different exercise.

`[practice]` sets `question_language` and `answer_language`, independently of dictionary `language.source`/`translation_target`. Codes such as EN/NO/FA are accepted. Instructions remain English; `{question_language}` and `{answer_language}` insert display names. Optional `[practice.language_names]` overrides names for other codes. Changing languages does not translate Excel content. Persian/Arabic/Hebrew/Urdu exercise text and the typing input use RTL, while English headings stay LTR.

Exercise audio uses gTTS directly, with a language/text-specific cache and global plus per-type audio switches. For `nb`/`nn`, gTTS uses generic Norwegian `no`; there is no dedicated Nynorsk voice. Anki's review preferences control automatic playback. No microphone recording, speech recognition, translation generation, or automatic speaking grading is performed.

**Anki compatibility:** the original V5 vocabulary model, fields, GUIDs and source ordering behavior are retained. Four separate additive models (`Vocabulary Exercise · type/sentence/gap/listen`) use IDs starting at `practice.model_id_base`; keep this base fixed after import. There is no migration of existing vocabulary notes and no existing model schema is replaced. All five types go in the same deck. New models are included when that type is present in APKG.

The regular CSV/XLSX remain analysis exports. Every CSV export also writes `*_anki.csv`, with note-type/HTML/tag/GUID import headers and positional fields. Import the APKG first to install the matching exercise models; then import this companion CSV in Anki Desktop (2.1.54+) to update notes. Select the intended deck. Keep the GUID and identity fields unchanged to update the same notes as APKG. CSV does not carry templates, CSS or media; audio must be available in `collection.media` (APKG includes referenced media). Use APKG for the easiest complete import. HTML preview includes fronts and revealed answers; it is not a quiz.

Validation: `python -m unittest test_v4 test_lexin_scraper test_exercises -v` and `python main.py --check`.

Set `input.order = "excel"` (default) to preserve worksheet order, or `"random"` to shuffle complete records on each run before fetching/exporting. The workbook is unchanged and answers/tags stay with their questions. `max_words` selects the first valid records before shuffling. This controls generation order; Anki review order is configured separately in Anki.

Multi-blank `gap` exercises stay on one card. Put each answer on its own line in the Answer cell, in blank order (Excel: Alt+Enter). Both […] and [...] markers can be mixed. Counts must match and answer lines must not be empty; otherwise the row is skipped with a report. The back shows the complete text with highlighted answers and preserved line breaks. Audio reads the completed text. Grade the entire exercise yourself. Commas are literal answer text, not separators.

Gap fronts now have one editable input per blank (including Preview); grading remains manual for the entire exercise. The native `type` comparison input appears during actual Anki review, not in Anki’s Preview dialog. Re-run and import the new APKG to update existing templates/content.

**AnkiDroid keyboard:** If tapping a gap input focuses it but does not open the keyboard, enable **Settings → Advanced → Workarounds → Type answer into the card**, then leave and reopen the review screen. This setting resolved the issue on a tested Android device. The option's location/name may vary by AnkiDroid version. See the [AnkiDroid manual](https://docs.ankidroid.org/#_workarounds).


Set `[sources.lexin] table_audio = true` to include pronunciation controls only for inflection-table forms in the exact Lexin entry. The global audio switch also applies. Files are cached and bundled; table controls do not autoplay. Set it to false for text-only tables. Additional network work shares the source time budget; increase it for large tables. Example/idiom pronunciation is excluded.

Lexin table pronunciation prefers the original Lexin audio, with a short per-control wait and gTTS fallback if it is unavailable. These controls never play all forms automatically. The `type` template uses only one native comparison, inherited on the back through FrontSide.

Lexin table audio uses compact replay buttons rather than media-player bars, with no autoplay. Gap questions and completed answers align to the text direction (LTR left, RTL right); speaking answers omit the sample-answer notice.

Shared media destination: set `[media] anki_directory = "C:/.../collection.media"` once near the top of config.toml. Audio and images keep their local originals and are copied there, including cached audio and table pronunciation. Blank disables external copying. Legacy audio.copy_to remains supported when the media section is absent. Use forward slashes in double-quoted TOML paths, or single quotes for literal Windows backslashes.

Native typing accepts one answer line; multiline type answers are skipped with a reason. Typing direction is note-specific so importing another practice language does not change older cards. The exercise audio status and failures are shown in the console.
