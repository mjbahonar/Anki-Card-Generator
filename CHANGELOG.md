# Release notes

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
