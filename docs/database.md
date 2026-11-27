# Dictionary database guide

`Cache/dictionaries.sqlite3` is a plain SQLite 3 file. Anything that reads SQLite (Python's built-in `sqlite3`, Node, PHP, Go, DB Browser for SQLite) can use it; no server is needed. This guide describes the layout written by Anki Card Generator 5.12 and later (`PRAGMA user_version` = 3) and shows how to read words, resolve inflected forms and get audio.

The easiest and safest way from Python is the library interface (`from app import api`, see TECHNICAL.md), which handles everything below for you. Read on if you want to use the file directly, for example from a Telegram bot or a website.

## Tables

| Table | One row per | Main columns |
| --- | --- | --- |
| `results` | Looked-up word × dictionary × settings | `key`, `source`, `word`, `content`, `sound`, `documents`, `saved_at` |
| `entries` | Lexin entry (one meaning of one headword), stored once | `id`, `variant`, `headword`, `headword_key`, `html`, `raw` |
| `result_entries` | Link: which entries a Lexin result shows | `key`, `entry_id` |
| `entry_forms` | Word form in an entry's inflection table | `form`, `entry_id` |
| `assets` | Media file (MP3 or image), stored once | `digest` (SHA-256), `data` (bytes) |
| `result_media` | Link: a result's media files | `key`, `filename`, `kind`, `digest` |
| `entry_media` | Link: an entry's table pronunciations | `entry_id`, `filename`, `kind`, `digest` |

### `results`

- `key` — JSON text `[1, source, normalized word, {settings}]`. The settings are the dictionary options that change the result (for Lexin: `variant`, `entries`, `table_audio`, `headword_audio`, ...). The same word can therefore have several rows, one per settings combination; any of them is a valid answer.
- `source` — `lexin`, `oxford`, `bokmalsordboka`, `dict_com`, ...
- `word` — the word that was looked up (without `å`/`en`/`ei`/`et` and `!`).
- `content` — card HTML, with three special cases:
  - `''` (empty): **not found** — the dictionary answered and the word is not in it.
  - contains `<!--entry:ID-->`: a Lexin result. Replace each placeholder with the entry's HTML (`zlib.decompress(entries.html)` for that `id`). Text between placeholders, such as `<div class="lexin-form-note">gikk → <b>gå</b></div>`, is kept as is.
  - otherwise: the full HTML (other dictionaries).
- `sound` — Anki sound tag of the headword pronunciation, e.g. `[sound:lexin_no_hus_699f41dd2d.mp3]`, or empty.
- `documents` — JSON list: where the result came from (`url`), original page HTML or a reference to it (`entry`), and for answers built offline `{"offline_forms": true}`.
- `saved_at` — UTC time stamp.

### Status of a result

| Status | How to recognise it |
| --- | --- |
| Not found | `content = ''` |
| Indirect (inflected form, e.g. `gikk` → `gå`) | `content LIKE '%lexin-form-note%'`; the base word is inside `→ <b>…</b>` |
| Built offline from saved entries | `documents LIKE '%"offline_forms": true%'` |
| Found directly | anything else |

### `entries`

- `id` — SHA-256 of the entry HTML; referenced as `<!--entry:ID-->`.
- `variant` — `bokmal` or `nynorsk`.
- `headword`, `headword_key` — the entry's headword as shown and normalized (see below).
- `lexin_id` — Lexin's pronunciation id of the headword. All meanings of one headword share it, so it is **not** unique per entry.
- `html` — zlib-compressed UTF-8 card HTML of the entry (definition, examples, inflection table).
- `raw` — zlib-compressed original page HTML of the entry (archive).

### Normalization

Words in `results.key`, `entries.headword_key` and `entry_forms.form` are normalized like this:

```python
import unicodedata
def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).replace('|', '').split()).casefold()
```

## Recipes

All examples use only Python's standard library and open the file read-only.

```python
import json, re, sqlite3, unicodedata, zlib

db = sqlite3.connect('file:Cache/dictionaries.sqlite3?mode=ro', uri=True)

def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).replace('|', '').split()).casefold()

def expand(content):
    """Card HTML of a result: placeholders replaced by their stored entries."""
    def entry(match):
        blob = db.execute('SELECT html FROM entries WHERE id = ?', (match.group(1),)).fetchone()[0]
        return zlib.decompress(blob).decode('utf-8')
    return re.sub(r'<!--entry:([0-9a-f]{64})-->', entry, content)
```

### 1. Look up a word

```python
def lookup(word, source='lexin'):
    """Newest saved result of a word: (status, html) or None if it was never looked up."""
    rows = db.execute('SELECT key, content, documents FROM results WHERE source = ? ORDER BY saved_at DESC',
                      (source,)).fetchall()
    wanted = normalize(word)
    for key, content, documents in rows:
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

For many lookups, select by `word` first (`WHERE source = ? AND word = ?`) and fall back to the loop above only when the spelling differs.

### 2. Inflected form → base word

`entry_forms` lists every form of every saved entry (`gikk`, `går`, `gått`, ... → `gå`):

```python
def base_words(form, variant='bokmal'):
    """Headwords whose inflection table contains form, and whether form is itself a headword."""
    key = normalize(form)
    is_headword = db.execute('SELECT 1 FROM entries WHERE headword_key = ? AND variant = ? LIMIT 1',
                             (key, variant)).fetchone() is not None
    bases = [h for (h,) in db.execute(
        'SELECT DISTINCT e.headword FROM entry_forms f JOIN entries e ON e.id = f.entry_id '
        'WHERE f.form = ? AND e.variant = ? ORDER BY e.headword', (key, variant))]
    return is_headword, bases

base_words('gikk')    # (False, ['gå'])
base_words('bøker')   # (False, ['bok', 'bøk'])  - when both entries are saved
base_words('hus')     # (True,  ['hus', 'huse']) - a headword itself, and the imperative of huse
```

To show the base word's entries for an inflected form:

```python
def entries_for_form(form, variant='bokmal'):
    key = normalize(form)
    return [zlib.decompress(html).decode('utf-8') for (html,) in db.execute(
        'SELECT DISTINCT e.html FROM entry_forms f JOIN entries e ON e.id = f.entry_id '
        'WHERE f.form = ? AND e.variant = ? AND e.headword_key != ?', (key, variant, key))]
```

Rules worth copying from the app:

- If the word is a headword itself (`is_headword`), prefer its own result: `skrev` is a past tense of `skrive` **and** a noun of its own.
- The index only knows entries that were saved. A form whose other base word was never looked up gives an incomplete answer (`dokumenter` also belongs to `dokumentere`).
- One base word can have several entries (meanings); `gå` has several. `DISTINCT e.html` shows each once.

### 3. Plain text of an entry

The HTML keeps Lexin's structure. With BeautifulSoup (`pip install beautifulsoup4`):

```python
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')
headword = soup.select_one('.grunnform').get_text(strip=True)
english = [dd.get_text(' ', strip=True) for dd in soup.select('dd[lang="en"]')]
```

### 4. Audio

```python
def headword_audio(word):
    """MP3 bytes of a result's headword pronunciation, or None."""
    for key, sound in db.execute("SELECT key, sound FROM results WHERE source='lexin' AND sound != ''"):
        if json.loads(key)[2] == normalize(word):
            filename = sound[len('[sound:'):-1]
            row = db.execute('SELECT a.data FROM result_media m JOIN assets a USING(digest) '
                             'WHERE m.key = ? AND m.filename = ?', (key, filename)).fetchone()
            return row[0] if row else None
    return None
```

`assets.data` holds the exact file bytes; `digest` is their SHA-256. Table pronunciations of an entry are in `entry_media` (file names appear in the entry HTML as `src="..."`).

## Using it on a server (bot, website)

- **Copy, don't share.** Copy the file to the server and open it read-only (`?mode=ro`). Let only Anki Card Generator write to it; copy it again to update the server.
- **Speed.** Reads are fast; add nothing else. If the server opens the file per request, keep one connection per worker instead.
- **Offline.** A bot reading this file needs no internet and no browser. New words still need Anki Card Generator (with internet) to fetch them.
- **Terms of use.** The content comes from the dictionaries' websites (Lexin © OsloMet, Oxford, Cambridge, ...). Using it for your own study is one thing; serving it to the public is another — check each dictionary's terms first.
- **Versions.** Read `PRAGMA user_version`; this guide describes version 3. Older files (0) store full HTML in `content` and have no `entries` table; run **Upgrade storage** (settings window, Database page) or `python main.py --upgrade-cache` to convert them. Do not open a newer file with an older Anki Card Generator.

## Maintenance

- **Back up** by copying the file while no run is in progress. `--upgrade-cache` makes `dictionaries.before-<version>.sqlite3` first.
- **Compact** (`VACUUM`, or the Compact file button) after large deletions.
- **Integrity:** `PRAGMA integrity_check` should return `ok`.
- Deleting results through the settings window or `--clear-cache` also removes entries and media nothing else uses. With plain SQL, delete from `results` with `PRAGMA foreign_keys = ON` (links are removed automatically), then remove unused rows from `entries` and `assets`.
