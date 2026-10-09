# Release notes

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
