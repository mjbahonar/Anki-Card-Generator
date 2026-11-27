# Release notes

## v5.13.0 — 2026-11-27

- Fixed offline answers keeping only one meaning of a word with several (`gikk` showed one of the meanings of *gå*): meanings are now told apart by their text, not by Lexin's pronunciation id, which all meanings share; of copies with the same text the one with table audio is used. Checked against 1,869 saved online results: none lost a meaning, 237 gained meanings beyond Lexin's first three results. No offline answers had been saved yet.
- When Lexin answers but has no match and the saved entries know the word as an inflected form (`grip` → *gripe*, `tell` → *telle*, beyond Lexin's first results), the form index answers, marked offline (*Lexin had no match*), whatever `offline_forms` is. Never after a timeout or error.
- Added **Fetch all offline answers again** (Database page) and `python main.py --refresh-offline`: asks Lexin again for every answer built offline, one word at a time; Stop keeps the rest for later.
- Database guide: `documents` of an offline answer also say `"lexin_missed": true` when Lexin was asked first.
- Database page: tiles for stored entries and indexed word forms, and a **Word forms** box: type a word to see the base word of an inflected form (`gikk` → *gå*) or all saved forms of a base word (`hus`: *huset, husa, husene*).
- Compatibility: backward-compatible minor release. No configuration, CLI (one new option), database layout, Anki or `app.api` changes.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check`, `git diff --check` and the flash-cards tests. On the real database: **Fetch all offline answers again** asked Lexin for all 391 offline answers (389 found, 2 not in Lexin, 0 left offline); `grip` and `tell`, which Lexin's search does not match, were answered from the index as *gripe* and *telle*. The Word forms lookup is covered by the GUI tests.

## v5.12.0 — 2026-11-27

- Versions of an entry that differ only in Lexin's search marks (highlighted search word, read-aloud and matched-row marks; not styled on cards) are stored once; card HTML no longer contains those marks.
- Lexin entries are stored once and compressed: inflected forms (`gikk`, `gått`, `går`) share one copy of *gå* instead of each saving the whole entry, and the raw page HTML is compressed too. Cards get byte-for-byte the same HTML. New tables `entries`, `result_entries`, `entry_forms` and `entry_media`; a Lexin result's `content` now holds `<!--entry:ID-->` placeholders.
- Offline inflected forms: with `sources.lexin.offline_forms = true` (default) a form that was never looked up is built from saved entries via the inflection-table index, without opening Lexin, when the word is not itself a saved headword. Marked *Offline* on the Database page (new filter and badge); **Fetch again** / `--refresh-word` always ask Lexin.
- Added a database guide for other programs (a bot, a website): tables, how to expand Lexin results, inflected form → base word, audio, server notes. `docs/database.md` and `docs/database_fa.md`; `--upgrade-cache` also copies them next to the database.
- Settings GUI server: a refused request's body is now read before replying, which could otherwise reset the connection on Windows.
- Added **Upgrade storage** (Database page) and `python main.py --upgrade-cache`: backs up the database, converts results saved before this version, and compacts the file.
- Compatibility: backward-compatible minor release for configuration, CLI and Anki: `offline_forms` is optional (default `true`), Anki fields, model IDs, note GUIDs and `app.api` are unchanged. The **database layout changes** (`PRAGMA user_version` 3): new results use it automatically; run **Upgrade storage** or `--upgrade-cache` once to convert older results (a backup is made first). Do not open an upgraded database with an older version, which would show `<!--entry:…-->` placeholders. Card HTML no longer contains Lexin's invisible search marks; cards look the same, and re-imported notes may be reported as updated.
- Validation: full automated test suite on a clean copy of this commit (three consecutive runs), `python main.py --check`, `git diff --check` and the flash-cards tests. On a real 340 MB database: upgrade and merge in about 3 minutes in total, 340 → 213 MB, all 5,408 results identical to the backup apart from the search marks, `integrity_check` ok. Offline answers for 12 never-searched forms matched Lexin online in 10 cases; *dokumenter* missed *dokumentere* (not yet saved) and *passa* added the correct *passe*. The guide's example code was run against the real database.

## v5.11.2 — 2026-11-26

- Fixed Stop (and Ctrl+C) hanging when pressed while Lexin was loading a page, so nothing was saved and a second Stop ended the run with exit code 1. Stop now asks the run to finish its current step: it is checked before each word, dictionary and audio lookup, then finished words are saved as a `_partial` file. The GUI uses a stop file instead of a console signal, so the browser is not interrupted; jobs started without a stop file (projects that subclass `GuiApp`, such as flash-cards) still get Ctrl+Break. A second press still stops at once.
- Compatibility: patch release. No configuration, CLI options, cache, Anki or `app.api` changes. The run log now says "Stopped; saving completed and partial words." (was "Interrupted; ...").
- Validation: full automated test suite on a clean copy of this commit (new tests for the stop flag, the stop file, a run stopped between words, the GUI's two-press Stop and the signal fallback), `python main.py --check`, `git diff --check` and the flash-cards tests. Reproduced live on a copy of a real cache: Stop while Lexin was loading a page hung for over two minutes before the fix; afterwards both the GUI stop file and Ctrl+Break saved all partial outputs (including the report) in about 3 seconds.

## v5.11.1 — 2026-11-26

- `å`, `en`, `ei`, `et` and a final `!` no longer filter Lexin meanings: they are only removed before the lookup, so a card shows every meaning (`en skål`: the bowl and the toast) and never suggests a word is only a noun or only a verb. `å lese` now reuses the cached result of `lese`. After `å`, an a-infinitive shows its own results and the e-infinitive verb (`å kjøpa`: *kjøp* and *kjøpe*). Results saved by 5.10.0–5.11.0 for marked words (filtered by word class) are not reused; those words are looked up once more.
- The interface language picker shows a flag beside each language: the United States for English and Iran's lion-and-sun flag for فارسی. Flags are drawn inline (flag emoji do not display on Windows); the picker works with the keyboard (arrows, Enter, Escape).
- Compatibility: patch release. No configuration, CLI, database structure, Anki or `app.api` changes.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check`, `git diff --check` and the flash-cards tests. Live on a copy of a real cache: å lese, ei jul, et hus, ei bok, en bok and å gikk came from the cached results of the bare words; en skål showed both the bowl and the toast; å kjøpa showed *kjøp* and *kjøpe*. The flag picker was checked in the browser in English and Persian.

## v5.11.0 — 2026-11-26

- Settings GUI in Persian: every page, button, message, setting label and help text, right-to-left, with the Vazirmatn font from `fonts/`. Choose فارسی at the bottom of the side bar; the choice is remembered. Paths, codes, IDs, sizes and dates stay left-to-right. Persian text lives in `app/gui/strings_fa.py`.
- Compatibility: backward-compatible minor release. No configuration, CLI, cache, Anki or `app.api` changes; English stays the default interface language.
- Validation: full automated test suite on a clean copy of this commit (including a test that every English string and every setting has a Persian label with the same placeholders, and that the font route serves only the bundled Vazirmatn files), `python main.py --check`, `git diff --check` and the flash-cards tests. In the browser: Persian Excel input, Dictionaries and Database pages, right-to-left layout, Vazirmatn loaded, sizes and dates left-to-right. Known limitation: `main.py` log lines, validation errors and the PDF report stay English.

## v5.10.0 — 2026-11-26

- Words written with `å`, `en`, `ei`, `et` or a final `!` are looked up without them in every dictionary. In Lexin the marker selects the entry: `å` keeps verbs, `en`/`ei`/`et` keep nouns (preferring that gender), so `en skål` is the bowl, not *skål!*. After `å`, an a-infinitive is tried with -e (`å kjøpa` → *kjøpe*, indirect) instead of the noun form *kjøpa*. Previously such words got unrelated Lexin results rejected and were saved as "not found".
- Added `[cards.normal] show_markers` (default `true`): `false` shows only the word on the card front (`skål` for `en skål!`); text-to-speech then says the same. Note identity is unchanged.
- Compatibility: backward-compatible minor release. `show_markers` is optional (default `true`, the previous display); the database structure, Anki fields, note GUIDs and `app.api` are unchanged. Words written with a marker get a separate Lexin cache entry (bare word plus word class), so they are looked up once; plain words keep their cached results. `select_audio` has an optional `spoken` argument.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check`, `git diff --check` and the flash-cards tests. Live on a copy of a real cache: en skål (bowl only, not the interjection), skål! (both), ei jul, et spøkelse, et hus, ei bok, en bok, å lese (verbs only), å kjøpa / å kasta / å snakka (→ kjøpe / kaste / snakke, indirect); with `show_markers = false` the fronts showed the bare words and text-to-speech said them. Known limitation: an expression such as *en gang* ("once") is read as the noun *gang*.

## v5.9.1 — 2026-11-26

- Fixed every Lexin word being fetched and saved again after `sources.lexin.form_entries` was added to `config.toml` (5.8.0–5.9.0 put it in the cache key, contrary to the 5.8.0 notes). It no longer affects the key of found results; it only decides when a saved "not found" is checked again. Results saved by 5.8.0–5.9.0 are reused, so nothing is fetched twice.
- Compatibility: patch release. No configuration, CLI, database structure, Anki or `app.api` changes. Lexin results saved with different `entries` or `variant` settings remain separate, as before.
- Validation: full automated test suite on a clean copy of this commit (with a new test that `form_entries` never changes the key and that 5.8.0–5.9.0 rows are reused), `python main.py --check`, `git diff --check` and the flash-cards tests. On a copy of a real cache: bil, billett, dem and bestille (saved before 5.8.0 and again under 5.8.0 keys) and gikk, husene, brødre (indirect) all came from the cache with no network lookup.

## v5.9.0 — 2026-11-26

- Added a run report: `"report"` in `output.formats` writes `<output>_report.pdf` (summary, every word with each dictionary's result, issues and every setting) and `<output>_report.png` (the summary page).
- Results found through an inflected form are treated as indirect translations: the Database page has an **Indirect** filter, an `Indirect → gå` badge and separate counts; reports show them as ↪ with the base word.
- Fixed a needless "No headword pronunciation available" warning for every inflected form (Lexin's recording says the base word, so the next audio provider is used on purpose).
- The `gikk → gå` note on cards is now a centered box with an "Inflected form" label, in light and dark mode (CSS only; cached results need no refresh — rebuild and import the deck).
- The distributed `config.toml` now includes `"report"` in `output.formats`.
- Compatibility: backward-compatible minor release. `"report"` is optional and older configs remain valid; the database structure, Anki fields, model IDs, note GUIDs and `app.api` are unchanged. The card style gains `.lexin-form-note` rules only.
- Validation: full automated test suite on a clean copy of this commit (including an end-to-end PDF/PNG render), `python main.py --check` on a local workbook, `git diff --check` and the flash-cards tests. A real run of 15 inflected test words on a copy of a real cache: all found indirectly with the expected base words, status COMPLETED with no issues, report PDF (6 pages) and PNG checked visually. The note box was checked in light and dark mode in Chromium; not yet viewed in AnkiDroid.

## v5.8.0 — 2026-11-26

- Lexin finds inflected forms: without an exact headword, the first `sources.lexin.form_entries` results (default 3; `0` = off) are checked for the input in their inflection tables (*gikk → gå*, *husene → hus*, *bøker → bøk, bok*, *større → stor*). Matching entries get a short `gikk → gå` note; the headword recording is skipped for them, so pronunciation comes from the next audio provider. Exact headwords still win.
- "Not found" Lexin results saved before this, or with another `form_entries`, are checked again automatically; found results are kept.
- Database page: checkboxes with **Delete selected**, **Delete all matching** (current search and filters) and **Recheck all not found**.
- Compatibility: backward-compatible minor release. `sources.lexin.form_entries` is optional (default 3), so older configs remain valid; set it to `0` for the previous exact-only behavior. Found results in existing caches are reused; only saved "not found" Lexin results are checked again. Words found through a form show a `gikk → gå` line in the Lexin field (styled by a new `.lexin-form-note` rule in `Styles/cards.css`); Anki fields, model IDs, note GUIDs and `app.api` are unchanged.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check` on a local workbook, `git diff --check` and the flash-cards tests. Live on a copy of a real cache: gikk → gå, husene → hus, bøker → bøk and bok, barna → barn, større → stor; a made-up word stayed "not found". In the browser: Delete selected, Delete all matching with a search and status filter, Recheck all not found.

## v5.7.1 — 2026-11-26

- Fixed every remaining word failing with "Target page, context or browser has been closed" after the browser closed mid-run (computer sleep, Chromium crash). The browser and Playwright's driver are now restarted automatically, with `WARN  browser: closed unexpectedly; restarting it` in the log; after 5 restarts in one run, browser sources are skipped with a clear message.
- Compatibility: patch release. No configuration, CLI, cache, `app.api` or Anki changes.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check` on a local workbook, `git diff --check` and the flash-cards tests. Live: after closing the browser and after stopping Playwright's driver, the next page opened in a restarted browser, and a real Lexin lookup for *hus* succeeded after the browser was closed. A real Chromium crash (killed process) was not reproduced.

## v5.7.0 — 2026-11-26

- Words that Lexin definitely does not have (*Ingen treff*, or no exact headword among the inspected results) are saved as "not found" and skipped on later runs, without expiry. Timeouts and errors are never saved this way. The run log shows `CACHE not in lexin (saved earlier)`.
- Added `python main.py --refresh-word WORD [--source SOURCE]`: deletes one word's cached results and looks it up again now.
- Settings GUI: new **Database** page with cache statistics, word search with filters, saved-content preview, Fetch again, Delete, Compact file and "Recheck not found". Cache maintenance moved there from Advanced.
- Compatibility: backward-compatible minor release. No configuration changes are needed; the database structure is unchanged (a "not found" result is a result with empty content). Anki fields, model IDs, note GUIDs and `app.api` are unchanged; flash-cards also skips cached "not found" words. Existing caches keep working; words that were never saved because Lexin had no entry are checked once more and then remembered.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check` on a local workbook, `git diff --check` and the flash-cards tests. Live on a copy of a real cache: `--refresh-word` saved *xqzvbrt* (Ingen treff) and *husene* (no exact headword) as not found and found *hus* normally. In the browser: Database statistics, search and filters, content preview, Fetch again, Delete and Compact.

## v5.6.1 — 2026-11-26

- Fixed the settings GUI marking a worksheet name (for example `FINAL`) as invalid in **Worksheet** (`input.sheet`). Worksheet and **Input column** (`input.word_column`) now accept a name or a zero-based number in the GUI, as `config.toml` always allowed. Digits are saved as a position (`2` = third sheet); anything else is saved as a name.
- Compatibility: patch release. No configuration, CLI, `app.api` or Anki changes.
- Validation: full automated test suite on a clean copy of this commit, `python main.py --check` on a local workbook, `git diff --check`, the flash-cards tests, and in the browser: saving `FINAL` as the worksheet wrote `sheet = "FINAL"` with its comment kept.

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
