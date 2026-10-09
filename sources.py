"""Source registry and adapters. User choices live only in config.toml."""

from contextlib import contextmanager
from dataclasses import dataclass
import html
from io import BytesIO
from pathlib import Path
import shutil
import time
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
import requests

from lexin_scraper import audio_filename, normalize_headword, scrape_and_process_lexin


@dataclass(frozen=True)
class SourceSpec:
    title: str
    languages: tuple = ()        # Empty means any language.
    rtl: bool = False


# This order defines the permanent V4 Anki schema, independent of enabled/order settings.
SOURCE_SPECS = {
    'lexin': SourceSpec('Lexin · Bokmål–English', ('no', 'nb')),
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
}


def supported(name, language):
    return not SOURCE_SPECS[name].languages or language in SOURCE_SPECS[name].languages


def clean_html(markup):
    soup = BeautifulSoup(str(markup), 'html.parser')
    for tag in soup.select('script, style, iframe, svg, button, input, form, link, audio, mtab, .ex-tooltip'):
        tag.decompose()
    allowed = {'div', 'span', 'p', 'br', 'hr', 'b', 'strong', 'em', 'i', 'ul', 'ol', 'li',
               'dl', 'dt', 'dd', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'h2', 'h3', 'h4', 'sup', 'sub', 'img'}
    for tag in list(soup.find_all(True)):
        if tag.name == 'sense':
            tag.name = 'div'
            tag['class'] = ['dc-sense']
        if tag.name not in allowed:
            tag.unwrap()
            continue
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in {'class', 'lang', 'colspan', 'rowspan', 'src', 'alt'}}
        if tag.name == 'img':
            src = tag.get('src', '')
            if not src or '/' in src or '\\' in src or ':' in src:
                tag.decompose()
    return str(soup)


def block(name, content, rtl=None):
    direction = SOURCE_SPECS[name].rtl if rtl is None else rtl
    return (f'<div class="gt-container source-container" dir="{"rtl" if direction else "ltr"}">'
            f'<div class="gt-title">{html.escape(SOURCE_SPECS[name].title)}</div>'
            f'<hr class="gt-separator"><div class="source-content">{clean_html(content)}</div></div>')


class SourceContext:
    def __init__(self, config):
        self.config = config
        self.language = config.section('language')['source']
        self.timeout = config.section('runtime')['timeout_seconds']
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

    def issue(self, word, source, message):
        if isinstance(message, requests.HTTPError) and message.response is not None:
            status = message.response.status_code
            message = f'HTTP {status}' + (' (rate limited; try again later)' if status == 429 else ' (source unavailable)')
        self.errors.append({'word': word, 'source': source, 'message': str(message)})
        print(f'  [{source}] {word}: {message}', flush=True)

    def fetch(self, url):
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    @contextmanager
    def page(self):
        if self.browser_error:
            raise RuntimeError(self.browser_error)
        if self.browser is None:
            try:
                from playwright.sync_api import sync_playwright
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=self.config.section('runtime')['headless'])
            except Exception as exc:
                self.browser_error = f'Browser unavailable; run python -m playwright install chromium. {exc}'
                raise RuntimeError(self.browser_error) from exc
        page = self.browser.new_page()
        page.set_default_timeout(self.timeout * 1000)
        try:
            yield page
        finally:
            page.close()

    def browse(self, url, selector):
        with self.page() as page:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout * 1000)
            page.locator(selector).first.wait_for()
            return BeautifulSoup(page.content(), 'html.parser')

    def save_audio(self, word, provider, data):
        if len(data) < 128 or not (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
            raise ValueError('Response is not a valid MP3')
        language = 'no' if self.language == 'nb' else self.language
        path = self.audio_dir / audio_filename(word, provider, language)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.register_audio(path)

    def register_audio(self, path):
        self.media.add(Path(path).resolve())
        destination = self.config.section('audio')['copy_to']
        if destination:
            try:
                target = self.config.resolve(destination) / path.name
                if target.resolve() != path.resolve():
                    shutil.copyfile(path, target)
            except OSError as exc:
                self.issue(path.name, 'audio_copy', exc)
        return f'[sound:{path.name}]'

    def cached_audio(self, word, provider):
        language = 'no' if self.language == 'nb' else self.language
        path = self.audio_dir / audio_filename(word, provider, language)
        if self.config.section('audio')['cache'] and path.is_file():
            data = path.read_bytes()
            if len(data) > 128 and (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
                return self.register_audio(path)
        return ''

    def lexin(self, word, number, audio=False):
        if audio:
            self.lexin_audio_attempted.add(word)
        cached = self.cached_audio(word, 'lexin') if audio else ''
        with self.page() as page:
            content, sound = scrape_and_process_lexin(
                word, number, page, download_audio=audio and not bool(cached),
                audio_directory=self.audio_dir, copy_to='', timeout_seconds=self.timeout)
        if sound:
            sound = self.register_audio(self.audio_dir / sound[7:-1])
        self.lexin_results[word] = (content, cached or sound)
        return content

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        finally:
            if self.playwright:
                self.playwright.stop()
            self.session.close()


def dictionary_content(name, word, number, ctx):
    encoded = quote(word, safe='')
    if name == 'lexin':
        priority = ctx.config.section('audio')['priority']
        audio = ctx.config.section('audio')['enabled'] and priority and priority[0] == 'lexin'
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
                    translated = element.get_text(strip=True) if element else ''
                if not translated:
                    raise ValueError('Empty translation')
                return block(name, html.escape(translated), rtl=target in ['fa', 'ar', 'he', 'ur'])
            except Exception:
                if attempt + 1 == runtime['translation_attempts']:
                    raise
                time.sleep(runtime['retry_delay_seconds'] * (attempt + 1))
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
        from PIL import Image
        soup = BeautifulSoup(ctx.fetch(f'https://www.google.com/search?tbm=isch&q={encoded}+clipart').text, 'html.parser')
        markup = []
        count = ctx.config.section('sources')[name].get('count', 3)
        for img in soup.select('img')[1:count + 1]:
            try:
                src = urljoin('https://www.google.com/', img.get('src', ''))
                data = ctx.fetch(src).content
                image = Image.open(BytesIO(data))
                image.thumbnail((800, 800))
                filename = audio_filename(word, 'image').removesuffix('.mp3') + f'_{len(markup)}.png'
                ctx.images_dir.mkdir(parents=True, exist_ok=True)
                path = ctx.images_dir / filename
                image.save(path, format='PNG')
                ctx.media.add(path.resolve())
                markup.append(f'<img src="{filename}" alt="{html.escape(word, quote=True)}">')
            except Exception as exc:
                ctx.issue(word, 'images', exc)
        if not markup:
            raise ValueError('No images downloaded')
        return block(name, ''.join(markup))
    raise ValueError(f'No adapter for {name}')


def select_audio(word, number, ctx):
    if not ctx.config.section('audio')['enabled']:
        return ''
    for provider in ctx.config.section('audio')['priority']:
        if provider == 'lexin' and ctx.language not in ['no', 'nb']:
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
                language = 'no' if ctx.language == 'nb' else ctx.language
                gTTS(text=word, lang=language, timeout=ctx.timeout).write_to_fp(buffer)
                return ctx.save_audio(word, cache_provider, buffer.getvalue())
        except Exception as exc:
            ctx.issue(word, provider + '_audio', exc)
    return ''
