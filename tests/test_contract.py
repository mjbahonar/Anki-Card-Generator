"""Contract tests: what other projects (the sibling flash-cards project) rely on.

A failure here means a change in this repository would break those projects. If the change
is intended: update the projects that use it, and for app.api changes raise API_VERSION and
follow RELEASING.md (an incompatible app.api change is a MAJOR version). See TECHNICAL.md,
"Using this repository as a library".
"""
import base64
from dataclasses import fields
import inspect
from io import BytesIO
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from PIL import Image

from app import api
from app.app_config import Config, load_config
from app.lexin_scraper import render_lexin_entry
from app.sources import SOURCE_SPECS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
BREAKS = 'This would break flash-cards (see tests/test_contract.py): '


def lexin_card(table_sounds=None):
    """Card HTML from the saved original Lexin entry for "hus", made by the current code."""
    raw = BeautifulSoup((FIXTURES / 'lexin_hus_entry.html').read_text(encoding='utf-8'), 'html.parser')
    entry = raw.select_one('ul.search-table')
    return BeautifulSoup(render_lexin_entry(entry.decode_contents(), 'bokmal', table_sounds), 'html.parser')


class ApiContractTests(unittest.TestCase):
    def test_public_names(self):
        self.assertEqual(api.API_VERSION, 1, BREAKS + 'API_VERSION changed; update the consumers first')
        expected = {'API_VERSION', '__version__', 'Config', 'ConfigError', 'SourceResult', 'WordResult',
                    'ImageResult', 'Lookup', 'load_settings', 'enabled_sources', 'read_input_words', 'sanitize_html', 'excel_formatted_cells'}
        self.assertTrue(expected <= set(api.__all__), BREAKS + f'missing {expected - set(api.__all__)}')
        for name in expected:
            self.assertTrue(hasattr(api, name), BREAKS + name)

    def test_signatures(self):
        def parameters(function):
            return [(p.name, p.default) for p in inspect.signature(function).parameters.values()]
        empty = inspect.Parameter.empty
        self.assertEqual(parameters(api.load_settings), [('path', empty), ('check_files', False)], BREAKS + 'load_settings')
        self.assertEqual(parameters(api.enabled_sources), [('config', empty)], BREAKS + 'enabled_sources')
        self.assertEqual(parameters(api.read_input_words), [('config', empty)], BREAKS + 'read_input_words')
        self.assertEqual(parameters(api.Lookup.__init__)[:2], [('self', empty), ('config', empty)], BREAKS + 'Lookup()')
        self.assertEqual(parameters(api.Lookup.word), [('self', empty), ('word', empty), ('sources', None), ('audio', True)],
                         BREAKS + 'Lookup.word')
        self.assertEqual(parameters(api.Lookup.images), [('self', empty), ('term', empty)], BREAKS + 'Lookup.images')
        self.assertEqual(parameters(api.sanitize_html), [('markup', empty)], BREAKS + 'sanitize_html')
        self.assertEqual(parameters(api.excel_formatted_cells),
                         [('path', empty), ('sheet', empty), ('column', empty), ('cells', empty)], BREAKS + 'excel_formatted_cells')
        for method in ('__enter__', '__exit__', 'close'):
            self.assertTrue(callable(getattr(api.Lookup, method)), BREAKS + 'Lookup.' + method)

    def test_result_fields(self):
        def names(cls):
            return [field.name for field in fields(cls)]
        self.assertEqual(names(api.SourceResult), ['name', 'title', 'rtl', 'status', 'html', 'message', 'cached'],
                         BREAKS + 'SourceResult fields')
        self.assertEqual(names(api.WordResult), ['word', 'language', 'translation_target', 'sources', 'audio', 'images', 'issues'],
                         BREAKS + 'WordResult fields')
        self.assertEqual(names(api.ImageResult), ['term', 'status', 'paths', 'credits', 'message', 'cached', 'issues'],
                         BREAKS + 'ImageResult fields')
        result = api.WordResult('hus', 'no', 'en', (api.SourceResult('lexin', 'Lexin', False, 'ok', '<p>x</p>'),), None, (), ())
        self.assertEqual([s.name for s in result.found()], ['lexin'], BREAKS + 'WordResult.found()')
        self.assertEqual(result.source('lexin').title, 'Lexin', BREAKS + 'WordResult.source()')

    def test_source_names_and_statuses(self):
        for name in ('lexin', 'google_translate', 'images', 'bokmalsordboka', 'dict_com'):
            self.assertIn(name, SOURCE_SPECS, BREAKS + f'source name {name!r}')


class LexinHtmlContractTests(unittest.TestCase):
    """flash-cards turns Lexin card HTML into headword, word class, meanings, examples and forms."""

    def test_entry_rows(self):
        card = lexin_card()
        entries = card.select('ul.search-table')
        self.assertEqual(len(entries), 1, BREAKS + 'one ul.search-table per Lexin entry')
        rows = entries[0].select('dt')
        self.assertTrue(rows and all(dt.find_next_sibling('dd') for dt in rows), BREAKS + 'dt/dd row pairs')
        labels = {dt.select_one('.nor-text-new').get_text(strip=True) for dt in rows if dt.select_one('.nor-text-new')}
        self.assertTrue({'oppslagsord', 'ordklasse', 'forklaring'} <= labels, BREAKS + f'row labels {labels}')
        languages = {(dt.select_one('span.dynamic') or dt).get_text(strip=True) for dt in rows}
        self.assertTrue({'Bokmål', 'Engelsk'} <= languages, BREAKS + f'row languages {languages}')

    def test_headword_pronunciation_and_table(self):
        card = lexin_card()
        self.assertEqual(card.select_one('.grunnform').get_text(strip=True), 'hus', BREAKS + '.grunnform')
        self.assertIn('/hu:s/', card.select_one('.pronunciation').get_text(), BREAKS + '.pronunciation')
        tables = card.select('table.inflection-table')
        self.assertEqual(len(tables), 1, BREAKS + 'one table.inflection-table (mobile copy removed)')
        self.assertIn('huset', tables[0].get_text(), BREAKS + 'inflection forms in the table cells')

    def test_table_pronunciations(self):
        card = lexin_card({'huset': 'lexin_table_no_huset_x.mp3'})
        audio = card.select('table.inflection-table audio.lexin-form-audio[src]')
        self.assertEqual([tag['src'] for tag in audio], ['lexin_table_no_huset_x.mp3'], BREAKS + 'table <audio src>')


class ImageAndConfigContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        data['language'].update(source='no', translation_target='en')
        data['sources'] = {'images': {'enabled': True, 'count': 1, 'priority': ['commons']}}
        data['output']['directory'] = str(self.directory / 'Output')
        data['audio']['directory'] = str(self.directory / 'Audio')
        data['dictionary_cache'] = {'enabled': True, 'path': str(self.directory / 'cache.sqlite3')}
        data['media'] = {'anki_directory': ''}
        self.config = Config(self.directory / 'config.toml', data)

    def tearDown(self):
        self.temp.cleanup()

    def test_image_search_returns_local_files_with_credits(self):
        buffer = BytesIO()
        Image.new('RGB', (120, 90), 'red').save(buffer, format='PNG')
        uri = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        with patch('app.image_sources.candidates', return_value=[(uri, 'Car.jpg | Ann | CC BY 4.0')]), \
                api.Lookup(self.config) as lookup:
            result = lookup.images('car')
        self.assertEqual(result.status, 'ok', BREAKS + f'image search: {result.message}')
        self.assertEqual(len(result.paths), 1, BREAKS + 'image file found from .image-result img[src]')
        self.assertTrue(result.paths[0].is_file(), BREAKS + 'image saved in output/media')
        self.assertEqual(result.credits, ('Car.jpg | Ann | CC BY 4.0',), BREAKS + 'credit from .image-credit')

    def test_config_keys_used_by_flash_cards(self):
        config = load_config(ROOT / 'config.toml', check_files=False)
        self.assertIsInstance(config.section('audio')['directory'], str, BREAKS + '[audio] directory')
        self.assertIn('copy_to', config.section('audio'), BREAKS + '[audio] copy_to')
        self.assertIsInstance(config.section('runtime')['word_delay_seconds'], (int, float), BREAKS + '[runtime] word_delay_seconds')
        self.assertIsInstance(config.section('language')['source'], str, BREAKS + '[language] source')
        # flash-cards sets these in memory: images on/off with count and priority, and no Anki media copying.
        data = dict(config.data)
        data['sources'] = {**config.data['sources'], 'images': {'enabled': True, 'count': 1, 'priority': ['bing', 'commons', 'google']}}
        data['media'] = {'anki_directory': ''}
        self.assertIn('images', api.enabled_sources(Config(config.path, data)), BREAKS + 'enabling [sources.images]')


if __name__ == '__main__':
    unittest.main()
