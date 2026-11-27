# راهنمای پایگاه دادهٔ دیکشنری

`Cache/dictionaries.sqlite3` یک فایل معمولی SQLite 3 است. هر برنامه‌ای که SQLite بخواند (ماژول داخلی `sqlite3` پایتون، Node، PHP، Go یا DB Browser for SQLite) می‌تواند از آن استفاده کند و سرور لازم ندارد. این راهنما ساختاری را توضیح می‌دهد که Anki Card Generator نسخهٔ 5.12 به بعد می‌نویسد (`PRAGMA user_version` = 3)، و نشان می‌دهد چطور کلمه بخوانید، شکل صرف‌شده را به کلمهٔ پایه برسانید و صدا بگیرید.

ساده‌ترین و امن‌ترین راه در پایتون، رابط کتابخانه‌ای (`from app import api`؛ TECHNICAL.md) است که همهٔ این کارها را خودش انجام می‌دهد. اگر می‌خواهید مستقیم با فایل کار کنید (مثلاً برای بات تلگرام یا سایت)، ادامه را بخوانید. نمونه‌کدها در نسخهٔ انگلیسی همین راهنما ([database.md](database.md)) هم هست.

## جدول‌ها

| جدول | هر ردیف | ستون‌های اصلی |
| --- | --- | --- |
| `results` | یک کلمهٔ جستجوشده × دیکشنری × تنظیمات | `key`، `source`، `word`، `content`، `sound`، `documents`، `saved_at` |
| `entries` | یک مدخل Lexin (یک معنی از یک کلمه)، فقط یک بار | `id`، `variant`، `headword`، `headword_key`، `html`، `raw` |
| `result_entries` | پیوند: هر نتیجهٔ Lexin کدام مدخل‌ها را نشان می‌دهد | `key`، `entry_id` |
| `entry_forms` | یک شکل کلمه در جدول صرف یک مدخل | `form`، `entry_id` |
| `assets` | یک فایل صوتی یا تصویری، فقط یک بار | `digest` (SHA-256)، `data` (بایت‌ها) |
| `result_media` | پیوند: فایل‌های رسانهٔ هر نتیجه | `key`، `filename`، `kind`، `digest` |
| `entry_media` | پیوند: تلفظ‌های جدول صرف هر مدخل | `entry_id`، `filename`، `kind`، `digest` |

### `results`

- `key`: متن JSON به شکل `[1, دیکشنری, کلمهٔ یکسان‌شده, {تنظیمات}]`. تنظیمات همان گزینه‌هایی است که نتیجه را عوض می‌کند (برای Lexin: `variant`، `entries`، `table_audio`، …). پس یک کلمه ممکن است چند ردیف داشته باشد؛ هر کدام جواب درستی است.
- `source`: `lexin`، `oxford`، `bokmalsordboka`، …
- `word`: کلمهٔ جستجوشده (بدون `å`/`en`/`ei`/`et` و `!`).
- `content`: HTML کارت، با سه حالت خاص:
  - `''` (خالی): **پیدا نشد** — دیکشنری جواب داده و کلمه در آن نیست.
  - شامل `<!--entry:ID-->`: نتیجهٔ Lexin. هر ارجاع را با HTML مدخل جایگزین کنید (`zlib.decompress(entries.html)` برای همان `id`). متن بین ارجاع‌ها، مثل `<div class="lexin-form-note">gikk → <b>gå</b></div>`، همان‌طور می‌ماند.
  - در بقیهٔ حالت‌ها: HTML کامل (دیکشنری‌های دیگر).
- `sound`: برچسب صدای تلفظ کلمه در Anki، مثل `[sound:lexin_no_hus_699f41dd2d.mp3]`، یا خالی.
- `documents`: فهرست JSON از منشأ نتیجه (`url`)، HTML اصلی صفحه یا ارجاع به آن (`entry`)، و برای جواب‌های آفلاین `{"offline_forms": true}`.
- `saved_at`: زمان ذخیره (UTC).

### وضعیت هر نتیجه

| وضعیت | چطور تشخیص بدهیم |
| --- | --- |
| پیدا نشد | `content = ''` |
| غیرمستقیم (شکل صرف‌شده، مثلاً `gikk` ← `gå`) | `content LIKE '%lexin-form-note%'`؛ کلمهٔ پایه داخل `→ <b>…</b>` است |
| آفلاین (از مدخل‌های ذخیره‌شده) | `documents LIKE '%"offline_forms": true%'` |
| پیدا شد (مستقیم) | بقیه |

### `entries`

- `id`: هش SHA-256 از HTML مدخل؛ با `<!--entry:ID-->` به آن ارجاع داده می‌شود.
- `variant`: `bokmal` یا `nynorsk`.
- `headword` و `headword_key`: کلمهٔ اصلی مدخل، همان‌طور که نمایش داده می‌شود و به‌صورت یکسان‌شده.
- `lexin_id`: شناسهٔ تلفظ کلمه در Lexin. همهٔ معنی‌های یک کلمه آن را مشترک دارند، پس برای هر مدخل یکتا **نیست**.
- `html`: HTML کارت آن مدخل (تعریف، مثال، جدول صرف)، فشرده با zlib و با کدگذاری UTF-8.
- `raw`: HTML اصلی صفحهٔ Lexin برای آن مدخل (آرشیو)، فشرده با zlib.

### یکسان‌سازی کلمه

کلمه‌ها در `results.key`، `entries.headword_key` و `entry_forms.form` این‌طور یکسان‌سازی شده‌اند:

```python
import unicodedata
def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).replace('|', '').split()).casefold()
```

## دستورالعمل‌ها

### ۱. باز کردن و بازسازی HTML

```python
import json, re, sqlite3, unicodedata, zlib

db = sqlite3.connect('file:Cache/dictionaries.sqlite3?mode=ro', uri=True)  # فقط‌خواندنی

def expand(content):
    """HTML کارت: هر ارجاع با مدخل ذخیره‌شده جایگزین می‌شود."""
    def entry(match):
        blob = db.execute('SELECT html FROM entries WHERE id = ?', (match.group(1),)).fetchone()[0]
        return zlib.decompress(blob).decode('utf-8')
    return re.sub(r'<!--entry:([0-9a-f]{64})-->', entry, content)
```

### ۲. جستجوی یک کلمه

```python
def lookup(word, source='lexin'):
    """جدیدترین نتیجهٔ ذخیره‌شدهٔ کلمه: (وضعیت، html)؛ None اگر هرگز جستجو نشده."""
    wanted = normalize(word)
    for key, content, documents in db.execute(
            'SELECT key, content, documents FROM results WHERE source = ? ORDER BY saved_at DESC', (source,)):
        if json.loads(key)[2] != wanted:
            continue
        if content == '':
            return 'not found', ''
        status = 'indirect' if 'lexin-form-note' in content else 'found'
        if '"offline_forms": true' in documents:
            status += ' (offline)'
        return status, expand(content)
    return None
```

### ۳. شکل صرف‌شده ← کلمهٔ پایه

جدول `entry_forms` همهٔ شکل‌های همهٔ مدخل‌های ذخیره‌شده را دارد (`gikk`، `går`، `gått`، … ← `gå`):

```python
def base_words(form, variant='bokmal'):
    """کلمه‌های پایه‌ای که این شکل در جدول صرفشان هست، و اینکه خود این شکل مدخل جدا هست یا نه."""
    key = normalize(form)
    is_headword = db.execute('SELECT 1 FROM entries WHERE headword_key = ? AND variant = ? LIMIT 1',
                             (key, variant)).fetchone() is not None
    bases = [h for (h,) in db.execute(
        'SELECT DISTINCT e.headword FROM entry_forms f JOIN entries e ON e.id = f.entry_id '
        'WHERE f.form = ? AND e.variant = ? ORDER BY e.headword', (key, variant))]
    return is_headword, bases

base_words('gikk')    # (False, ['gå'])
base_words('bøker')   # (False, ['bok', 'bøk'])  اگر هر دو مدخل ذخیره شده باشند
base_words('hus')     # (True,  ['hus', 'huse']) خودش مدخل است، و امر فعل huse هم هست
```

**قاعده‌هایی که خود برنامه هم رعایت می‌کند:**

- اگر کلمه خودش مدخل جدا باشد (`is_headword`)، نتیجهٔ خودش را نشان دهید: `skrev` هم گذشتهٔ `skrive` است و **هم** یک اسم مستقل.
- فهرست فقط مدخل‌هایی را می‌شناسد که ذخیره شده‌اند. اگر کلمهٔ پایهٔ دیگرِ یک شکل هرگز جستجو نشده باشد، جواب ناقص است (`dokumenter` به `dokumentere` هم تعلق دارد).
- یک کلمهٔ پایه ممکن است چند مدخل (چند معنی) داشته باشد؛ `gå` چند مدخل دارد.

### ۴. متن ساده و معنی انگلیسی

با BeautifulSoup (`pip install beautifulsoup4`):

```python
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')
headword = soup.select_one('.grunnform').get_text(strip=True)
english = [dd.get_text(' ', strip=True) for dd in soup.select('dd[lang="en"]')]
```

### ۵. صدا

بایت‌های فایل MP3 در `assets.data` است. نام فایل تلفظ کلمه در ستون `sound` نتیجه آمده (`[sound:نام]`)؛ با `result_media` به `assets` برسید:

```sql
SELECT a.data FROM result_media m JOIN assets a USING(digest)
WHERE m.key = :key AND m.filename = :filename;
```

تلفظ‌های جدول صرف هر مدخل در `entry_media` است (نام فایل‌ها در HTML مدخل به شکل `src="..."` آمده).

## استفاده روی سرور (بات تلگرام، سایت)

- **کپی کنید، مشترک استفاده نکنید.** فایل را روی سرور کپی و فقط‌خواندنی باز کنید (`?mode=ro`). فقط Anki Card Generator باید در آن بنویسد؛ برای به‌روزرسانی سرور دوباره کپی کنید.
- **سرعت:** خواندن سریع است. اگر برای هر درخواست فایل را باز می‌کنید، به جایش یک اتصال برای هر worker نگه دارید.
- **آفلاین:** باتی که این فایل را می‌خواند به اینترنت و مرورگر نیاز ندارد. کلمه‌های جدید هنوز باید با Anki Card Generator (با اینترنت) گرفته شوند.
- **شرایط استفاده:** محتوا از سایت دیکشنری‌هاست (Lexin © OsloMet، Oxford، Cambridge، …). استفاده برای مطالعهٔ شخصی یک چیز است و ارائهٔ عمومی چیز دیگر؛ اول شرایط هر دیکشنری را بررسی کنید.
- **نسخه:** `PRAGMA user_version` را بخوانید؛ این راهنما نسخهٔ 3 را توضیح می‌دهد. فایل‌های قدیمی‌تر (0) HTML کامل را در `content` دارند و جدول `entries` ندارند؛ با **Upgrade storage** (صفحهٔ Database در پنجرهٔ تنظیمات) یا `python main.py --upgrade-cache` تبدیلشان کنید. فایل جدید را با نسخهٔ قدیمی برنامه باز نکنید.

## نگهداری

- **پشتیبان:** وقتی اجرایی در جریان نیست فایل را کپی کنید. `--upgrade-cache` خودش اول `dictionaries.before-<نسخه>.sqlite3` می‌سازد.
- **فشرده کردن:** بعد از حذف‌های بزرگ `VACUUM` (یا دکمهٔ Compact file).
- **سلامت:** `PRAGMA integrity_check` باید `ok` برگرداند.
- حذف از طریق پنجرهٔ تنظیمات یا `--clear-cache` مدخل‌ها و رسانه‌های بی‌استفاده را هم پاک می‌کند. با SQL مستقیم، با `PRAGMA foreign_keys = ON` از `results` حذف کنید (پیوندها خودکار پاک می‌شوند) و بعد ردیف‌های بی‌استفادهٔ `entries` و `assets` را پاک کنید.
