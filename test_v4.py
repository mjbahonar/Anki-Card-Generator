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
from bs4 import BeautifulSoup

import pandas as pd

from anki_exporter import FIELDS, answer_template, display_sources, generate_anki_package, info_html
from app_config import Config, ConfigError, load_config
from main import export_outputs, read_words, run
from sources import SOURCE_SPECS, SourceContext, dictionary_content, select_audio

ROOT = Path(__file__).resolve().parent


class V4Tests(unittest.TestCase):
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
