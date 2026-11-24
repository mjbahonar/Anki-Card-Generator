"""Library interface used by other projects (app.api) and packaging metadata."""
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import app
from app.api import API_VERSION, ConfigError, Lookup, enabled_sources, load_settings
from app.app_config import Config, load_config
from app.sources import SOURCE_SPECS
import main

ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        data['language'].update(source='no', translation_target='fa')
        data['sources'] = {name: {'enabled': name in ('lexin', 'google_translate', 'dict_com', 'images', 'oxford')}
                           for name in SOURCE_SPECS}
        data['output']['directory'] = str(self.directory / 'Output')
        data['audio'].update(directory=str(self.directory / 'Audio'), enabled=True)
        data['dictionary_cache'] = {'enabled': True, 'path': str(self.directory / 'cache.sqlite3')}
        data.setdefault('cards', {}).setdefault('normal', {})['audio'] = True
        self.config = Config(self.directory / 'config.toml', data)

    def tearDown(self):
        self.temp.cleanup()

    def test_load_settings_does_not_require_excel_or_style_files(self):
        path = self.directory / 'config.toml'
        shutil.copy(ROOT / 'config.toml', path)  # Relative input/style paths do not exist here.
        config = load_settings(path)
        self.assertEqual(config.path, path.resolve())
        with self.assertRaises(ConfigError):
            load_config(path)
        with self.assertRaises(ConfigError):
            load_settings(path, check_files=True)

    def test_enabled_sources_follow_config_order_and_language(self):
        self.assertEqual(enabled_sources(self.config), ['lexin', 'google_translate', 'dict_com', 'images'])

    def test_word_reports_each_source_audio_and_images(self):
        images = self.directory / 'Output' / 'media'
        images.mkdir(parents=True)
        (images / 'hus_0.png').write_bytes(b'png')

        def content(name, word, number, ctx):
            if name == 'lexin':
                return '<div>house</div>'
            if name == 'dict_com':
                raise ValueError('markup changed')
            if name == 'images':
                return '<div class="image-result"><img src="hus_0.png" alt="hus"></div>'
            return ''

        with patch('app.api.dictionary_content', side_effect=content), \
                patch('app.api.select_audio', return_value='[sound:hus.mp3]'):
            with Lookup(self.config) as lookup:
                result = lookup.word(' hus ')
        self.assertEqual(result.word, 'hus')
        self.assertEqual((result.language, result.translation_target), ('no', 'fa'))
        self.assertEqual([s.status for s in result.sources], ['ok', 'empty', 'fail', 'ok'])
        self.assertEqual([s.name for s in result.found()], ['lexin', 'images'])
        self.assertEqual(result.source('lexin').title, SOURCE_SPECS['lexin'].title)
        self.assertIn('markup changed', result.source('dict_com').message)
        self.assertEqual(result.audio, self.directory / 'Audio' / 'hus.mp3')
        self.assertEqual(result.images, (images / 'hus_0.png',))
        self.assertEqual({issue['source'] for issue in result.issues}, {'google_translate', 'dict_com'})

    def test_issues_are_per_word_and_sources_can_be_narrowed(self):
        with patch('app.api.dictionary_content', side_effect=ValueError('down')), \
                patch('app.api.select_audio', return_value=''):
            with Lookup(self.config) as lookup:
                first = lookup.word('hus', sources=['lexin'], audio=False)
                second = lookup.word('bil', sources=['lexin'], audio=False)
        self.assertEqual([s.name for s in second.sources], ['lexin'])
        self.assertEqual(len(first.issues), 1)
        self.assertEqual([issue['word'] for issue in second.issues], ['bil'])
        self.assertIsNone(second.audio)

    def test_rejects_blank_word_and_disabled_sources(self):
        with Lookup(self.config) as lookup:
            with self.assertRaises(ValueError):
                lookup.word('  ')
            with self.assertRaises(ValueError):
                lookup.word('hus', sources=['oxford'])  # Enabled, but English-only.

    def test_images_search_any_term_with_credits(self):
        images = self.directory / 'Output' / 'media'
        images.mkdir(parents=True)
        (images / 'car_0.png').write_bytes(b'png')
        markup = ('<div class="gt-container"><div class="image-result"><img src="car_0.png" alt="car">'
                  '<div class="image-credit">Car.jpg | Ann | CC BY 4.0</div></div>'
                  '<div class="image-result"><img src="missing.png"></div></div>')
        calls = []

        def content(name, word, number, ctx):
            calls.append((name, word))
            return markup

        with patch('app.api.dictionary_content', side_effect=content), Lookup(self.config) as lookup:
            result = lookup.images(' car ')
            self.assertEqual(calls, [('images', 'car')])
            self.assertEqual((result.term, result.status), ('car', 'ok'))
            self.assertEqual(result.paths, (images / 'car_0.png',))
            self.assertEqual(result.credits, ('Car.jpg | Ann | CC BY 4.0',))
            with self.assertRaises(ValueError):
                lookup.images('')
        self.config.section('sources')['images'] = {'enabled': False}
        with Lookup(self.config) as lookup, self.assertRaises(ValueError):
            lookup.images('car')

    def test_bing_candidates_use_full_images_and_credit_the_page(self):
        from unittest.mock import Mock
        from app.image_sources import candidates
        page = ('<a class="iusc" m="{&quot;murl&quot;:&quot;https://cars.example/car.jpg&quot;,'
                '&quot;purl&quot;:&quot;https://www.cars.example/new&quot;,&quot;t&quot;:&quot;Car&quot;}"></a>'
                '<a class="iusc" m="not json"></a>'
                '<a class="iusc" m="{&quot;murl&quot;:&quot;data:x&quot;}"></a>')
        ctx = Mock(fetch=Mock(return_value=Mock(text=page)))
        self.assertEqual(candidates('bing', 'car', ctx, 1),
                         [('https://cars.example/car.jpg', 'Bing Images | cars.example | https://www.cars.example/new')])
        self.assertIn('q=car%20clipart', ctx.fetch.call_args[0][0])
        from app.dictionary_cache import cache_key
        self.config.section('sources')['images'] = {'enabled': True, 'count': 1, 'priority': ['bing']}
        self.assertIn('"bing_query": "clipart"', cache_key('images', 'car', self.config))
        self.config.section('sources')['images'] = {'enabled': True, 'count': 1, 'priority': ['commons']}
        self.assertNotIn('bing_query', cache_key('images', 'car', self.config))  # Commons-only caches unchanged.
        self.assertIn('adlt=strict', ctx.fetch.call_args[0][0])
        ctx.fetch = Mock(side_effect=[Mock(text='<p>light page</p>'), Mock(text=page)])
        self.assertEqual(len(candidates('bing', 'car', ctx, 1)), 1)  # Retried once.
        ctx.fetch = Mock(return_value=Mock(text='<p>Please solve this captcha</p>'))
        with self.assertRaisesRegex(ValueError, 'blocked'):
            candidates('bing', 'car', ctx, 1)
        self.assertEqual(ctx.fetch.call_count, 2)

    def test_separators_shown_by_site_css_are_written_out(self):
        from bs4 import BeautifulSoup
        from app.sources import restore_separators
        forms = ('<td><span><span class="comma"><!-- --><span>husa</span></span><!-- -->'
                 '<span class="comma"><span>husene</span></span></span></td>'
                 '<td><span class="comma"><span>huset</span></span></td>')
        fixed = restore_separators('bokmalsordboka', forms)
        self.assertEqual([td.get_text() for td in BeautifulSoup(fixed, 'html.parser').select('td')], ['husa, husene', 'huset'])
        self.assertEqual(restore_separators('bokmalsordboka', fixed), fixed)  # Cached results are repaired once.
        entry = '<span class="lex_ful_entr l1">hus</span><span class="lex_ful_morf"><span>n</span></span><div>building</div>'
        fixed = restore_separators('dict_com', entry)
        self.assertTrue(BeautifulSoup(fixed, 'html.parser').get_text().startswith('hus n '))
        self.assertEqual(restore_separators('dict_com', fixed), fixed)
        self.assertEqual(restore_separators('oxford', forms), forms)  # Other sources untouched.

    def test_sanitize_html_keeps_formatting_and_removes_unsafe_markup(self):
        from app.api import sanitize_html
        html = sanitize_html('<table><tr><td style="color: red">et hus</td></tr></table><br>'
                             '<a href="https://ex.com">link</a><a href="javascript:x()">bad</a>'
                             '<script>alert(1)</script><img src="x.png" onerror="y()"><iframe></iframe>')
        self.assertIn('<td style="color: red">et hus</td>', html)
        self.assertIn('<a href="https://ex.com">link</a>', html)
        self.assertIn('bad', html)
        for unsafe in ('javascript:', '<script', 'onerror', '<iframe', 'alert'):
            self.assertNotIn(unsafe, html)

    def test_excel_formatted_cells_keep_excel_formatting(self):
        from openpyxl import Workbook
        from openpyxl.cell.rich_text import CellRichText, TextBlock
        from openpyxl.cell.text import InlineFont
        from openpyxl.styles import Font
        from app.api import excel_formatted_cells
        book = Workbook()
        sheet = book.active
        sheet.append(['Word', 'Meaning'])
        sheet.append(['hus', CellRichText(['a ', TextBlock(InlineFont(b=True, color='FFC00000'), 'house'), '\nhuset'])])
        sheet.append(['bil', 'car'])
        sheet.append(['gå', 'to go'])
        sheet['B4'].font = Font(italic=True)
        path = self.directory / 'formatted.xlsx'
        book.save(path)
        cells = excel_formatted_cells(path, 0, 1, {2: 'a house\nhuset', 3: 'car', 4: 'to go'})
        self.assertEqual(set(cells), {2, 4})                     # Unformatted 'car' stays plain text.
        self.assertIn('font-weight: 700', cells[2])
        self.assertIn('color: #C00000', cells[2])
        self.assertIn('>house</span>', cells[2])
        self.assertIn('<br>huset', cells[2])
        self.assertIn('font-style: italic', cells[4])
        self.assertEqual(excel_formatted_cells(path, 0, 1, {2: 'different text'}), {})  # Mismatch: no formatting.

    def test_wikimedia_requests_identify_the_client(self):
        from app.image_sources import WIKIMEDIA_HEADERS, wikimedia_headers
        self.assertEqual(wikimedia_headers('https://upload.wikimedia.org/a.jpg'), WIKIMEDIA_HEADERS)
        self.assertIsNone(wikimedia_headers('https://example.com/wikimedia.org.jpg'))
        self.assertIsNone(wikimedia_headers('data:image/png;base64,xx'))
        self.assertNotIn('Mozilla', WIKIMEDIA_HEADERS['User-Agent'])

    def test_versions_agree(self):
        self.assertEqual(API_VERSION, 1)
        self.assertEqual(main.VERSION, app.__version__)
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual(project['tool']['setuptools']['dynamic']['version'], {'attr': 'app.__version__'})
        changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        latest = next(line for line in changelog.splitlines() if line.startswith('## v'))
        self.assertTrue(latest.startswith(f'## v{app.__version__} '), latest)
        requirements = [line.strip() for line in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
                        if line.strip() and not line.startswith('#')]
        self.assertEqual(project['project']['dependencies'], requirements)


if __name__ == '__main__':
    unittest.main()
