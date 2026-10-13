"""Exact Bokmål/Nynorsk entries and their headword pronunciation from Lexin."""

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


def render_lexin_entry(entry_html, variant='bokmal', table_sounds=None):
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
    for span in soup.select('.ordbank-table.desktop td > div > span'):
        form = normalize_headword(span.get_text(' ', strip=True))
        filename = (table_sounds or {}).get(form)
        if filename:
            audio = soup.new_tag('audio', preload='none', src=filename)
            audio['class'] = ['lexin-form-audio']
            audio['aria-label'] = 'Pronunciation: ' + span.get_text(' ', strip=True)
            span.insert_after(audio)
            button = soup.new_tag('button', type='button')
            button['class'] = ['lexin-form-play']
            button['aria-label'] = audio['aria-label']
            button['onclick'] = 'var a=this.nextElementSibling;a.currentTime=0;a.play().catch(function(){});'
            button.string = '▶'
            audio.insert_before(button)
    title = 'Nynorsk' if variant == 'nynorsk' else 'Bokmål'
    return (f'<div class="gt-container lexin-container"><div class="gt-title">Lexin · {title}–English</div>'
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


def save_lexin_audio(response, word, audio_directory=None, copy_to=None, language='no', provider='lexin'):
    if not response.ok:
        raise ValueError(f'Pronunciation HTTP {response.status}')
    data = response.body()
    if len(data) < 128 or not (data.startswith(b'ID3') or
                             (data[0] == 0xff and data[1] & 0xe0 == 0xe0)):
        raise ValueError('Pronunciation response is not an MP3')
    filename = audio_filename(word, provider, language)
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


def download_table_audio(entry, page, audio_directory, language, timeout_ms, on_error=None,
                         on_media=None, cache=True, fallback=None):
    """Only the exact entry's desktop inflection controls; repeated forms share media."""
    sounds = {}
    entry.locator('details').evaluate_all('(nodes) => nodes.forEach(node => node.open = true)')
    buttons = entry.locator('.ordbank-table.desktop td .tts-btn')
    for index in range(buttons.count()):
        button = buttons.nth(index)
        form = button.locator('xpath=..').locator('span').first.inner_text().strip()
        key = normalize_headword(form)
        if not key or key in sounds:
            continue
        directory = Path(audio_directory) if audio_directory else Path(__file__).resolve().parent / 'Audio'
        path = directory / audio_filename(form, 'lexin_table', language)
        try:
            data = path.read_bytes() if cache and path.is_file() else b''
            valid = len(data) >= 128 and (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224))
            if not valid:
                with page.expect_response(lambda response: '.mp3' in response.url.lower() and 'leseweb.dk/' in response.url,
                                          timeout=min(3000, timeout_ms())) as pending:
                    button.click(timeout=min(3000, timeout_ms()))
                save_lexin_audio(pending.value, form, directory, '', language, 'lexin_table')
            if on_media:
                on_media(path)
            sounds[key] = path.name
        except Exception as exc:
            try:
                if not fallback:
                    raise exc
                fallback_sound = fallback(form, language)
                sounds[key] = fallback_sound[7:-1]
            except Exception as fallback_error:
                if on_error:
                    on_error('lexin_table_audio', fallback_error)
    return sounds


def scrape_and_process_lexin(word, word_number, page, *, download_audio=True,
                             audio_directory=None, copy_to=None, timeout_seconds=20,
                             verbose=True, on_error=None, remaining_timeout=None, variant='bokmal',
                             table_audio=False, on_table_media=None, audio_cache=True, table_fallback=None):
    """Return (full first exact entry HTML, sound tag); audio failure keeps the entry."""
    def log(message):
        if verbose:
            print(message)

    def timeout_ms():
        return (remaining_timeout() if remaining_timeout else timeout_seconds) * 1000

    if variant not in ('bokmal', 'nynorsk'):
        raise ValueError('Lexin variant must be bokmal or nynorsk')
    language = 'nn' if variant == 'nynorsk' else 'nb'
    lemma_selector = f'dd[data-type="LEM"][lang="{language}"]'
    log(f'[LEXIN] ({word_number}) {word}')
    entry_html = ''
    sound_tag = ''
    try:
        page.goto(f'https://lexin.oslomet.no/#/findwords/message.{variant}-english?q=' + quote(str(word), safe=''),
                  wait_until='domcontentloaded', timeout=timeout_ms())
        page.locator('.search-table ' + lemma_selector).first.wait_for(timeout=timeout_ms())
        entries = page.locator('ul.search-table')
        entry = None
        for index in range(entries.count()):
            page.set_default_timeout(timeout_ms())
            candidate = entries.nth(index)
            lemmas = candidate.locator(lemma_selector)
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
        entry_html = render_lexin_entry(entry.inner_html(), variant)
        def render_with_table_audio():
            if not table_audio:
                return render_lexin_entry(entry.inner_html(), variant)
            sounds = download_table_audio(entry, page, audio_directory,
                                          'nn' if variant == 'nynorsk' else 'no', timeout_ms,
                                          on_error, on_table_media, audio_cache, table_fallback)
            return render_lexin_entry(entry.inner_html(), variant, sounds)
        if not download_audio:
            return render_with_table_audio(), ''
        lemma = entry.locator(lemma_selector).first
        forms = lemma.locator('.grunnform')
        button = lemma.locator('.tts-btn').first
        for index in range(forms.count()):
            if normalize_headword(forms.nth(index).inner_text()) == normalize_headword(str(word)):
                button = forms.nth(index).locator('xpath=..').locator('.tts-btn').first
                break
        try:
            # Leseweb generates a playlist, then an MP3 after the headword button is clicked.
            with page.expect_response(lambda r: '.mp3' in r.url.lower() and 'leseweb.dk/' in r.url,
                                      timeout=timeout_ms()) as pending:
                button.click(timeout=min(5000, timeout_ms()))
            sound_tag = save_lexin_audio(pending.value, word, audio_directory, copy_to,
                                         'nn' if variant == 'nynorsk' else 'no')
        except Exception as exc:
            if on_error:
                on_error('lexin_audio', exc)
            log(f'[LEXIN] Pronunciation unavailable: {exc}')
        entry_html = render_with_table_audio()
    except Exception as exc:
        if on_error:
            on_error('lexin', exc)
        log(f'[LEXIN] Search failed for {word!r}: {exc}')
    return entry_html, sound_tag
