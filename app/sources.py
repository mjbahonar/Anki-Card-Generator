"""Source registry and adapters. User choices live only in config.toml."""

from contextlib import contextmanager
from dataclasses import dataclass
import html
import re
import hashlib
from io import BytesIO
from pathlib import Path
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import time
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from PIL import UnidentifiedImageError
import requests

from app.lexin_scraper import audio_filename, normalize_headword, scrape_and_process_lexin


@dataclass(frozen=True)
class SourceSpec:
    title: str
    languages: tuple = ()        # Empty means any language.
    rtl: bool = False


# This order defines the permanent V4 Anki schema, independent of enabled/order settings.
SOURCE_SPECS = {
    'lexin': SourceSpec('Lexin · Norwegian–English', ('no', 'nb', 'nn')),
    'google_translate': SourceSpec('Google Translate'),
    'dict_com': SourceSpec('Dict.com', ('no', 'nb', 'en')),
    'fastdic': SourceSpec('Fastdic', ('en',), True),
    'faraazin': SourceSpec('Faraazin', ('en',), True),
    'b_amooz': SourceSpec('B-Amooz', ('en',), True),
    'dictionary_com': SourceSpec('Dictionary.com', ('en',)),
    'thesaurus': SourceSpec('Thesaurus.com', ('en',)),
    'google_dictionary': SourceSpec('Google Dictionary', ('en',)),
    'cambridge': SourceSpec('Cambridge Dictionary', ('en',)),
    'images': SourceSpec('Images'),
    'oxford': SourceSpec("Oxford Learner's Dictionary", ('en',)),
    'bokmalsordboka': SourceSpec('Bokmålsordboka', ('no', 'nb', 'nn')),
    'nynorskordboka': SourceSpec('Nynorskordboka', ('no', 'nb', 'nn')),
}


def supported(name, language):
    return not SOURCE_SPECS[name].languages or language in SOURCE_SPECS[name].languages


def clean_html(markup, extra_tags=(), extra_attributes=()):
    soup = BeautifulSoup(str(markup), 'html.parser')
    for tag in soup.select('script, style, iframe, svg, button, input, form, link, audio, mtab, .ex-tooltip'):
        tag.decompose()
    allowed = {'div', 'span', 'p', 'br', 'hr', 'b', 'strong', 'em', 'i', 'ul', 'ol', 'li',
               'dl', 'dt', 'dd', 'table', 'caption', 'thead', 'tbody', 'tr', 'td', 'th', 'h2', 'h3', 'h4', 'sup', 'sub', 'img', 'a'} | set(extra_tags)
    for tag in list(soup.find_all(True)):
        if tag.name == 'sense':
            tag.name = 'div'
            tag['class'] = ['dc-sense']
        if tag.name not in allowed:
            tag.unwrap()
            continue
        tag.attrs = {k: v for k, v in tag.attrs.items()
                     if k in {'class', 'lang', 'colspan', 'rowspan', 'src', 'alt', 'dir', 'href', *extra_attributes}}
        if tag.name == 'a' and not str(tag.get('href', '')).startswith(('https://', 'http://')):
            tag.unwrap()
            continue
        if re.search(r'url\s*\(|expression|@import|javascript:', str(tag.get('style', '')), re.I):
            tag.attrs.pop('style')  # Inline styles may set colors/fonts, never load resources.
        if tag.get('dir') not in ('ltr', 'rtl', 'auto'):
            tag.attrs.pop('dir', None)
        if tag.name == 'img':
            src = tag.get('src', '')
            if not src or '/' in src or '\\' in src or ':' in src:
                tag.decompose()
    return str(soup)


def block(name, content, rtl=None):
    content = clean_html(content)
    parsed = BeautifulSoup(content, 'html.parser')
    if not parsed.get_text(strip=True) and not parsed.find('img'):
        raise ValueError('No usable dictionary content received')
    direction = SOURCE_SPECS[name].rtl if rtl is None else rtl
    return (f'<div class="gt-container source-container" dir="{"rtl" if direction else "ltr"}">'
            f'<div class="gt-title">{html.escape(SOURCE_SPECS[name].title)}</div>'
            f'<hr class="gt-separator"><div class="source-content">{content}</div></div>')


class SourceContext:
    def __init__(self, config):
        self.config = config
        self.language = config.section('language')['source']
        self.request_timeout = config.section('runtime')['timeout_seconds']
        self.source_deadline = None
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.browser = self.playwright = None
        self.browser_error = None
        self.audio_dir = config.resolve(config.section('audio')['directory'])
        self.images_dir = config.resolve(config.section('output')['directory']) / 'media'
        self.media = set()
        self.errors = []
        self.lexin_results = {}
        self.lexin_audio_attempted = set()
        from app.dictionary_cache import DictionaryCache
        cache = config.data.get('dictionary_cache', {})
        self.dictionary_cache = (DictionaryCache(config.resolve(cache.get('path', 'Cache/dictionaries.sqlite3')))
                                 if cache.get('enabled', True) else None)
        self.cache_capture = None
        self.last_cache_hit = False

    def archive_image(self, remote, data, image_format, caption):
        if self.cache_capture is None:
            return
        suffix = {'JPEG': '.jpg', 'PNG': '.png', 'GIF': '.gif', 'WEBP': '.webp'}.get(image_format, '.bin')
        filename = hashlib.sha256(data).hexdigest() + suffix
        path = self.dictionary_cache.path.parent / 'media' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.cache_capture['archive'].add(path)
        self.cache_capture['documents'].append({'url': remote, 'caption': caption, 'assets': {remote: filename}})

    def capture_entry(self, markup, url):
        """Archive original entry HTML and its directly exposed image/audio files."""
        if self.cache_capture is None:
            return
        url = str(url)
        document = {'url': url, 'html': str(markup), 'assets': {}}
        self.cache_capture['documents'].append(document)
        soup = BeautifulSoup(str(markup), 'html.parser')
        urls = []
        for node in soup.select('img[src], audio[src], audio source[src], [data-src-mp3]'):
            if node.name == 'img' and node.find_parent(class_='tts-btn'):
                continue  # Replay icons are UI controls, not dictionary illustrations.
            value = node.get('data-src-mp3') or node.get('src')
            if value:
                urls.append((urljoin(url, value), 'image' if node.name == 'img' else 'audio'))
        for remote, kind in dict.fromkeys(urls):
            if not remote.startswith(('https://', 'http://')):
                continue
            try:
                if remote in self.cache_capture['urls']:
                    filename = self.cache_capture['urls'][remote]
                else:
                    response = self.session.get(remote, timeout=self.timeout)
                    response.raise_for_status()
                    data = response.content
                    self.check_budget()
                    if kind == 'audio':
                        if len(data) < 128 or not (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
                            raise ValueError('Dictionary audio is not MP3')
                        suffix = '.mp3'
                    elif data.lstrip().startswith((b'<svg', b'<?xml')):
                        root = ET.fromstring(data)
                        if root.tag.rsplit('}', 1)[-1] != 'svg':
                            raise ValueError('Dictionary image response is not SVG')
                        suffix = '.svg'
                    else:
                        from PIL import Image
                        with Image.open(BytesIO(data)) as image:
                            suffix = {'JPEG': '.jpg', 'PNG': '.png', 'GIF': '.gif', 'WEBP': '.webp'}.get(image.format)
                            image.verify()
                        if not suffix:
                            raise ValueError('Unsupported dictionary image format')
                    filename = hashlib.sha256(remote.encode()).hexdigest() + suffix
                    path = self.dictionary_cache.path.parent / 'media' / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    self.cache_capture['archive'].add(path)
                    self.cache_capture['urls'][remote] = filename
                document['assets'][remote] = filename
            except Exception as exc:
                document.setdefault('media_errors', []).append({'url': remote, 'message': str(exc)})
                message = (f'Could not archive {kind}: {remote} | '
                           + ('Response is not a supported image' if isinstance(exc, UnidentifiedImageError)
                              else str(exc)))
                self.issue(self.cache_capture['word'], 'dictionary_media', message)

    def cache_result(self, name, word, loader, audio=False):
        from app.dictionary_cache import cache_key
        self.last_cache_hit = False
        if self.dictionary_cache is None:
            return loader()
        key = cache_key(name, word, self.config, audio)
        try:
            cached = (None if self.config.data.get('dictionary_cache', {}).get('refresh', False)
                      else self.dictionary_cache.get(key, self))
            if (cached is None and name == 'lexin' and self.config.section('sources').get('lexin', {}).get('entries', 2) == 1
                    and not self.config.data.get('dictionary_cache', {}).get('refresh', False)):
                # Pre-multiple-entry caches hold one entry, so they only satisfy entries = 1.
                import json
                legacy = json.loads(key)
                legacy[3].pop('adapter_revision', None)
                legacy[3].pop('entries', None)
                legacy_key = json.dumps(legacy, sort_keys=True, ensure_ascii=False)
                cached = self.dictionary_cache.get(legacy_key, self)
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.issue(word, 'dictionary_cache', exc)
            cached = None
        if cached is not None:
            content, sound, documents = cached
            if name == 'lexin':
                self.lexin_results[word] = (content, sound)
                if audio:
                    self.lexin_audio_attempted.add(word)
            self.last_cache_hit = True
            return content
        previous = self.cache_capture
        capture = {'word': word, 'source': name, 'documents': [], 'archive': set(), 'urls': {}, 'media': set()}
        self.cache_capture = capture
        errors = len(self.errors)
        try:
            content = loader()
            self.check_budget()
            # Optional archive failures must not discard valid card text/audio.
            # Incomplete dictionary/card fetches still retain the old good result.
            if content and not any(e['source'] not in ('media_copy', 'dictionary_media') for e in self.errors[errors:]):
                sound = self.lexin_results.get(word, ('', ''))[1] if name == 'lexin' else ''
                media = [(p, 'audio' if p.suffix.lower() == '.mp3' else 'image') for p in capture['media']]
                media.extend((p, 'archive') for p in capture['archive'])
                try:
                    self.dictionary_cache.put(key, name, word, content, sound, capture['documents'], media)
                except (OSError, sqlite3.Error) as exc:
                    self.issue(word, 'dictionary_cache', exc)
            return content
        finally:
            self.cache_capture = previous

    def check_budget(self):
        if self.source_deadline is not None and time.monotonic() >= self.source_deadline:
            raise TimeoutError('Source time limit exceeded; moving to the next source')

    @property
    def timeout(self):
        self.check_budget()
        if self.source_deadline is None:
            return self.request_timeout
        return min(self.request_timeout, max(.001, self.source_deadline - time.monotonic()))

    @contextmanager
    def source_budget(self):
        previous = self.source_deadline
        seconds = self.config.section('runtime').get('source_timeout_seconds', 30)
        self.source_deadline = time.monotonic() + seconds if seconds else None
        try:
            yield
            self.check_budget()
        finally:
            self.source_deadline = previous

    def pause(self, seconds):
        self.check_budget()
        if self.source_deadline is not None:
            seconds = min(seconds, max(0, self.source_deadline - time.monotonic()))
        time.sleep(seconds)
        self.check_budget()

    def issue(self, word, source, message):
        if isinstance(message, requests.HTTPError) and message.response is not None:
            status = message.response.status_code
            message = f'HTTP {status}' + (' (rate limited; try again later)' if status == 429 else ' (source unavailable)')
        self.errors.append({'word': word, 'source': source, 'message': str(message)})

    def fetch(self, url):
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        self.check_budget()
        # Oxford captures its entry itself; images archive only the chosen files,
        # never every thumbnail on a search results page.
        if (self.cache_capture is not None and self.cache_capture['source'] not in ('oxford', 'images')
                and 'html' in response.headers.get('Content-Type', '')):
            soup = BeautifulSoup(response.text, 'html.parser')
            entries = soup.select('.entry, section.results__container, .container.mt-2, #id-sec-entry-group-dcom, section.synonym-antonym-panel')
            self.capture_entry(''.join(str(el) for el in entries) or response.text, response.url)
        return response

    @contextmanager
    def page(self):
        if self.browser_error:
            raise RuntimeError(self.browser_error)
        if self.browser is None:
            # An expired source budget belongs to this source, not the browser.
            timeout = self.timeout
            try:
                from playwright.sync_api import sync_playwright, TimeoutError as LaunchTimeout
            except Exception as exc:
                self.browser_error = f'Browser unavailable; run pip install -r requirements.txt. {exc}'
                raise RuntimeError(self.browser_error) from exc
            try:
                if self.playwright is None:
                    self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(
                    headless=self.config.section('runtime')['headless'], timeout=timeout * 1000)
            except LaunchTimeout as exc:
                # A slow cold start must not disable every later browser source.
                raise TimeoutError(f'Browser launch timed out: {exc}') from exc
            except Exception as exc:
                self.browser_error = f'Browser unavailable; run python -m playwright install chromium. {exc}'
                raise RuntimeError(self.browser_error) from exc
        page = self.browser.new_page()
        try:
            page.set_default_timeout(self.timeout * 1000)
            yield page
        finally:
            page.close()

    def browse(self, url, selector):
        with self.page() as page:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout * 1000)
            page.locator(selector).first.wait_for(timeout=self.timeout * 1000)
            soup = BeautifulSoup(page.content(), 'html.parser')
            self.capture_entry(''.join(str(el) for el in soup.select(selector)), page.url)
            return soup

    def audio_language(self, provider):
        if provider == 'lexin':
            variant = self.config.section('sources').get('lexin', {}).get(
                'variant', 'nynorsk' if self.language == 'nn' else 'bokmal')
            return 'nn' if variant == 'nynorsk' or (variant == 'both' and self.language == 'nn') else 'no'
        return 'no' if self.language == 'nb' or (provider == 'google_tts' and self.language == 'nn') else self.language

    def save_audio(self, word, provider, data):
        if len(data) < 128 or not (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
            raise ValueError('Response is not a valid MP3')
        language = self.audio_language(provider)
        path = self.audio_dir / audio_filename(word, provider, language)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.register_audio(path)

    def register_audio(self, path):
        self.register_media(path)
        return f'[sound:{path.name}]'

    def register_media(self, path):
        path = Path(path).resolve()
        self.media.add(path)
        if self.cache_capture is not None:
            self.cache_capture['media'].add(path)
        destination = self.config.data.get('media', {}).get('anki_directory',
                      self.config.section('audio').get('copy_to', ''))
        if destination:
            try:
                target = self.config.resolve(destination) / path.name
                if target.resolve() != path.resolve():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
            except OSError as exc:
                self.issue(path.name, 'media_copy', exc)
        return path

    def cached_audio(self, word, provider):
        language = self.audio_language(provider)
        path = self.audio_dir / audio_filename(word, provider, language)
        if self.config.section('audio')['cache'] and path.is_file():
            data = path.read_bytes()
            if len(data) > 128 and (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
                return self.register_audio(path)
        return ''

    def table_audio_fallback(self, form, language):
        from app.exercises import exercise_audio
        return exercise_audio(form, language, self)

    def cached_table_audio_fallback(self, form, language):
        from app.exercises import cached_exercise_audio
        return cached_exercise_audio(form, language, self)

    def lexin(self, word, number, audio=False):
        return self.cache_result('lexin', word, lambda: self._lexin(word, number, audio), audio)

    def _lexin(self, word, number, audio=False):
        if audio:
            self.lexin_audio_attempted.add(word)
        cached = self.cached_audio(word, 'lexin') if audio else ''
        variant = self.config.section('sources').get('lexin', {}).get(
            'variant', 'nynorsk' if self.language == 'nn' else 'bokmal')
        variants = ('bokmal', 'nynorsk') if variant == 'both' else (variant,)
        primary = variant if variant != 'both' else ('nynorsk' if self.language == 'nn' else 'bokmal')
        contents, sound = [], ''
        for selected in variants:
            with self.page() as page:
                content, selected_sound = scrape_and_process_lexin(
                    word, number, page, download_audio=audio and selected == primary and not bool(cached),
                    audio_directory=self.audio_dir, copy_to='', timeout_seconds=self.timeout,
                    verbose=False, on_error=lambda source, error: self.issue(word, source, error),
                    remaining_timeout=lambda: self.timeout, variant=selected,
                    table_audio=(self.config.section('audio')['enabled'] and
                                 self.config.data.get('cards', {}).get('normal', {}).get('audio', True) and
                                 self.config.section('sources').get('lexin', {}).get('table_audio', False)),
                    on_table_media=self.register_audio,
                    audio_cache=self.config.section('audio')['cache'],
                    table_fallback=self.table_audio_fallback,
                    table_cached_fallback=self.cached_table_audio_fallback,
                    on_entry=lambda markup: self.capture_entry(markup, page.url),
                    max_entries=self.config.section('sources').get('lexin', {}).get('entries', 2))
            contents.append(content)
            sound = selected_sound or sound
        content = ''.join(contents)
        if sound:
            sound = self.register_audio(self.audio_dir / sound[7:-1])
        self.lexin_results[word] = (content, cached or sound)
        return content

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        finally:
            try:
                if self.playwright:
                    self.playwright.stop()
            finally:
                self.session.close()


def dictionary_content(name, word, number, ctx):
    if name == 'lexin':
        return _dictionary_content(name, word, number, ctx)
    if isinstance(ctx, SourceContext):
        return ctx.cache_result(name, word, lambda: _dictionary_content(name, word, number, ctx))
    return _dictionary_content(name, word, number, ctx)


def _dictionary_content(name, word, number, ctx):
    encoded = quote(word, safe='')
    if name in ('bokmalsordboka', 'nynorskordboka'):
        from app.ordbokene_scraper import ordbokene_content
        return block(name, ordbokene_content(word, 'bm' if name == 'bokmalsordboka' else 'nn', ctx))
    if name == 'oxford':
        from app.oxford_scraper import oxford_content
        return block(name, oxford_content(word, ctx))
    if name == 'lexin':
        priority = word_audio_priority(ctx.config)
        audio = (ctx.config.section('audio')['enabled'] and priority and priority[0] == 'lexin'
                 and ctx.config.data.get('cards', {}).get('normal', {}).get('audio', True))
        return ctx.lexin(word, number, audio=audio)
    if name == 'google_translate':
        runtime = ctx.config.section('runtime')
        target = ctx.config.section('language')['translation_target']
        for attempt in range(runtime['translation_attempts']):
            try:
                if target == ctx.language:
                    translated = word
                else:
                    response = ctx.session.get('https://translate.google.com/m',
                                               params={'sl': ctx.language, 'tl': target, 'q': word}, timeout=ctx.timeout)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    element = soup.select_one('.result-container, .t0')
                    if element:
                        ctx.capture_entry(str(element), response.url)
                    translated = element.get_text(strip=True) if element else ''
                if not translated:
                    raise ValueError('Empty translation')
                return block(name, html.escape(translated), rtl=target in ['fa', 'ar', 'he', 'ur'])
            except Exception:
                if attempt + 1 == runtime['translation_attempts']:
                    raise
                ctx.pause(runtime['retry_delay_seconds'] * (attempt + 1))
    if name == 'dict_com':
        # This is the same bidirectional pair for both input languages. An unknown
        # English route can silently fall back to the site's German dictionary.
        soup = ctx.browse(f'https://dict.com/engelsk-norsk/{encoded}', '#entry-body .main-body sense')
        headword = soup.select_one('#entry-header .lex_ful_entr')
        # Dict.com marks irregular English verbs with a trailing asterisk (eat*).
        if not headword or normalize_headword(headword.get_text().rstrip('*')) != normalize_headword(word):
            raise ValueError('No exact dictionary entry')
        content = ''.join(str(el) for el in soup.select('#entry-header .lex_ful_entr, #entry-rest .lex_ful_morf, #entry-body > .main-body'))
        return '<div class="dc-container"><div class="gt-title">Dict.com</div><hr class="gt-separator"><div class="dc-content">' + clean_html(content) + '</div></div>'
    if name in ['fastdic', 'b_amooz', 'thesaurus', 'dictionary_com']:
        routes = {
            'fastdic': (f'https://fastdic.com/word/{encoded}', 'section.results__container'),
            'b_amooz': (f'https://dic.b-amooz.com/en/dictionary/w?word={encoded}', '.container.mt-2'),
            'thesaurus': (f'https://www.thesaurus.com/browse/{encoded}', 'section.synonym-antonym-panel'),
            'dictionary_com': (f'https://www.dictionary.com/browse/{encoded}', '#id-sec-entry-group-dcom'),
        }
        url, selector = routes[name]
        soup = BeautifulSoup(ctx.fetch(url).text, 'html.parser')
        elements = soup.select(selector)
        if not elements:
            raise ValueError('Dictionary definition not found (site may have changed)')
        for el in soup.select('#faqs, #cite, .fd-sidebar, .relevant, .suggestion-form-btn, .tab-wrapper.tab-big'):
            el.decompose()
        if name == 'fastdic':
            pieces = []
            limit = ctx.config.section('sources')[name].get('examples_per_definition', 3)
            for meaning in soup.select('.meaning'):
                definition = meaning.find('p', recursive=False)
                if not definition:
                    continue
                pos = meaning.select_one('.pos')
                pieces.append('<div class="definition-group"><div class="part-of-speech">'
                              + html.escape(pos.get_text(' ', strip=True) if pos else '') + '</div><p>'
                              + html.escape(definition.get_text(' ', strip=True)) + '</p>')
                for example in meaning.select('.result__sentences')[:limit]:
                    sentences = example.select('.sentence p')
                    if sentences:
                        pieces.append('<div class="example" dir="ltr">' + html.escape(sentences[0].get_text(' ', strip=True)) + '</div>')
                    if len(sentences) > 1:
                        pieces.append('<div class="example translation" dir="rtl">' + html.escape(sentences[1].get_text(' ', strip=True)) + '</div>')
                pieces.append('</div>')
            if not pieces:
                raise ValueError('Fastdic definitions not found')
            return block(name, ''.join(pieces))
        return block(name, ''.join(str(el) for el in elements))
    if name in ['faraazin', 'cambridge', 'google_dictionary']:
        routes = {
            'faraazin': (f'https://www.faraazin.ir/?q={encoded}', '.translate-details'),
            'cambridge': (f'https://dictionary.cambridge.org/dictionary/english/{encoded}', '.entry-body'),
            'google_dictionary': (f'https://www.google.com/search?hl=en&q=define+{encoded}', '.lr_container'),
        }
        url, selector = routes[name]
        soup = ctx.browse(url, selector)
        if name == 'cambridge':
            pieces, seen = [], set()
            limit = ctx.config.section('sources')[name].get('examples_per_definition', 3)
            for definition in soup.select('.entry-body .def-block'):
                text_node = definition.select_one('.def')
                if not text_node:
                    continue
                text = text_node.get_text(' ', strip=True)
                if text in seen:
                    continue
                seen.add(text)
                pieces.append('<div class="definition-group"><p><strong>' + html.escape(text) + '</strong></p>')
                for example in definition.select('.examp')[:limit]:
                    pieces.append('<div class="example">' + html.escape(example.get_text(' ', strip=True)) + '</div>')
                pieces.append('</div>')
            if not pieces:
                raise ValueError('Cambridge definitions not found')
            return block(name, ''.join(pieces))
        return block(name, ''.join(str(el) for el in soup.select(selector)))
    if name == 'images':
        from app.image_sources import download_images
        return block(name, download_images(word, ctx))
    raise ValueError(f'No adapter for {name}')


def word_audio_priority(config):
    """Headword audio providers for language.source; unlisted languages use audio.priority."""
    audio, language = config.section('audio'), config.section('language')['source']
    table = audio.get('word', {})
    for code in (language, 'no' if language in ('nb', 'nn') else None):
        if code in table:
            return table[code]
    return audio['priority']


def select_audio(word, number, ctx):
    if not ctx.config.section('audio')['enabled']:
        return ''
    for provider in word_audio_priority(ctx.config):
        if provider == 'lexin' and ctx.language not in ['no', 'nb', 'nn']:
            continue
        if provider == 'fastdic' and ctx.language != 'en':
            continue
        cache_provider = ('fastdic_' + ctx.config.section('audio')['english_accent'] if provider == 'fastdic'
                          else provider)
        try:
            cached = ctx.cached_audio(word, cache_provider)
            if cached:
                return cached
            if provider == 'lexin':
                if word not in ctx.lexin_audio_attempted:
                    ctx.lexin(word, number, audio=True)
                sound = ctx.lexin_results.get(word, ('', ''))[1]
                if not sound:
                    raise ValueError('No headword pronunciation available')
                return sound
            if provider == 'fastdic':
                soup = BeautifulSoup(ctx.fetch('https://fastdic.com/word/' + quote(word, safe='')).text, 'html.parser')
                accent = ctx.config.section('audio')['english_accent']
                span = soup.select_one(f'span.audio.js-audio[data-type="{accent}"]')
                if not span or not span.get('data-src'):
                    raise ValueError('Pronunciation not found')
                url = f'https://cdn.fastdic.com/c-en-audios/{accent}/mp3/{span["data-src"]}.mp3'
                return ctx.save_audio(word, cache_provider, ctx.fetch(url).content)
            if provider == 'google_tts':
                from gtts import gTTS
                buffer = BytesIO()
                language = ctx.audio_language('google_tts')
                gTTS(text=word, lang=language, timeout=ctx.timeout).write_to_fp(buffer)
                return ctx.save_audio(word, cache_provider, buffer.getvalue())
        except Exception as exc:
            ctx.issue(word, provider + '_audio', exc)
    return ''
