"""Supported interface for other projects, such as flash-cards.

Only the names in ``__all__`` are supported. ``API_VERSION`` increases when one of
them changes incompatibly; all other modules in ``app`` are internal.

Dictionary, audio, image, cache and network settings come from this repository's
config.toml, so a consumer only needs its own presentation settings:

    from app.api import Lookup, load_settings

    config = load_settings('../Meaning-Ankidroid/config.toml')
    with Lookup(config) as lookup:
        result = lookup.word('hus')
        for source in result.found():
            print(source.title, source.html)
"""

from dataclasses import dataclass
from pathlib import Path
import re

from app import __version__
from app.anki_exporter import display_sources
from app.app_config import Config, ConfigError, load_config
from app.sources import SOURCE_SPECS, SourceContext, dictionary_content, select_audio

__all__ = ['API_VERSION', '__version__', 'Config', 'ConfigError', 'SourceResult', 'WordResult', 'ImageResult',
           'Lookup', 'load_settings', 'enabled_sources', 'read_input_words', 'sanitize_html',
           'excel_formatted_cells']

API_VERSION = 1
EMPTY_MESSAGE = 'No exact entry/content received'


@dataclass(frozen=True)
class SourceResult:
    """One dictionary's result for one word."""
    name: str           # Config key, e.g. 'lexin'.
    title: str          # Display title, e.g. 'Lexin · Norwegian–English'.
    rtl: bool           # True when the content is right-to-left (e.g. Persian).
    status: str         # 'ok', 'empty' or 'fail'.
    html: str = ''      # Sanitized card HTML; image src values are filenames in WordResult.images.
    message: str = ''   # Reason for 'empty'/'fail'.
    cached: bool = False


@dataclass(frozen=True)
class WordResult:
    word: str
    language: str              # language.source
    translation_target: str    # language.translation_target
    sources: tuple             # SourceResult items in config order.
    audio: Path | None         # Headword pronunciation MP3, if available.
    images: tuple              # Local image Paths, in display order.
    issues: tuple              # {'word', 'source', 'message'} dicts raised while fetching this word.

    def found(self):
        """Sources that returned content (the images source included)."""
        return tuple(source for source in self.sources if source.status == 'ok')

    def source(self, name):
        return next((source for source in self.sources if source.name == name), None)


@dataclass(frozen=True)
class ImageResult:
    """Lookup.images(term): downloaded images for a search term."""
    term: str
    status: str                # 'ok', 'empty' or 'fail'
    paths: tuple               # Local image Paths, best first.
    credits: tuple             # Credit text per path (Commons: title | author | license | URLs).
    message: str = ''
    cached: bool = False
    issues: tuple = ()


def load_settings(path, check_files=False):
    """Load and validate config.toml.

    The Excel input and card style files are only checked when check_files=True,
    so a consumer that supplies its own words does not need them.
    """
    return load_config(path, check_files=check_files)


def sanitize_html(markup):
    """Safe HTML for user-written content such as an Excel Meaning cell (as with [meaning] html = true).

    Scripts, event handlers, iframes, forms, non-http(s) links and resource-loading styles are
    removed; tables, links, line breaks and inline colors/fonts stay.
    """
    from app.sources import clean_html
    return clean_html(str(markup), extra_tags=('u', 's', 'h1', 'h5', 'h6', 'code', 'pre', 'blockquote'),
                      extra_attributes=('style', 'title'))


def excel_formatted_cells(path, sheet, column, cells):
    """Excel cell text as HTML that keeps the formatting set in Excel (as for the Meaning column).

    Keeps bold, italic, underline, strike-through, text and solid fill colors, font size and family,
    also for parts of a cell (rich text); .xlsx and .xls. The workbook is only read.
    path: workbook; sheet: name or 0-based index; column: 0-based column index;
    cells: {Excel row number (1-based): the cell's plain text}.
    Returns {row: HTML} only for cells that have formatting; others stay plain text.
    """
    from pathlib import Path
    from app.excel_formatting import formatted_question, read_question_formats
    path = Path(path).resolve()
    config = Config(path, {'input': {'file': str(path), 'sheet': sheet}})
    records = [{'Kind': 'normal', 'InputRow': row, 'Meaning': text} for row, text in cells.items() if text]
    formats = read_question_formats(config, records, column, field='Meaning', include_normal=True)
    return {row: formatted_question({'Words': cells[row], 'QuestionRuns': runs}) for row, runs in formats.items()}


def enabled_sources(config):
    """Enabled sources compatible with language.source, in config order."""
    return display_sources(config)


def read_input_words(config):
    """Vocabulary words (blank/normal type) from the configured Excel workbook."""
    from app.exercises import read_records
    return [record['Words'] for record in read_records(config)[0] if record['Kind'] == 'normal']


class Lookup:
    """Fetches dictionary content, audio and images, reusing the shared cache.

    Holds network sessions and possibly a browser: use it as a context manager or call
    close(). One instance should be used by one thread at a time.
    """

    def __init__(self, config, context_factory=SourceContext):
        self.config = config
        self._context = context_factory(config)
        self._count = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def close(self):
        self._context.close()

    def word(self, word, sources=None, audio=True):
        """Look up one word. sources defaults to enabled_sources(config) and must be a subset of it."""
        word = str(word).strip()
        if not word:
            raise ValueError('word must not be blank')
        available = enabled_sources(self.config)
        names = available if sources is None else list(dict.fromkeys(sources))
        unknown = [name for name in names if name not in available]
        if unknown:
            raise ValueError(f'Sources not enabled for this language: {", ".join(unknown)}')
        ctx, start = self._context, len(self._context.errors)
        self._count += 1
        results = [self._source(name, word) for name in names]
        sound = self._audio(word) if audio else ''
        images = [path for result in results if result.name == 'images' for path, _ in self._image_files(result)]
        return WordResult(
            word=word, language=self.config.section('language')['source'],
            translation_target=self.config.section('language')['translation_target'],
            sources=tuple(results), audio=ctx.audio_dir / sound[7:-1] if sound else None,
            images=tuple(images), issues=tuple(dict(issue) for issue in ctx.errors[start:]))

    def images(self, term):
        """Search images for any term, e.g. a word's English meaning, using [sources.images] options.

        Results are cached by term like other dictionary results. [sources.images] must be
        enabled in the configuration passed to Lookup.
        """
        term = str(term).strip()
        if not term:
            raise ValueError('term must not be blank')
        if not self.config.section('sources').get('images', {}).get('enabled'):
            raise ValueError('sources.images is not enabled in this configuration')
        ctx, start = self._context, len(self._context.errors)
        self._count += 1
        result = self._source('images', term)
        files = self._image_files(result)
        return ImageResult(term=term, status=result.status, paths=tuple(path for path, _ in files),
                           credits=tuple(credit for _, credit in files), message=result.message,
                           cached=result.cached, issues=tuple(dict(issue) for issue in ctx.errors[start:]))

    def _image_files(self, result):
        """(local path, credit) pairs from an images SourceResult, in display order."""
        if result.status != 'ok':
            return []
        from bs4 import BeautifulSoup
        files = []
        for block in BeautifulSoup(result.html, 'html.parser').select('img'):
            filename = block.get('src', '')
            path = self._context.images_dir / filename
            if not filename or re.search(r'[/\\:]', filename) or not path.is_file():
                continue
            holder = block.find_parent(class_='image-result')
            credit = holder.select_one('.image-credit') if holder else None
            files.append((path, credit.get_text(' ', strip=True) if credit else ''))
        return files

    def _source(self, name, word):
        ctx, spec = self._context, SOURCE_SPECS[name]
        previous = len(ctx.errors)
        ctx.last_cache_hit = False
        try:
            with ctx.source_budget():
                content = dictionary_content(name, word, self._count, ctx)
        except Exception as exc:
            ctx.issue(word, name, exc)
            return SourceResult(name, spec.title, spec.rtl, 'fail', message=ctx.errors[-1]['message'])
        if content:
            return SourceResult(name, spec.title, spec.rtl, 'ok', content, cached=bool(ctx.last_cache_hit))
        if len(ctx.errors) == previous:
            ctx.issue(word, name, EMPTY_MESSAGE)
        failed = any(issue['source'] == name and issue['message'] != EMPTY_MESSAGE for issue in ctx.errors[previous:])
        return SourceResult(name, spec.title, spec.rtl, 'fail' if failed else 'empty', message=ctx.errors[-1]['message'])

    def _audio(self, word):
        from app.exercises import options
        if not options(self.config, 'normal')['audio']:
            return ''
        ctx = self._context
        try:
            with ctx.source_budget():
                return select_audio(word, self._count, ctx)
        except Exception as exc:
            ctx.issue(word, 'audio', exc)
            return ''
