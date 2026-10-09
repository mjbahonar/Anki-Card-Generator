"""Exact Bokmål entries and their headword pronunciation from Lexin."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.parse import quote

from bs4 import BeautifulSoup
from dotenv import load_dotenv


def normalize_headword(text):
    return " ".join(unicodedata.normalize("NFC", text).replace("|", "").split()).casefold()


def audio_filename(word, provider, language='no'):
    stem = re.sub(r'[^\w-]', '_', str(word), flags=re.UNICODE).strip('_')[:80] or 'word'
    digest = hashlib.sha256(str(word).encode('utf-8')).hexdigest()[:10]
    return f"{provider}_{language}_{stem}_{digest}.mp3"


def render_lexin_entry(entry_html):
    """Keep the full entry, including inflection, without site controls or scripts."""
    soup = BeautifulSoup(entry_html, 'html.parser')
    for node in soup.select('.tts-btn, .ordbank-table.mobile, summary, script, style, iframe, img, audio, button'):
        node.decompose()
    for node in soup.find_all('details'):
        node.unwrap()
    for node in soup.find_all('a'):
        node.unwrap()
    # Retain structural attributes only; site IDs, event handlers and styles are unnecessary.
    allowed = {'div', 'span', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'b', 'strong',
               'i', 'em', 'p', 'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'sup', 'sub'}
    for node in list(soup.find_all(True)):
        if node.name not in allowed:
            node.unwrap()
            continue
        node.attrs = {key: value for key, value in node.attrs.items()
                      if key in {'class', 'lang', 'colspan', 'rowspan'}}
    return ('<div class="gt-container lexin-container"><div class="gt-title">Lexin · Bokmål–English</div>'
            '<hr class="gt-separator"><div class="lexin-content"><ul class="search-table">'
            + str(soup) + '</ul></div></div>')


def choose_norwegian_audio(word, word_number, lexin_sound, google_tts):
    """Call Google only when Lexin did not return a successfully saved pronunciation."""
    if lexin_sound:
        return lexin_sound
    source = BeautifulSoup(google_tts(word, word_number), 'html.parser').find('source')
    if source and source.get('src'):
        return f"[sound:{source['src']}]"
    return ''


def save_lexin_audio(response, word, audio_directory=None, copy_to=None):
    if not response.ok:
        raise ValueError(f'Pronunciation HTTP {response.status}')
    data = response.body()
    if len(data) < 128 or not (data.startswith(b'ID3') or
                             (data[0] == 0xff and data[1] & 0xe0 == 0xe0)):
        raise ValueError('Pronunciation response is not an MP3')
    filename = audio_filename(word, 'lexin')
    audio_dir = Path(audio_directory) if audio_directory else Path(__file__).resolve().parent / 'Audio'
    audio_dir.mkdir(parents=True, exist_ok=True)
    local_path = audio_dir / filename
    local_path.write_bytes(data)
    load_dotenv()
    media_dir = os.getenv('ADDRESS') if copy_to is None else copy_to
    if media_dir:
        try:
            destination = Path(media_dir) / filename
            if destination.resolve() != local_path.resolve():
                shutil.copyfile(local_path, destination)
        except OSError as exc:
            print(f'[LEXIN] Could not copy pronunciation to ADDRESS: {exc}')
    return f'[sound:{filename}]'


def scrape_and_process_lexin(word, word_number, page, *, download_audio=True,
                             audio_directory=None, copy_to=None, timeout_seconds=20,
                             verbose=True, on_error=None):
    """Return (full first exact entry HTML, sound tag); audio failure keeps the entry."""
    def log(message):
        if verbose:
            print(message)

    log(f'[LEXIN] ({word_number}) {word}')
    entry_html = ''
    sound_tag = ''
    try:
        page.goto('https://lexin.oslomet.no/#/findwords/message.bokmal-english?q=' + quote(str(word), safe=''),
                  wait_until='domcontentloaded', timeout=timeout_seconds * 1000)
        page.locator('.search-table dd[data-type="LEM"][lang="nb"]').first.wait_for(timeout=timeout_seconds * 1000)
        entries = page.locator('ul.search-table')
        entry = None
        for index in range(entries.count()):
            candidate = entries.nth(index)
            lemmas = candidate.locator('dd[data-type="LEM"][lang="nb"]')
            if not lemmas.count():
                continue
            lemma = lemmas.first
            forms = lemma.locator('.grunnform')
            texts = forms.all_text_contents() if forms.count() else [lemma.inner_text()]
            if any(normalize_headword(text) == normalize_headword(str(word)) for text in texts):
                entry = candidate
                break
        if entry is None:
            log(f'[LEXIN] No exact headword for {word!r}')
            return '', ''
        entry_html = render_lexin_entry(entry.inner_html())
        if not download_audio:
            return entry_html, ''
        lemma = entry.locator('dd[data-type="LEM"][lang="nb"]').first
        forms = lemma.locator('.grunnform')
        button = lemma.locator('.tts-btn').first
        for index in range(forms.count()):
            if normalize_headword(forms.nth(index).inner_text()) == normalize_headword(str(word)):
                button = forms.nth(index).locator('xpath=..').locator('.tts-btn').first
                break
        try:
            # Leseweb generates a playlist, then an MP3 after the headword button is clicked.
            with page.expect_response(lambda r: '.mp3' in r.url.lower() and 'leseweb.dk/' in r.url,
                                      timeout=timeout_seconds * 1000) as pending:
                button.click(timeout=5000)
            sound_tag = save_lexin_audio(pending.value, word, audio_directory, copy_to)
        except Exception as exc:
            if on_error:
                on_error('lexin_audio', exc)
            log(f'[LEXIN] Pronunciation unavailable: {exc}')
    except Exception as exc:
        if on_error:
            on_error('lexin', exc)
        log(f'[LEXIN] Search failed for {word!r}: {exc}')
    return entry_html, sound_tag
