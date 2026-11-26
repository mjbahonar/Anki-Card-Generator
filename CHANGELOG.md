# Release notes

## v5.6.0 — 2026-11-26

- Added a settings GUI: `python main.py --gui` opens a local browser page that edits `config.toml` in place (comments kept, validated with the same rules as `main.py`), reorders dictionaries, and has Check, Run and Stop buttons with a live log. Stop saves finished words like Ctrl+C. The interface is English; its text is in `app/gui/i18n.py` so other languages can be added later. New dependency: `tomlkit`. `app.api`, card output and the Anki schema are unchanged.
- Added optional `[anki.saved_decks]` (`"Deck name" = deck_id`) for switching between decks. Only `deck_name`/`deck_id` decide the output deck; each saved deck needs its own ID. The GUI shows the list as a deck picker with add and remove. Older configs without the list remain valid.
- Added `input.first_row` / `input.last_row`: read only an Excel row range (row numbers as shown in Excel; `0` = no limit). A reversed range or a range without words stops `--check` and the run with an error. Applied before `max_words` and random order.
- Settings GUI: **Browse…** opens the Windows file dialog for the workbook and style file; a refresh button rescans the folder and shows whether the file exists.
- Ctrl+Break on Windows now stops a run the same way as Ctrl+C (finished words are saved).
- Added `python main.py --clear-source-cache SOURCE`: removes every cached result of one dictionary (for example `images`), its unused database backups and `Cache/media` archive files, then compacts the database. Other dictionaries' cache, the `Audio`/`Images` folders and cards are unchanged.
- Compatibility: backward-compatible minor release. All new settings are optional, so older `config.toml` files remain valid; CLI behavior without the new options is unchanged. Anki fields, model IDs and note GUIDs are unchanged, and `app.api` (used by flash-cards) is unchanged. New dependency: `tomlkit` (run `python -m pip install -r requirements.txt`).
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check` on a local workbook, `git diff --check`, and the flash-cards tests against this version. In the browser: saving keeps comments, dictionary reordering, deck switching/adding, Check and Run with live log, Stop saving a partial file, workbook found/missing indicator, row-range errors. `--clear-source-cache images` shrank a real cache from 74 MB to 26 MB. Known limitations: the Browse dialog uses Tk and was checked to open from the server thread, not clicked through in an automated test; after Stop, Playwright may print shutdown warnings in the log.

## v5.5.0 — 2026-11-24

- Packaging: added `pyproject.toml`, so other projects can install this repository (`pip install -e ../Meaning-Ankidroid`) and reuse its dictionaries, audio, images and cache instead of copying code. `python main.py` is unchanged.
- Added `app.api` (`API_VERSION = 1`): `load_settings`, `enabled_sources`, `read_input_words`, `Lookup` with `WordResult`/`SourceResult`, and `Lookup.images(term)` with `ImageResult` to search images for any term (such as an English meaning), `sanitize_html` (the Meaning-column HTML rules) and `excel_formatted_cells` (Excel cell formatting as HTML). Other modules remain internal.
- Added contract tests (`tests/test_contract.py`) that fail when a change would break projects using `app.api`: API names, signatures and result fields, Lexin card HTML structure (checked against a saved real entry), image result HTML and the config keys they use.
- `load_config(path, check_files=False)` skips the Excel/style file checks for library use; the default behavior is unchanged.
- The version now lives in `app.__version__`; `main.VERSION` still works.
- Added `"bing"` to `sources.images.priority`: full-size Bing Images results for "<word> clipart" with strict SafeSearch, credited to the source site. No license data; for personal study material only. Existing priorities are unchanged.
- Fixed words running together in Bokmålsordboka/Nynorskordboka alternative forms ("husahusene" → "husa, husene") and Dict.com headwords ("husn" → "hus n"). The sites draw these separators with CSS that cards do not include; they are now written into the text, also for cached results.
- Fixed Wikimedia Commons images failing with HTTP 403 ("Too many requests… robot policy"): Commons API and image requests now send a descriptive User-Agent instead of a generic browser one.
- Compatibility: backward-compatible minor release. No configuration, CLI or Anki schema changes; model IDs and note GUIDs are unchanged and older configs remain valid. Bokmålsordboka/Dict.com card text now includes the restored separators, so re-imported notes show "husa, husene" instead of "husahusene". `"bing"` is opt-in; default image priorities are unchanged.
- Validation: 137 automated tests (including the new API and contract tests) on a clean copy of this commit, `git diff --check`, and live runs: Bing images for bil/hus downloaded, shown in the HTML preview and bundled in an APKG, then reused from the cache on a second run without network image search; Lexin + Bokmålsordboka + Dict.com cards through the flash-cards project. `python main.py --check` with the default config and a local `Input.xlsx` (33 words, Lexin). Known limitations: Google Images answers automated searches with a CAPTCHA on many networks; Bing results are automatic and may need review.

## v5.4.0 — 2026-10-26

- Output files now start with the input workbook name: `<input>_<filename_prefix>_<date-time>`.
- Added `[audio.word]` to choose headword audio providers per input language (`lexin`, `fastdic`, `google_tts`); `[]` disables headword audio for that language. `nb`/`nn` use the `no` list and unlisted languages keep `audio.priority`, so older configs work unchanged.
- Added `sources.lexin.entries` (default 2, range 1–10): the first N Lexin results are checked and every exact headword match is kept. Pre-multiple-entry single-result caches are no longer reused at the default; affected words such as reise are fetched again once. Revision-2 caches remain valid.
- Added a VS Code recommendation for the Even Better TOML extension (colored, validated `config.toml`).
- Added `[meaning] html = true` to read the Meaning column as sanitized HTML (tables, http(s) links, line breaks, inline colors/fonts). Scripts, event handlers, iframes, unsafe links and resource-loading styles are removed. Default `false` keeps the existing Excel-formatting behavior.
- Compatibility: backward-compatible minor release. Anki fields, model IDs and note GUIDs are unchanged; older configs remain valid. New output filenames start with the input name, so scripts matching `words_*` need updating.
- Validation: 116 automated tests, `main.py --check` on the local workbook and `git diff --check`. Live runs: Lexin reise returned both exact entries with Lexin audio; English book used Fastdic audio; an HTML-meaning table and link rendered in the HTML preview and APKG built. Physical AnkiDroid rendering of HTML meanings was not verified.

## v5.3.0 — 2026-10-14

- Added a local SQLite dictionary cache with exact generated card HTML, original received entry HTML and byte-for-byte media backups. Successful results are reused by normalized word, source and effective options; fixed dictionaries do not depend on the selected input language. Missing media is restored from the database. Existing audio remains reusable and local caches are excluded from Git.
- Added `dictionary_cache.enabled/path/refresh` and `python main.py --clear-cache WORD [--source SOURCE]`. Per-word deletion removes every selected cache variant and related database media references while retaining local audio/image files. Optional archive failures do not discard valid card results; SVG images are supported, replay icons are excluded and corrupted media backups can be repaired by refetching.
- Lexin checks only the first two result entries on the initial page and keeps exact Norwegian headword matches, so homographs such as gift retain both definitions, examples and inflection tables. It never scans later entries or result pages. Existing single-entry caches remain usable; clear only the word that needs updating.
- Reduced Lexin table-audio delays by reusing previously downloaded gTTS fallback audio before requesting it again. With fallback enabled, the native service wait is limited to 1.5 seconds; after a failure, remaining uncached forms of that word use fallback without repeated waits. Cached original Lexin audio remains preferred.
- Added an optional fifth Excel column, Meaning, shown first on the back under the heading meaning for all card types. `[meaning] enabled = false` hides it. The Answer column retains its existing role and English Info remains last. Direct whole-cell/rich-text formatting is preserved for exercise fronts and personal meanings; gap markers work across formatted runs and unformatted portions inherit the Excel cell size.
- Added a portable font fallback and a real bundled Vazirmatn bold face, with its open-source license, for devices without Windows Excel fonts. The bold font is included in APKG. Moved supporting Python modules into app/ and automated tests into tests/; main.py remains the only application launcher.
- Included the reviewed blank Template.xlsx with Word, Type, Tag, Answer and Meaning headers, an Excel card-type dropdown and a quick-reference sheet. Its original workbook bytes and native validation are preserved. Copy it to Input.xlsx and fill rows below the headers; distributed config uses header = true, keeps every dictionary section, and leaves personal media destinations blank.
- Compatibility: this is a backward-compatible minor release. Published Anki field schemas, model IDs and note GUIDs remain unchanged, so no note migration is required. Older configs and one-/four-column workbooks remain accepted; keep existing deck/model IDs when upgrading and regenerate/import APKG to update card content and styling.
- Validation: 103 automated tests, configuration validation on the local 33-record input, template parsing across all five card types, checksum preservation, APKG/CSV/HTML checks and diff checks. Isolated live Lexin tests passed gift, hund and bil; measured fresh fetches improved from 6.5/10.4/9.4 seconds to 2.4/4.8/5.3 seconds, with repeat cache reads below 0.01 seconds. Desktop and mobile browser layouts loaded distinct regular/bold faces. Physical AnkiDroid rendering and legacy XLS rich-text rendering were not verified; exact font availability, phone zoom, conditional formatting and network/service behavior remain limitations.

## v5.2.0 — 2026-10-13

- Added optional Excel type/tags/answer columns with normal, type, sentence, gap and listen cards. Blank type preserves the one-column vocabulary workflow. Automatic editable type tags and optional random generation order.
- Added language-aware English instructions, per-type settings, Norwegian/Persian text direction, native spelling comparison and multi-blank exercises on one card with editable inputs and highlighted completed answers. Missing/invalid answers and unavailable listening audio are skipped and reported.
- Added Lexin Bokmål/Nynorsk/both selection in the existing Lexin field. Optional inflection-table audio uses compact manual replay buttons, a local cache and gTTS fallback; example audio is excluded.
- Added one shared Anki media destination for audio and images while keeping local originals. Legacy audio.copy_to configurations remain accepted. Distributed config leaves the personal media destination blank and retains every dictionary section.
- Fixed Norwegian audio variant/cache selection, Nynorsk gTTS fallback, note-specific typing direction, multiline typing validation and exercise audio reporting/delays. Empty checks now fail when every row is invalid.
- CSV exports include an Anki import companion for vocabulary-only and mixed decks, with the same GUIDs as APKG. Install the matching models via APKG before CSV import; CSV does not contain templates or media.
- Compatibility: existing V5 vocabulary fields/model/GUIDs are unchanged. Four additive exercise models use stable independent IDs; no migration or major-version bump is required. Keep deck/model IDs fixed after import.
- Validation: 61 automated tests, configuration validation and diff checks. Live public hus passed Bokmål with all five table pronunciations and Nynorsk with headword audio. Local browser checks cover LTR/RTL layout; native Anki Preview intentionally omits the type comparison box. Real AnkiDroid review was not tested. External dictionary availability and network budgets still apply.

## v5.1.0 — 2026-10-09

- Added an optional per-word/source network budget (`runtime.source_timeout_seconds`, default 30; 0 disables). Share remaining time across requests, browser waits and translation retry delays; hide expired source results and continue with other sources. Individual request timeout (`runtime.timeout_seconds`) also defaults to 30 seconds. Audio requests use the individual request timeout separately.
- Wait for Ordbøkene hydration before toggling inflection, and use the remaining budget for table waits. Surface component warnings immediately even when source content succeeds.
- Live `spise` and `hus` passed Lexin/Bokmålsordboka/Dict.com with a five-second budget; `spise` inflection completed in about 1.7 seconds.
- Validation: 39 automated tests, configuration check and live budget/inflection checks. Anki schema and note identity are unchanged from v5.0.0. Time limits govern network operations; cleanup/local work may add time. Google rate limits and Faraazin DNS availability remain external limitations.

## v5.0.0 — 2026-10-09

- Added separate Bokmålsordboka and Nynorskordboka sources, enabled for Norwegian input. Expand inflection tables for every exact entry; retain bold/italic emphasis, homograph entries, senses and set phrases. Tables scroll horizontally on narrow screens.
- Final validation: 36 automated tests, configuration validation and live `hus`, `bok`, `lese` in both new dictionaries with no source/export errors. Verified all six dictionary results, noun/verb/participle tables, bold text, Anki database integrity and final fields, and mobile layout. Existing Oxford and image live checks are described below. Google Translate rate limits and Faraazin DNS availability remain external limitations.
- The final V5 model adds Oxford and both Ordbøkene fields. Defaults use model `1559328451` and deck `2059400451`; do not reuse V3/V4 IDs or the draft V5 model `1559328450`. Import into a new deck; review history is not automatically migrated.

- Restored vocabulary images with configurable Google/Commons fallback, including inline Google images, local PNG media, per-provider diagnostics and Commons attribution. Live `book`, `cat`, `apple` downloaded three images each through Commons after Google returned no results.

- Follow Oxford's same-headword entry links to include every available part of speech, deduplicating entries and excluding compounds. Handle nested single-sense definitions. Live verification: `book` (noun/verb), `round` (five parts of speech), `fast` (four); all output formats completed without issues.

- Added an English-only Oxford Learner's Dictionary source using direct HTML, exact headword validation, main definitions and a configurable number of examples per definition. Oxford pronunciation is not requested; existing Fastdic/Google TTS priority remains unchanged.
- Anki schema migration: a new Oxford field requires a new default model (`1559328451`) and deck (`2059400451`). Do not reuse V4 model IDs. Existing V4 decks are preserved; review history is not migrated automatically. Source toggles and ordering remain stable within the new model.
- Validation: live `book`, `house`, `eat` with Oxford, Fastdic and Cambridge; all five formats completed without errors and Fastdic audio was downloaded for each word. Automated coverage includes exact headword rejection, example limits and exclusion of audio/site controls.

## v4.0.2 — 2026-10-09

- Added readable per-word source statuses, elapsed times, audio status and a final console report with source totals, issues and output paths.
- Preserved available rows after unexpected runtime/audio errors and reported output-directory, autosave and error-report write failures without discarding successful exports.
- Captured Lexin search/audio errors in the structured report, bounded Chromium launch timeout, and fixed browser/session cleanup after setup failures.
- Preserved Fastdic example direction, rejected empty sanitized definitions, validated finite timing values and SQLite-compatible Anki IDs, and created optional audio-copy directories.
- Validation: 30 automated tests, configuration validation and live checks of six words. Norwegian Lexin/Dict.com and English Fastdic/Cambridge/Dict.com returned content; all five output formats completed, both Anki databases passed integrity checks and all six freshly downloaded MP3s were bundled.
- Known limitations: Google Translate returned HTTP 429; Faraazin failed DNS resolution. Dict.com uses the English–Norwegian pair even for English input; it does not provide English–Persian translations. No Oxford/Merriam-Webster adapter is included in this release.

## v4.0.1 — 2026-10-09

- Removed obsolete launchers (`main_script.py` and `main_script(word_by_word).py`), unused V3 styles and screenshots, and archived/extra-language README files. Keep `main.py` as the single entry point and English/Persian as the maintained README languages.
- Preserved all Excel workbooks and the active V4 configuration, dictionaries, styles and tests.
- Added a release policy: lowercase `vMAJOR.MINOR.PATCH` tags, matching runtime versions and GitHub releases, immutable published tags and release notes with validation/limitations. Historical tags remain unchanged.
- Faraazin was enabled for `house`, `book` and `eat`. Both its bare and `www` domains failed DNS resolution from this environment; other sources and all output formats completed. Geographic blocking is not confirmed.
- Validation: 21 automated tests, configuration check, and checksum verification of every pre-existing Excel workbook.

## V4.0 — 2026-10-09

Unified application for English and Norwegian. One `config.toml` controls input workbook/sheet/column, language, source toggles/order, audio priority/cache, deck/model identity, output formats, shared styling and the English Info footer. Run `main.py`.

- Replaced duplicated entry-point logic with a validated, import-safe pipeline and a source registry. Previous entry filenames delegate to V4.
- Removed the obsolete Selenium scraper module; browser-based adapters now use lazy Playwright pages. No ChromeDriver or `.env` media configuration is needed.
- Kept the current V3.6N card appearance in `Styles/cards.css` for every language and dictionary. The English Info block is always last.
- Built a fixed unified Anki schema and stable word-based note GUIDs. Source toggles, order and new audio do not change note identity. Defaults use a new V4 model/deck, without automatic migration from V3.
- Export selected Excel, CSV, Anki, playable HTML and JSON outputs. Bundle only referenced media/font. Support cached pronunciation, source-specific failures, bounded network timeouts/retries, recovery CSV and Ctrl+C partial exports.
- Added source adapters for the former English dictionaries to the same catalog; incompatible sources are skipped by input language. Google Translate source/target are configurable.
- Added 16 V4 integration tests alongside five Lexin tests: Excel selection, Unicode duplicates, config validation, stable schema/GUIDs, source order, output selection, media inclusion, failure isolation, interruption recovery, audio fallback, language-specific caching, dictionary routing and clean English definitions.
- Live-tested three Norwegian words (`bok`, `hus`, `spise`) with Lexin/Dict.com and three English words (`house`, `book`, `eat`) with Fastdic/Dict.com/Cambridge, generating all five output formats. Google Translate returned HTTP 429 in both runs; other results and audio were saved successfully. Other optional source adapters are not all live-verified.

نسخهٔ ۴ یک نسخهٔ اصلی مشترک است: تنظیمات در `config.toml` و اجرا از `main.py`. استایل فعلی حفظ شده، Info انگلیسی پایین همه است، سورس‌ها از کانفیگ کنترل می‌شوند و مدل جدید Anki هویت کارت‌ها را با تغییر سورس و صوت ثابت نگه می‌دارد. مدل و دک نسخهٔ ۳ خودکار مهاجرت نمی‌کنند.

## V3.6N — 2026-10-09

Norwegian edition on the `Norwegian-to-English` branch, following `V3.5N`.

### Changes

- Added Lexin Bokmål–English as the first section on the card back, before Google Translate and Dict.com.
- Select the first exact headword from the displayed Lexin results, preserving Norwegian letters and rejecting unrelated search matches. Keep its complete definitions, inflection tables, examples, idioms and compounds.
- Download the selected headword's Lexin pronunciation and use it on the front. Fall back to Google TTS if the entry or audio is unavailable; avoid a broken sound reference if both fail. Inflection and compound pronunciation files are not downloaded.
- Include the downloaded MP3 in the Anki package. Local audio generation works without `ADDRESS`; copying to the configured Anki media folder remains optional.
- Style Lexin consistently with existing cards, including dark mode and horizontal scrolling for inflection tables on mobile.
- Repair Dict.com extraction for its current HTML structure and use `engelsk-norsk`. Keep the requested entry's translations and phrases while excluding advertisements and full-text search hits.
- Append the Lexin Anki field to retain existing field positions and model/deck IDs.

### Validation

- Five automated tests cover headword normalization, entry cleanup, invalid audio responses, fallback selection and safe filenames.
- Ten live Lexin searches: nine exact entries and their audio were retrieved; Lexin reported no exact entry for `etterpåklok`, so approximate matches were rejected.
- Verified `bok` desktop/mobile previews and Anki package fields, front sound reference and bundled audio.
- Simulated a Lexin speech outage: the definition remained available and a real Google TTS fallback MP3 was generated.
- Tested the repaired Dict.com scraper on `hus`, `bok` and `spise`.

### Known limitations

- Google Translate can reject requests with rate-limit/server errors; its section is empty when translation fails. This release does not fix that service error.
- Dictionary extraction depends on the sites' current markup and availability. Lexin chooses the first exact entry on the displayed results page; additional homonym entries are not combined.
- Lexin and Google pronunciation are synthesized speech. No audio is downloaded for inflections, compounds or examples.

### توضیحات فارسی

نسخهٔ `V3.6N` نسخهٔ جدید شاخهٔ نروژی است. Lexin با معنی، جدول صرف، مثال‌ها و ترکیب‌های همان مدخل دقیق، بالاتر از ترجمهٔ گوگل و Dict.com نمایش داده می‌شود. صوت خودِ سرواژه از Lexin دانلود و روی فرانت قرار می‌گیرد؛ اگر دریافت نشود Google TTS جایگزین می‌شود. صوت صرف‌ها و ترکیب‌ها دانلود نمی‌شود. ساختار جدید Dict.com نیز پشتیبانی شده و با سه کلمه تست شده است. خطای محدودیت درخواست ترجمهٔ گوگل همچنان ممکن است رخ دهد.
