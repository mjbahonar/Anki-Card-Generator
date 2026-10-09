"""V4 integration tests without external dictionary availability."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch
import zipfile
import io
from contextlib import redirect_stdout
from bs4 import BeautifulSoup

import pandas as pd

from anki_exporter import FIELDS, answer_template, display_sources, generate_anki_package, info_html
from app_config import Config, ConfigError, load_config
from main import export_outputs, read_words, run
from sources import SOURCE_SPECS, SourceContext, dictionary_content, select_audio
from sources import clean_html, block

ROOT = Path(__file__).resolve().parent


class V4Tests(unittest.TestCase):
    def test_ordbokene_exact_homographs_emphasis_and_inflection(self):
        from ordbokene_scraper import exact_article, render_article
        markup = '''<div class="article-title"><h3>bok<span class="hgno"><span class="sr-only">1</span>I</span></h3>
          <div class="subheader">noun <em>feminine</em></div></div><button>Inflection</button>
          <table class="infl-table"><caption>Inflection</caption><thead><tr><th colspan="2">singular</th></tr></thead>
          <tbody><tr><td rowspan="2"><strong>boka</strong></td><td>bøker</td></tr></tbody></table>
          <section class="expressions"><strong>fullt hus</strong><em>example</em></section><div role="toolbar">Copy link</div>'''
        self.assertTrue(exact_article(markup, 'bok'))
        self.assertFalse(exact_article(markup, 'bokhandel'))
        result = clean_html(render_article(markup))
        for expected in ['<strong>boka</strong>', '<strong>fullt hus</strong>', '<em>example</em>', 'colspan="2"', 'rowspan="2"', 'inflection-wrapper']:
            self.assertIn(expected, result)
        self.assertNotIn('Copy link', result)
        self.assertNotIn('<button', result)

    def test_image_fallback_persists_media_and_credits(self):
        from io import BytesIO
        from PIL import Image
        from image_sources import download_images
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        buffer = BytesIO()
        Image.new('RGB', (100, 100), 'red').save(buffer, format='PNG')
        context.fetch = Mock(return_value=Mock(content=buffer.getvalue()))
        with patch('image_sources.candidates', side_effect=[ValueError('Google blocked'),
                   [('https://example.com/image.png', 'Artist | CC BY 4.0')]]):
            result = download_images('cat', context)
        self.assertIn('CC BY 4.0', result)
        self.assertIn('image_commons_no_cat', result)
        self.assertEqual(len(context.media), 1)
        self.assertTrue(next(iter(context.media)).is_file())
        self.assertEqual(context.errors[0]['source'], 'images_google')

    def test_images_skip_invalid_response_and_fill_requested_count(self):
        from io import BytesIO
        from PIL import Image
        from image_sources import download_images
        self.config.section('sources')['images'].update(count=1, priority=['commons'])
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        buffer = BytesIO()
        Image.new('RGB', (90, 90), 'blue').save(buffer, format='PNG')
        context.fetch = Mock(side_effect=[Mock(content=b'not an image'), Mock(content=buffer.getvalue())])
        with patch('image_sources.candidates', return_value=[('https://example.com/bad',''),
             ('https://example.com/good','credit'), ('https://example.com/extra','')]):
            result = download_images('book', context)
        self.assertEqual(result.count('<img'), 1)
        self.assertEqual(context.fetch.call_count, 2)

    def test_oxford_all_parts_of_speech_without_compounds_or_duplicate_fetches(self):
        self.config.section('language')['source'] = 'en'
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        def response(pos, index, links):
            return Mock(url=f'https://www.oxfordlearnersdictionaries.com/definition/english/round_{index}', text=f'''
            <div class="entry"><h1 class="headword">round</h1><span class="pos">{pos}</span>
            <li class="sense"><span class="sensetop"><span class="def">{pos} definition</span></span></li></div>{links}''')
        links = ''.join(f'<a href="/definition/english/round_{i}">round</a>' for i in range(1, 6))
        links += '<a href="/definition/english/round-up">compound</a><a href="https://other.example/definition/english/round_6">other</a>'
        context.fetch = Mock(side_effect=[response(pos, i, links) for i, pos in enumerate(
            ['adjective', 'adverb', 'preposition', 'noun', 'verb'], 1)])
        result = dictionary_content('oxford', 'round', 1, context)
        for pos in ['adjective', 'adverb', 'preposition', 'noun', 'verb']:
            self.assertIn(pos + ' definition', result)
        self.assertEqual(context.fetch.call_count, 5)
        self.assertNotIn('compound', result)

    def test_oxford_schema_rejects_old_model_id(self):
        text = (ROOT / 'config.toml').read_text(encoding='utf-8')
        path = self.directory / 'old_model.toml'
        path.write_text(text.replace('model_id = 1559328451', 'model_id = 1559328440'), encoding='utf-8')
        with self.assertRaisesRegex(ConfigError, 'new model_id'):
            load_config(path)

    def test_oxford_exact_entry_examples_and_no_audio_request(self):
        self.config.section('language')['source'] = 'en'
        self.config.section('sources')['oxford']['examples_per_definition'] = 1
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        context.fetch = Mock(return_value=Mock(text='''<div class="entry"><h1 class="headword">book</h1>
          <span class="pos">noun</span><ol><li class="sense"><span class="def">printed &amp; bound pages</span>
          <ul class="examples"><li><span class="x">first example</span></li><li><span class="x">second example</span></li></ul>
          <div class="unbox">advertisement</div><div data-src-mp3="audio.mp3">play audio</div></li></ol>
          <div class="idioms"><li class="sense"><span class="def">unrelated idiom</span></li></div></div>'''))
        result = dictionary_content('oxford', 'book', 1, context)
        self.assertIn('printed &amp; bound pages', result)
        self.assertIn('first example', result)
        for unwanted in ['second example', 'advertisement', 'audio.mp3', 'play audio', 'unrelated idiom']:
            self.assertNotIn(unwanted, result)
        context.fetch.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'exact Oxford'):
            dictionary_content('oxford', 'books', 1, context)

    def test_browser_launch_uses_configured_timeout(self):
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        with patch('playwright.sync_api.sync_playwright') as start:
            engine = start.return_value.start.return_value
            with context.page():
                pass
            self.assertEqual(engine.chromium.launch.call_args.kwargs['timeout'], context.timeout * 1000)

    def test_lexin_search_errors_are_reported_without_console_traceback(self):
        from lexin_scraper import scrape_and_process_lexin
        page = Mock()
        page.goto.side_effect = RuntimeError('search failed\nlong traceback')
        callback, output = Mock(), io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(scrape_and_process_lexin('bok', 1, page, verbose=False, on_error=callback), ('', ''))
        callback.assert_called_once()
        self.assertEqual(callback.call_args.args[0], 'lexin')
        self.assertEqual(output.getvalue(), '')

    def test_config_rejects_nonfinite_numbers_and_oversized_ids(self):
        text = (ROOT / 'config.toml').read_text(encoding='utf-8')
        path = self.directory / 'invalid.toml'
        for old, new, message in [('timeout_seconds = 20', 'timeout_seconds = nan', 'timeout_seconds'),
                                  ('word_delay_seconds = 0.5', 'word_delay_seconds = inf', 'word_delay_seconds'),
                                  ('deck_id = 2059400451', 'deck_id = 9223372036854775808', 'SQLite')]:
            with self.subTest(message=message):
                path.write_text(text.replace(old, new), encoding='utf-8')
                with self.assertRaisesRegex(ConfigError, message):
                    load_config(path)

    def test_runtime_failure_saves_partial_words(self):
        self.config.section('output')['formats'] = ['json']
        with patch('main.dictionary_content', return_value='<p>definition</p>'), \
             patch('main.select_audio', return_value=''), patch('main.time.sleep', side_effect=RuntimeError('runtime failure')), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.config), 1)
        saved = next(self.directory.glob('*_partial.json'))
        self.assertEqual(len(json.loads(saved.read_text(encoding='utf-8'))['words']), 1)

    def test_html_preserves_example_direction_and_rejects_empty_content(self):
        self.assertIn('dir="ltr"', clean_html('<div dir="ltr" onclick="bad()">example</div>'))
        self.assertNotIn('onclick', clean_html('<div onclick="bad()">example</div>'))
        with self.assertRaises(ValueError):
            block('fastdic', '<script>not a definition</script>')

    def test_browser_setup_failure_closes_page_and_session_cleanup_survives(self):
        context = SourceContext(self.config)
        context.browser = Mock()
        page = context.browser.new_page.return_value
        page.set_default_timeout.side_effect = RuntimeError('setup')
        with self.assertRaises(RuntimeError), context.page():
            self.fail('Page should not be yielded')
        page.close.assert_called_once()
        context.playwright = Mock()
        context.playwright.stop.side_effect = RuntimeError('stop')
        context.session.close = Mock()
        with self.assertRaises(RuntimeError):
            context.close()
        context.session.close.assert_called_once()

    def test_unexpected_audio_error_keeps_words_and_prints_final_report(self):
        self.config.section('output')['formats'] = ['json']
        output = io.StringIO()
        with patch('main.dictionary_content', return_value='<p>definition</p>'), \
             patch('main.select_audio', side_effect=RuntimeError('unexpected audio failure')), redirect_stdout(output):
            self.assertEqual(run(self.config), 0)
        text = output.getvalue()
        self.assertIn('FINAL REPORT', text)
        self.assertIn('Words saved: 2/2', text)
        self.assertIn('COMPLETED WITH WARNINGS', text)
        saved = next(path for path in self.directory.glob('*.json') if not path.name.endswith('_errors.json'))
        self.assertEqual(len(json.loads(saved.read_text(encoding='utf-8'))['words']), 2)

    def test_report_write_failure_does_not_discard_export(self):
        self.config.section('output')['formats'] = ['csv']
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name.endswith('_errors.json'):
                raise PermissionError('report locked')
            return original(path, *args, **kwargs)
        with patch('main.dictionary_content', side_effect=RuntimeError('offline')), \
             patch('main.select_audio', return_value=''), patch.object(Path, 'write_text', write), redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.config), 1)
        self.assertTrue(list(self.directory.glob('*.csv')))

    def test_unwritable_output_returns_export_failures(self):
        blocked = self.directory / 'blocked'
        blocked.write_text('file', encoding='utf-8')
        self.config.section('output')['directory'] = str(blocked)
        self.config.section('output')['formats'] = ['csv', 'json']
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        paths, failures = export_outputs([{'Words': 'bok'}], self.config, 'test', context)
        self.assertEqual(paths, [])
        self.assertEqual(len(failures), 2)

    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.directory = Path(self.temp.name)
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        data['input']['file'] = str(self.directory / 'input.xlsx')
        data['output']['directory'] = str(self.directory)
        data['audio']['directory'] = str(self.directory / 'Audio')
        data['style']['file'] = str(ROOT / 'Styles/cards.css')
        data['runtime']['keep_awake'] = False
        data['runtime']['word_delay_seconds'] = 0
        data['runtime']['retry_delay_seconds'] = 0
        self.config = Config(ROOT / 'config.toml', data)
        pd.DataFrame(['bok', 'hus']).to_excel(data['input']['file'], header=False, index=False)

    def tearDown(self):
        self.temp.cleanup()

    def package_contents(self, path):
        with zipfile.ZipFile(path) as archive:
            media = json.loads(archive.read('media'))
            database = self.directory / (path.stem + '.anki2')
            database.write_bytes(archive.read('collection.anki2'))
        connection = sqlite3.connect(database)
        try:
            models = json.loads(connection.execute('select models from col').fetchone()[0])
            notes = connection.execute('select guid, flds from notes order by id').fetchall()
        finally:
            connection.close()
        return next(iter(models.values())), notes, media

    def test_excel_blank_duplicate_unicode_and_limit(self):
        pd.DataFrame(['bok', None, ' BOK ', 'blå', 'bla\u030a', 'hus']).to_excel(self.config.section('input')['file'], header=False, index=False)
        self.assertEqual(read_words(self.config), ['bok', 'blå', 'hus'])
        self.config.section('input')['max_words'] = 2
        self.assertEqual(read_words(self.config), ['bok', 'blå'])

    def test_named_sheet_and_header_column(self):
        pd.DataFrame({'Other': [1], 'Word': ['house']}).to_excel(self.config.section('input')['file'], sheet_name='Vocabulary', index=False)
        self.config.section('input').update(header=True, word_column='Word', sheet='Vocabulary')
        self.assertEqual(read_words(self.config), ['house'])
        self.config.section('input')['word_column'] = 'Missing'
        with self.assertRaises(ConfigError):
            read_words(self.config)

    def test_config_rejects_typo_and_invalid_output(self):
        text = (ROOT / 'config.toml').read_text(encoding='utf-8')
        path = self.directory / 'bad.toml'
        path.write_text(text.replace('translation_target', 'translation_targte'), encoding='utf-8')
        with self.assertRaisesRegex(ConfigError, 'translation_target'):
            load_config(path)
        path.write_text(text.replace('["xlsx", "csv", "apkg", "html", "json"]', '["pdf"]'), encoding='utf-8')
        with self.assertRaisesRegex(ConfigError, 'formats'):
            load_config(path)

    def test_source_order_and_language_filter(self):
        data = self.config.data
        data['sources'] = {'dict_com': {'enabled': True}, 'lexin': {'enabled': True}, 'fastdic': {'enabled': True}}
        self.assertEqual(display_sources(self.config), ['dict_com', 'lexin'])
        data['language']['source'] = 'en'
        self.assertEqual(display_sources(self.config), ['dict_com', 'fastdic'])
        self.assertTrue(answer_template(self.config).endswith('{{#Info}}{{Info}}{{/Info}}'))
        self.assertIn('About this deck', info_html(self.config))
        self.assertNotIn('درباره', info_html(self.config))

    def test_schema_and_guid_stable_after_source_order_and_audio_change(self):
        row = {'Words': 'bok', 'FrontField': 'bok', 'lexin': '<p>book</p>', 'Info': info_html(self.config)}
        first = self.directory / 'first.apkg'
        generate_anki_package([row], first, self.config, set())
        model1, notes1, _ = self.package_contents(first)
        self.config.data['sources'] = {'dict_com': {'enabled': True}, 'lexin': {'enabled': False}}
        row['FrontField'] = 'bok [sound:changed.mp3]'
        second = self.directory / 'second.apkg'
        generate_anki_package([row], second, self.config, set())
        model2, notes2, _ = self.package_contents(second)
        self.assertEqual([f['name'] for f in model1['flds']], FIELDS)
        self.assertEqual(model1['flds'], model2['flds'])
        self.assertEqual(notes1[0][0], notes2[0][0])
        self.assertNotIn('{{lexin}}', model2['tmpls'][0]['afmt'])

    def test_only_referenced_media_is_bundled(self):
        used, unused = self.directory / 'used.mp3', self.directory / 'unused.mp3'
        used.write_bytes(b'ID3' + b'x' * 200)
        unused.write_bytes(b'ID3' + b'x' * 200)
        path = self.directory / 'media.apkg'
        generate_anki_package([{'Words': 'bok', 'FrontField': 'bok [sound:used.mp3]'}], path, self.config, {used, unused})
        _, _, media = self.package_contents(path)
        self.assertEqual(set(media.values()), {'used.mp3'})

    def test_all_output_formats_and_info_last(self):
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        rows = [{'Words': 'bok', 'FrontField': 'bok', 'Sound': '', 'lexin': '<p>book</p>', 'Info': info_html(self.config)}]
        paths, failures = export_outputs(rows, self.config, 'test', context)
        self.assertFalse(failures)
        self.assertEqual({p.suffix for p in paths}, {'.csv', '.xlsx', '.json', '.html', '.apkg'})
        self.assertEqual(pd.read_csv(self.directory / 'test.csv').columns[-1], 'Info')
        preview = (self.directory / 'test.html').read_text(encoding='utf-8')
        self.assertLess(preview.index('<p>book</p>'), preview.index('About this deck'))

    def test_only_requested_output_is_written(self):
        self.config.section('output')['formats'] = ['csv']
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        paths, failures = export_outputs([{'Words': 'bok', 'FrontField': 'bok', 'Sound': ''}], self.config, 'only', context)
        self.assertFalse(failures)
        self.assertEqual([p.suffix for p in paths], ['.csv'])
        self.assertFalse((self.directory / 'only.apkg').exists())

    def test_failed_source_does_not_stop_other_words(self):
        self.config.section('output')['formats'] = ['json']
        self.config.section('audio')['enabled'] = False
        def adapter(name, word, number, ctx):
            if name == 'google_translate':
                raise RuntimeError('Rate limited')
            return '<p>' + word + '</p>'
        with patch('main.dictionary_content', side_effect=adapter):
            self.assertEqual(run(self.config), 0)
        report = json.loads(next(self.directory.glob('words_*.json')).read_text(encoding='utf-8'))
        self.assertEqual(len(report['words']), 2)
        self.assertEqual(len(report['errors']), 2)
        self.assertTrue(all(r['dict_com'] for r in report['words']))

    def test_ctrl_c_preserves_partial_word(self):
        self.config.section('output')['formats'] = ['json']
        with patch('main.dictionary_content', side_effect=KeyboardInterrupt):
            self.assertEqual(run(self.config), 2)
        report = json.loads(next(self.directory.glob('*_partial.json')).read_text(encoding='utf-8'))
        self.assertEqual(report['words'][0]['Words'], 'bok')

    def test_audio_disabled_never_calls_providers(self):
        self.config.section('audio')['enabled'] = False
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        with patch.object(context, 'lexin') as lexin:
            self.assertEqual(select_audio('bok', 1, context), '')
            lexin.assert_not_called()

    def test_audio_fallback_no_duplicate_lexin_attempt_and_language_cache(self):
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        context.lexin_audio_attempted.add('bok')
        context.lexin_results['bok'] = ('entry', '')
        with patch.object(context, 'lexin') as lexin, patch('gtts.gTTS') as tts:
            tts.return_value.write_to_fp.side_effect = lambda buffer: buffer.write(b'ID3' + b'x' * 200)
            sound = select_audio('bok', 1, context)
            self.assertIn('google_tts_no', sound)
            lexin.assert_not_called()
        english = copy.deepcopy(self.config.data)
        english['language']['source'] = 'en'
        context2 = SourceContext(Config(self.config.path, english))
        self.addCleanup(context2.close)
        with patch('gtts.gTTS') as tts, patch.object(context2, 'fetch', side_effect=RuntimeError('No Fastdic')):
            tts.return_value.write_to_fp.side_effect = lambda buffer: buffer.write(b'ID3' + b'y' * 200)
            self.assertIn('google_tts_en', select_audio('bok', 1, context2))
            tts.assert_called_once()

    def test_translation_timeout_retry_and_html_escape(self):
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        response = Mock(text='<div class="result-container">&lt;کتاب&gt;</div>')
        context.session.get = Mock(side_effect=[TimeoutError('timeout'), response])
        result = dictionary_content('google_translate', 'bok', 1, context)
        self.assertIn('&lt;کتاب&gt;', result)
        self.assertEqual(context.session.get.call_count, 2)
        self.assertEqual(context.session.get.call_args.kwargs['timeout'], context.timeout)

    def test_imports_do_not_launch_browser_or_read_excel(self):
        import importlib
        import main
        with patch('pandas.read_excel') as reader, patch('sources.SourceContext') as context:
            importlib.reload(main)
            reader.assert_not_called()
            context.assert_not_called()

    def test_dict_com_uses_valid_bidirectional_route_for_english(self):
        self.config.section('language')['source'] = 'en'
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        context.browse = Mock(return_value=BeautifulSoup('''<div id="entry-header"><span class="lex_ful_entr">house*</span></div>
            <div id="entry-body"><section class="main-body"><mtab>Bøyning</mtab><sense>hus</sense></section>
            <section id="entry-fulltext">unrelated</section><p>Annonse</p></div>''', 'html.parser'))
        result = dictionary_content('dict_com', 'house', 1, context)
        self.assertIn('hus', result)
        self.assertNotIn('unrelated', result)
        self.assertNotIn('Annonse', result)
        self.assertNotIn('Bøyning', result)
        self.assertIn('/engelsk-norsk/house', context.browse.call_args.args[0])

    def test_english_adapters_exclude_site_ui_and_limit_examples(self):
        self.config.section('sources')['fastdic']['examples_per_definition'] = 1
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        markup = '''<section class="results__container"><div class="meaning"><div class="pos">noun</div>
            <p>خانه</p><div class="vt-word-banner__title">Advert</div>
            <div class="result__sentences"><div class="sentence"><p>example one</p></div></div>
            <div class="result__sentences"><div class="sentence"><p>example two</p></div></div></div></section>'''
        context.fetch = Mock(return_value=Mock(text=markup))
        result = dictionary_content('fastdic', 'house', 1, context)
        self.assertIn('خانه', result)
        self.assertIn('example one', result)
        self.assertNotIn('example two', result)
        self.assertNotIn('Advert', result)
        context.browse = Mock(return_value=BeautifulSoup('''<div class="entry-body"><div class="def-block">
            <div class="def">a building</div><div class="examp">an example</div></div>
            <div class="smartt">SMART Vocabulary: unrelated links</div></div>''', 'html.parser'))
        result = dictionary_content('cambridge', 'house', 1, context)
        self.assertIn('a building', result)
        self.assertIn('an example', result)
        self.assertNotIn('SMART Vocabulary', result)


if __name__ == '__main__':
    unittest.main()
