# Technical guide

[Getting started](README.md) · [راهنمای فنی فارسی](docs/technical_fa.md)

Advanced configuration, source behavior, exercise rules, cache maintenance and development. For installation and your first deck, start with the README.

## Contents

- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Exercise cards](#exercise-cards)
- [Lexin table pronunciation](#lexin-table-pronunciation)
- [Shared media destination](#shared-media-destination)
- [Dictionary cache and maintenance](#dictionary-cache-and-maintenance)
- [Development](#development)

## Configuration

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

In the same file, set `language.source = "en"`, select the desired input workbook, and enable sources such as `oxford`, `fastdic`, `cambridge`, `faraazin` or `b_amooz`. Headword audio follows `[audio.word]` for the input language (`en = ["fastdic", "google_tts"]` by default; `[]` disables it). Lexin is automatically skipped for English. To make a separate deck, set a different `deck_id` and `deck_name`; the shared `model_id` can stay the same.

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
| `lexin` | Norwegian | Up to two exact Bokmål/Nynorsk headword entries: explanations, inflections, examples, idioms and compounds |
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

Choose any subset of `xlsx`, `csv`, `apkg`, `html` and `json`. Files are named `<input workbook>_<filename_prefix>_<date-time>`. The HTML preview includes playable audio. JSON includes source errors; a separate `*_errors.json` is written when issues occur. Recovery CSV files save progress every `autosave_every` words; set it to `0` to disable. Ctrl+C saves partial results.

For example, `formats = ["apkg", "html"]` creates just an Anki package and a preview. The input filename, sheet and word column are independent of the chosen output formats.

Only the input headword's pronunciation is downloaded. `[audio.word]` chooses providers per `language.source` (`lexin`, `fastdic`, `google_tts`; the first success wins, `[]` disables headword audio); `nb`/`nn` use the `no` list and unlisted languages use `audio.priority`. `cards.normal.audio = false` turns headword audio off for every language. Provider priority is independent of the visible dictionary list. Norwegian defaults to Lexin with Google TTS fallback; English defaults to Fastdic with a selected US/UK accent and Google TTS fallback. Cached audio is reused. Anki packages include only referenced media and the font, rather than the entire media directory. Lexin/Google audio is synthesized speech.

### Anki identity

After the first import, keep the deck/model IDs fixed. Disabling or reordering sources does not change the schema. Note GUIDs depend on the model, deck, language and normalized word, so changing definitions or audio does not create a new note. Use a new deck ID when you want an independent deck.

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

## Exercise cards

Excel may contain five adjacent columns starting at `input.word_column`: **input | type | tags | answer | meaning**. Existing one-column and four-column workbooks continue to work; blank type means `normal`. Type names are case-insensitive. Comma-separated input tags are merged with the automatic type tag; whitespace within a tag becomes an underscore. Each `[cards.<type>]` section allows editing `title`, `instruction`, `tag`, and `audio`. Leave the normal title/instruction blank to retain the vocabulary front.

The fifth column is an optional personal meaning for every card type. Non-empty text appears first in the answer section, under the exact heading `meaning`, before dictionary results or exercise answers; English Info stays last. Direct Excel text formatting, including rich-text bold/color and line breaks, is retained. Blank/missing meaning creates no section. It does not replace the Answer column or affect typing comparison, speech, dictionary caching or note identity. Existing Anki fields/model IDs are retained; rerun and import the APKG to update cards.

Set `[meaning] enabled = false` in config.toml to hide personal meanings for every card type; `true` enables them (also the default for older configs). The Excel text remains intact. Regenerate and import the APKG after changing this option.

Set `[meaning] html = true` to read Meaning cells as HTML, for example `<table><tr><td>et hus</td><td>huset</td></tr></table>`, `<a href="https://...">link</a>`, `<br>` or `<span style="color: red">`. Excel cell formatting is then ignored; use `<br>` for line breaks. Scripts, event handlers, iframes, forms, non-http(s) links and styles that load resources are removed. Images must be plain filenames already in Anki's media folder. `false` (default) shows tags as typed text.

Excel font names include the bundled Vazirmatn fallback for devices without Windows fonts such as Calibri. A real Vazirmatn 700 bold face is included alongside the original regular font and packaged in APKG. This improves bold rendering on Android without depending on synthesized font weight. The open-source font and license come from [Vazirmatn's official repository](https://github.com/rastikerdar/vazirmatn). Import/sync the regenerated package and its media. Phone card zoom, OS text scaling and WebView fonts can still affect sizing and line wraps; desktop browser mobile emulation does not prove identical rendering on a physical phone.

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

Validation: `python -m unittest discover -s tests -v` and `python main.py --check`.

Set `input.order = "excel"` (default) to preserve worksheet order, or `"random"` to shuffle complete records on each run before fetching/exporting. The workbook is unchanged and answers/tags stay with their questions. `max_words` selects the first valid records before shuffling. This controls generation order; Anki review order is configured separately in Anki.

Multi-blank `gap` exercises stay on one card. Put each answer on its own line in the Answer cell, in blank order (Excel: Alt+Enter). Both […] and [...] markers can be mixed. Counts must match and answer lines must not be empty; otherwise the row is skipped with a report. The back shows the complete text with highlighted answers and preserved line breaks. Audio reads the completed text. Grade the entire exercise yourself. Commas are literal answer text, not separators.

Gap fronts now have one editable input per blank (including Preview); grading remains manual for the entire exercise. The native `type` comparison input appears during actual Anki review, not in Anki’s Preview dialog. Re-run and import the new APKG to update existing templates/content.

**AnkiDroid keyboard:** If tapping a gap input focuses it but does not open the keyboard, enable **Settings → Advanced → Workarounds → Type answer into the card**, then leave and reopen the review screen. This setting resolved the issue on a tested Android device. The option's location/name may vary by AnkiDroid version. See the [AnkiDroid manual](https://docs.ankidroid.org/#_workarounds).

## Lexin table pronunciation

`[sources.lexin] entries = 2` checks the first N Lexin results (1–10) and keeps those whose headword exactly matches the input, so homographs such as reise show both meanings. Older single-entry caches are reused only with `entries = 1`.

Set `[sources.lexin] table_audio = true` to include pronunciation controls only for inflection-table forms in the exact Lexin entry. The global audio switch also applies. Files are cached and bundled; table controls do not autoplay. Set it to false for text-only tables. Additional network work shares the source time budget; increase it for large tables. Example/idiom pronunciation is excluded.

Lexin table pronunciation prefers the original Lexin audio, with a short per-control wait and gTTS fallback if it is unavailable. These controls never play all forms automatically. The `type` template uses only one native comparison, inherited on the back through FrontSide.

Table pronunciation checks both original Lexin files and previously downloaded gTTS fallback files before making requests. For uncached forms, Lexin gets up to 1.5 seconds when fallback is available; after a failed attempt, the remaining uncached forms of the same word use fallback without repeating the service wait. Cached original Lexin files remain preferred. Replay-button icons are omitted from media archiving; dictionary illustrations are retained. This reduces fresh-fetch delays without invalidating existing dictionary caches.

For isolated live timing diagnostics, run `python -m tests.benchmark_lexin --label measurement hus hund bil`. It uses a temporary dictionary database and copies of existing audio under Output, measures fresh dictionary fetches and repeat cache hits, then writes `Output/lexin_benchmark_measurement.json`. User workbooks, the real cache and original media are not modified. Fresh timings vary with the network and audio-service response.

Lexin table audio uses compact replay buttons rather than media-player bars, with no autoplay. Gap questions and completed answers align to the text direction (LTR left, RTL right); speaking answers omit the sample-answer notice.

## Shared media destination

Shared media destination: set `[media] anki_directory = "C:/.../collection.media"` once near the top of config.toml. Audio and images keep their local originals and are copied there, including cached audio and table pronunciation. Blank disables external copying. Legacy audio.copy_to remains supported when the media section is absent. Use forward slashes in double-quoted TOML paths, or single quotes for literal Windows backslashes.

Native typing accepts one answer line; multiline type answers are skipped with a reason. Typing direction is note-specific so importing another practice language does not change older cards. The exercise audio status and failures are shown in the console.

## Dictionary cache and maintenance

`[dictionary_cache]` in `config.toml` enables a local SQLite database at `Cache/dictionaries.sqlite3`. Successful results are reused across runs by normalized word, dictionary and effective source options. Fixed dictionaries such as Oxford do not depend on the selected input language; Lexin variants remain separate. Translation results also include the source/target language pair. Changing examples, image count or audio options uses a separate result. Anki fields and note identities are unchanged.

The database stores the exact generated card HTML, original fetched entry HTML and byte-for-byte backups of downloaded media. Original image-search files are retained alongside the resized card copies. Original entry images and directly exposed MP3 URLs (including Oxford pronunciation) are archived in `Cache/media`, even when the card renderer omits them. Dynamically generated Lexin headword/table audio is saved when enabled; site controls requiring other interactions are not automatically executed. This archives received entries, not an entire dictionary website. Archived-only assets do not change card appearance or audio priority.

Audio used by cards stays in the configured `[audio].directory` (default `Audio`); card images stay in `[output].directory/media` (currently `Output/media`). Cache hits restore missing or changed files from database backups and register card media for APKG and optional copying to `[media].anki_directory`. Existing downloaded audio is reused; older text/image results are populated on their first successful run after this update. Empty, failed, timed-out or incomplete results are retried rather than cached. Cache errors produce warnings and allow fetching to continue.

Set `dictionary_cache.refresh = true` to fetch again and replace successful results; then return it to `false` for reuse. `enabled = false` disables dictionary caching. Paths are relative to `config.toml`. The cache is local and ignored by Git; back up the SQLite file to preserve entries and media together. No extra database dependency or server is needed.

SVG entry images are also archived without conversion. Failure to archive an optional original-entry image/audio file does not prevent caching valid card content and its downloaded media. The failed asset URL and error are recorded in the original document metadata; use `refresh = true` to retry these optional assets. This differs from incomplete dictionary text or card pronunciation, which still prevents caching the incomplete result.

To inspect the database visually, install [DB Browser for SQLite](https://sqlitebrowser.org/dl/), open `Cache/dictionaries.sqlite3`, and select **Browse Data → results**. Columns include `word`, `source`, `content` (card HTML), `sound`, `documents` (original entry metadata/HTML) and `saved_at`. `result_media` maps results to filenames, and `assets` contains the binary file backups. In **Execute SQL**, use this read-only listing:

```sql
SELECT word, source, saved_at, sound FROM results ORDER BY source, word;
```

### Exact Lexin matching

Lexin inspects only the first two result entries on the initial page and keeps those whose Norwegian headword exactly matches the input (case/Unicode/whitespace normalized). It never visits later result pages or scans later entries. Each matching entry keeps its definition, examples and inflection table; English-only matches and compounds are excluded. One headword pronunciation is used on the front, while enabled table pronunciation is processed for each retained entry. Existing Lexin caches, including older single-entry results, remain usable without refetching. To update an older word with both entries, explicitly clear that word's cache using the commands below.

### Clear one word from the cache

Remove all cache variants of one word without running the workbook or fetching sources:

```powershell
python main.py --clear-cache hus --source lexin
python main.py --clear-cache hus
```

The first command affects Lexin only; the second affects all sources for that word. The configured database path is respected, even when caching is disabled. Related media references and unused binary backups are removed from the database; local audio/image files remain. A subsequent normal run fetches the deleted dictionary result again.

### Manual SQL maintenance

For manual deletion in DB Browser's **Execute SQL**, explicitly remove child references too (some connections disable foreign keys), then save using **Write Changes**:

```sql
BEGIN;
DELETE FROM result_media WHERE key IN (
  SELECT key FROM results WHERE source = 'lexin' AND lower(trim(word)) = 'hus'
);
DELETE FROM results WHERE source = 'lexin' AND lower(trim(word)) = 'hus';
DELETE FROM assets WHERE NOT EXISTS (
  SELECT 1 FROM result_media WHERE result_media.digest = assets.digest
);
COMMIT;
```

The CLI also handles Unicode normalization and case folding for words beyond this ASCII example. Close DB Browser after saving before using the CLI or running the application.

## Development

`main.py` runs the pipeline, `app/app_config.py` validates settings, `app/sources.py` contains the source catalog/adapters, `app/lexin_scraper.py` handles Lexin, and `app/anki_exporter.py` builds Anki cards. Imports do not start browsers or read input files. Browser resources are created on demand and closed after processing.

```powershell
python -m unittest discover -s tests -v
```

`main.py` is the application entry point. Use `config.toml` for everyday settings.

All supporting Python modules live in the `app/` package; automated tests live in `tests/`. The repository root contains only `main.py` as a Python file. Run tests from the repository root with `python -m unittest discover -s tests -v`. Configuration, workbooks, styles, media and the existing dictionary database keep their paths.

Exercise prompts (`type`, `sentence`, `gap`) retain direct Excel text formatting on the front: whole-cell and partial-text bold, italic, underline, strike-through and font colors; XLSX also retains solid cell fills and custom font sizes/families. Rich-text XLSX requires `openpyxl>=3.1.5` from requirements.txt. Gap markers work even across formatted runs. Plain question/answer values remain separate for speech, native typing and stable note identity. Listening prompts stay hidden on the front. Normal vocabulary cards retain their shared appearance. Conditional formatting, borders and spreadsheet geometry are not copied. The input workbook is read without being modified.

| File | Purpose |
| --- | --- |
| `config.toml` | The only file you edit for everyday settings |
| `Template.xlsx` | Blank five-column input template; copy to Input.xlsx |
| `main.py` | The only file you run |
| `app/app_config.py` | Configuration validation |
| `app/sources.py` | Dictionary and audio adapters |
| `app/lexin_scraper.py`, `app/oxford_scraper.py`, `app/ordbokene_scraper.py` | Dictionary-specific extraction |
| `app/image_sources.py` | Google/Commons image downloading |
| `app/anki_exporter.py` | Stable Anki model and package generation |
| `app/console_report.py` | Console progress and final run summary |
| `Styles/cards.css` | The shared card style |
| `tests/test_*.py` | Automated tests |

See [release notes](CHANGELOG.md) for version changes and migration details, and [the release policy](RELEASING.md) for publishing conventions.
