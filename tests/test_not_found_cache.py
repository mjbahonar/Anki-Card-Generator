"""Definitely-absent words are remembered; failures are not. Plus the cache browser queries."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import tomllib
import unittest
from unittest.mock import Mock, patch

from app.app_config import Config
from app.dictionary_cache import DictionaryCache
from app.sources import SourceContext

ROOT = Path(__file__).resolve().parents[1]
MP3 = b'ID3' + b'x' * 200


class NotFoundCacheTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.root = Path(self.temp.name)
        self.data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        self.data['media'] = {'anki_directory': ''}
        self.data['dictionary_cache'] = {'enabled': True, 'path': str(self.root / 'cache' / 'dict.sqlite3')}
        self.data['audio']['directory'] = str(self.root / 'Audio')
        self.data['output']['directory'] = str(self.root / 'Output')
        self.contexts = []

    def tearDown(self):
        for ctx in self.contexts:
            ctx.close()
        self.temp.cleanup()

    def context(self):
        ctx = SourceContext(Config(ROOT / 'config.toml', self.data))
        self.contexts.append(ctx)
        return ctx

    def absent(self, ctx):
        def load():
            ctx.definitely_absent = True
            return ''
        return load

    def test_definitely_absent_word_is_saved_and_skipped_later(self):
        ctx = self.context()
        self.assertEqual(ctx.cache_result('oxford', 'xqzvbrt', self.absent(ctx)), '')
        later = self.context()
        loader = Mock(return_value='<p>should not run</p>')
        self.assertEqual(later.cache_result('oxford', 'xqzvbrt', loader), '')
        loader.assert_not_called()
        self.assertTrue(later.last_cache_hit)
        self.assertTrue(later.last_not_found)
        rows = later.dictionary_cache.search('xqz', status='not_found')['rows']
        self.assertEqual([(r['word'], r['source'], r['not_found']) for r in rows], [('xqzvbrt', 'oxford', True)])

    def test_failures_timeouts_and_plain_empty_results_are_not_saved(self):
        for mode in ('error-issue', 'timeout', 'plain-empty', 'refresh'):
            with self.subTest(mode=mode):
                ctx = self.context()
                def load():
                    if mode != 'plain-empty':
                        ctx.definitely_absent = True
                    if mode == 'error-issue':
                        ctx.issue('word', 'oxford', 'page did not load')
                    if mode == 'timeout':
                        ctx.source_deadline = 0
                    return ''
                if mode == 'timeout':
                    with self.assertRaises(TimeoutError):
                        ctx.cache_result('oxford', mode, load)
                else:
                    ctx.cache_result('oxford', mode, load)
                if mode == 'refresh':
                    continue
                loader = Mock(return_value='complete')
                self.assertEqual(self.context().cache_result('oxford', mode, loader), 'complete')
                loader.assert_called_once()

    def test_refresh_setting_rechecks_a_saved_absent_word(self):
        ctx = self.context()
        ctx.cache_result('oxford', 'gone', self.absent(ctx))
        self.data['dictionary_cache']['refresh'] = True
        loader = Mock(return_value='<p>now it exists</p>')
        self.assertEqual(self.context().cache_result('oxford', 'gone', loader), '<p>now it exists</p>')
        loader.assert_called_once()

    def test_lexin_marks_absent_only_when_every_variant_says_so(self):
        for variant, answers, expected in [('bokmal', ['absent'], True), ('both', ['absent', 'absent'], True),
                                           ('both', ['absent', 'error'], False), ('bokmal', ['error'], False)]:
            with self.subTest(variant=variant, answers=answers):
                self.data['sources']['lexin']['variant'] = variant
                ctx = self.context()
                calls = iter(answers)

                def scrape(word, number, page, **kwargs):
                    if next(calls) == 'absent':
                        kwargs['on_not_found']()
                    else:
                        kwargs['on_error']('lexin', TimeoutError('slow'))
                    return '', ''
                ctx.page = Mock(return_value=Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False)))
                ctx.definitely_absent = False
                with patch('app.sources.scrape_and_process_lexin', side_effect=scrape):
                    self.assertEqual(ctx._lexin('xqz', 1), '')
                self.assertEqual(ctx.definitely_absent, expected)
        self.data['sources']['lexin']['variant'] = 'bokmal'


class CacheBrowserTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.root = Path(self.temp.name)
        self.cache = DictionaryCache(self.root / 'dict.sqlite3')
        sound = self.root / 'hus.mp3'
        sound.write_bytes(MP3)
        self.cache.put('k-hus', 'lexin', 'hus', '<p>house</p>', '[sound:hus.mp3]', [], [(sound, 'audio')])
        self.cache.put('k-hus-ox', 'oxford', 'hus', '<p>x</p>', '', [], [])
        self.cache.put('k-100%', 'lexin', '100%_sikker', '<p>sure</p>', '', [], [])
        self.cache.put('k-xq', 'lexin', 'xqzvbrt', '', '', [], [])

    def tearDown(self):
        self.temp.cleanup()

    def test_stats_count_words_results_not_found_and_media(self):
        stats = self.cache.stats()
        self.assertEqual((stats['results'], stats['not_found'], stats['words']), (4, 1, 3))
        lexin = next(s for s in stats['sources'] if s['source'] == 'lexin')
        self.assertEqual((lexin['results'], lexin['not_found']), (3, 1))
        self.assertEqual(stats['media'], [{'kind': 'audio', 'files': 1, 'bytes': len(MP3)}])
        self.assertGreater(stats['file_bytes'], 0)
        self.assertFalse(DictionaryCache(self.root / 'none.sqlite3').stats()['exists'])

    def test_search_filters_and_treats_wildcards_literally(self):
        self.assertEqual(self.cache.search('hus')['total'], 2)
        self.assertEqual(self.cache.search('hus', source='lexin')['rows'][0]['media_files'], 1)
        self.assertEqual([r['word'] for r in self.cache.search('%')['rows']], ['100%_sikker'])
        self.assertEqual(self.cache.search('_')['total'], 1)
        self.assertEqual([r['word'] for r in self.cache.search(status='not_found')['rows']], ['xqzvbrt'])
        self.assertEqual(self.cache.search(status='found')['total'], 3)
        self.assertEqual(len(self.cache.search(limit=2)['rows']), 2)

    def test_delete_matching_uses_the_same_filters_as_search(self):
        self.assertEqual(self.cache.delete_matching('hus', source='oxford'), 1)
        self.assertEqual(self.cache.delete_matching(status='not_found'), 1)
        self.assertEqual([r['word'] for r in self.cache.search()['rows']], ['100%_sikker', 'hus'])
        self.assertEqual(self.cache.delete_matching('%'), 1)  # Literal %, not "everything".
        self.assertEqual(self.cache.delete_matching(), 1)
        with closing(sqlite3.connect(self.cache.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)

    def test_entry_delete_forget_and_compact(self):
        entry = self.cache.entry('k-hus')
        self.assertEqual((entry['content'], entry['not_found'], entry['media'][0]['filename']), ('<p>house</p>', False, 'hus.mp3'))
        self.assertIsNone(self.cache.entry('missing'))
        self.assertEqual(self.cache.delete_keys(['k-hus', 'missing']), 1)
        with closing(sqlite3.connect(self.cache.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)  # Unused backup removed.
        self.assertTrue((self.root / 'hus.mp3').is_file())
        self.assertEqual(self.cache.delete_not_found('oxford'), 0)
        self.assertEqual(self.cache.delete_not_found(), 1)
        before, after = self.cache.compact()
        self.assertLessEqual(after, before)


class RefreshWordTests(unittest.TestCase):
    def test_refresh_word_deletes_then_looks_up_and_reports_saved_absence(self):
        import io
        from contextlib import redirect_stdout
        import main
        (ROOT / 'Output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'Output') as folder:
            text = (ROOT / 'config.toml').read_text(encoding='utf-8')
            path = Path(folder) / 'config.toml'
            path.write_text(text.replace('path = "Cache/dictionaries.sqlite3"', 'path = "dict.sqlite3"'), encoding='utf-8')
            store = DictionaryCache(Path(folder) / 'dict.sqlite3')
            store.put('old', 'lexin', 'xqz', '<p>stale</p>', '', [], [])

            class FakeLookup:
                def __init__(self, config):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def word(self, word, sources=None, audio=True):
                    store.put('new', 'lexin', word, '', '', [], [])  # What a real absent lookup saves.
                    return SimpleNamespace(sources=[SimpleNamespace(
                        name='lexin', status='empty', message='No exact entry/content received')])
            out = io.StringIO()
            with patch('app.api.Lookup', FakeLookup), patch('app.api.enabled_sources', return_value=['lexin']), \
                    redirect_stdout(out):
                code = main.main(['--config', str(path), '--refresh-word', 'xqz', '--source', 'lexin'])
            text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Removed 1 cached results for 'xqz' (lexin)", text)
        self.assertIn('saved as not found', text)


if __name__ == '__main__':
    unittest.main()
