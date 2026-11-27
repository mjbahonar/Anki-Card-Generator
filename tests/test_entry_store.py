"""Lexin entries stored once and compressed; the form index answers inflected forms offline."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch

from app.app_config import Config
from app.dictionary_cache import DictionaryCache, split_lexin
from app.lexin_scraper import clean_entry
from app.sources import SourceContext

ROOT = Path(__file__).resolve().parents[1]


def entry(word, meaning, forms=(), lang='nb'):
    cells = ''.join(f'<td><div><span>{f}</span></div></td>' for f in forms)
    return (f'<div class="gt-container lexin-container"><ul class="search-table"><li><dl>'
            f'<dd lang="{lang}"><span class="grunnform"><span class="highlight">{word}</span></span></dd>'
            f'<dd lang="en">{meaning}</dd></dl><div class="ordbank-table desktop"><table><tr>{cells}</tr></table></div>'
            f'</li></ul></div>')


NOTE = '<div class="lexin-form-note">gikk → <b>gå</b></div>'
GAA = entry('gå', 'go, walk', ['å gå', 'går', 'gikk', 'har gått'])
GAA2 = entry('gå', 'leave', ['å gå', 'går', 'gikk', 'har gått'])
HUS = entry('hus', 'house', ['et hus', 'huset', 'husene'])


def docs(*raws):
    return [{'url': 'https://lexin', 'html': raw, 'assets': {}} for raw in raws]


class EntryStoreTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.cache = DictionaryCache(Path(self.temp.name) / 'c.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def count(self, table):
        with closing(sqlite3.connect(self.cache.path)) as db:
            return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_split_keeps_notes_and_refuses_unexpected_content(self):
        manifest, documents, entries = split_lexin(NOTE + GAA + NOTE + GAA2, docs('<ul>raw1</ul>', '<ul>raw2</ul>'))
        self.assertEqual(manifest.count('<!--entry:'), 2)
        self.assertEqual(manifest.count('lexin-form-note'), 2)
        self.assertEqual([e['headword'] for e in entries], ['gå', 'gå'])
        self.assertEqual([d['entry'] for d in documents], [e['id'] for e in entries])
        self.assertNotIn('html', documents[0])
        self.assertIsNone(split_lexin('<p>plain</p>', []))
        self.assertIsNone(split_lexin('', []))

    def test_results_share_entries_and_read_back_exactly(self):
        self.cache.put('k-gaa', 'lexin', 'gå', GAA + GAA2, '', docs('<ul>a</ul>', '<ul>b</ul>'), [])
        self.cache.put('k-gikk', 'lexin', 'gikk', NOTE + GAA + NOTE + GAA2, '', docs('<ul>a</ul>', '<ul>b</ul>'), [])
        self.cache.put('k-gaatt', 'lexin', 'gått', NOTE + GAA, '', docs('<ul>a</ul>'), [])
        self.assertEqual(self.count('entries'), 2)  # gå stored once, not three times.
        ctx = Mock(audio_dir=Path(self.temp.name), images_dir=Path(self.temp.name))
        # Read back exactly, minus Lexin's search marks (cards do not show them).
        self.assertEqual(self.cache.get('k-gikk', ctx)[0], NOTE + clean_entry(GAA) + NOTE + clean_entry(GAA2))
        self.assertEqual(self.cache.entry('k-gaa')['content'], clean_entry(GAA) + clean_entry(GAA2))
        self.assertEqual([r['indirect'] for r in self.cache.search('gikk')['rows']], [['gå']])
        self.cache.delete_keys(['k-gaa', 'k-gikk'])
        self.assertEqual(self.count('entries'), 1)  # GAA2 no longer used; GAA still is.
        self.cache.delete_keys(['k-gaatt'])
        self.assertEqual((self.count('entries'), self.count('entry_forms')), (0, 0))

    def test_versions_differing_only_in_search_marks_are_one_entry(self):
        marked = GAA.replace('<span class="highlight">gå</span>', '<span class="highlight">gikk</span>')
        self.cache.put('a', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])
        self.cache.put('b', 'lexin', 'gikk', NOTE + GAA.replace('<span class="highlight">gå</span>', 'gå'), '',
                       docs('<ul>b</ul>'), [])
        self.assertEqual(self.count('entries'), 1)
        self.assertNotEqual(marked, GAA)

    def test_upgrade_merges_versions_stored_before_marks_were_removed(self):
        import sqlite3 as lite
        from app.dictionary_cache import pack
        self.cache.connect().close()
        with closing(lite.connect(self.cache.path)) as db:
            for i, (key, html) in enumerate([('a', GAA), ('b', GAA.replace('>gå</span></span>', '>gå</span></span>'))]):
                digest = f'{i:064x}'
                db.execute('INSERT INTO results(key, source, word, content, sound, documents) VALUES(?,?,?,?,?,?)',
                           (key, 'lexin', 'gå', f'<!--entry:{digest}-->', '', json.dumps([{'url': 'u', 'entry': digest}])))
                db.execute('INSERT INTO entries(id, source, variant, headword, headword_key, lexin_id, html, raw) '
                           'VALUES(?,?,?,?,?,?,?,?)', (digest, 'lexin', 'bokmal', 'gå', 'gå', '1', pack(html), pack('<ul>r</ul>')))
                db.execute('INSERT INTO result_entries VALUES(?,?)', (key, digest))
            db.commit()
        self.assertEqual(self.count('entries'), 2)
        converted, entries, _ = self.cache.upgrade()
        self.assertEqual((converted, entries), (2, 1))
        self.assertEqual(self.cache.entry('b')['content'], clean_entry(GAA))
        with closing(lite.connect(self.cache.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], DictionaryCache.STORE_VERSION)
        self.assertEqual(self.cache.upgrade()[0], 0)  # Nothing left to do.

    def test_missing_entry_makes_the_result_a_miss_not_wrong_content(self):
        self.cache.put('k', 'lexin', 'hus', HUS, '', docs('<ul>x</ul>'), [])
        with closing(sqlite3.connect(self.cache.path)) as db:
            db.execute('PRAGMA foreign_keys = OFF')
            db.execute('DELETE FROM entries')
            db.commit()
        self.assertIsNone(self.cache.get('k', Mock()))

    def test_upgrade_converts_old_rows_and_is_idempotent(self):
        self.cache.connect().close()
        with closing(sqlite3.connect(self.cache.path)) as db:
            db.execute('INSERT INTO results(key, source, word, content, sound, documents) VALUES(?,?,?,?,?,?)',
                       ('old', 'lexin', 'gikk', NOTE + GAA, '', json.dumps(docs('<ul>raw</ul>'))))
            db.execute('INSERT INTO results(key, source, word, content, sound, documents) VALUES(?,?,?,?,?,?)',
                       ('nf', 'lexin', 'xqz', '', '', '[]'))
            db.commit()
        converted, entries, forms = self.cache.upgrade()
        self.assertEqual((converted, entries), (1, 1))
        self.assertGreaterEqual(forms, 4)
        self.assertEqual(self.cache.entry('old')['content'], NOTE + clean_entry(GAA))
        self.assertTrue(self.cache.entry('nf')['not_found'])
        self.assertEqual(self.cache.upgrade()[0], 0)

    def test_form_info_shows_base_words_and_all_forms(self):
        self.cache.put('k', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])
        info = self.cache.form_info('Gikk')
        self.assertEqual((info['headword'], [b['headword'] for b in info['bases']]), ([], ['gå']))
        info = self.cache.form_info('gå')
        self.assertEqual(info['headword'][0]['variant'], 'bokmal')
        self.assertEqual(info['headword'][0]['forms'], ['gikk', 'gå', 'går', 'gått'])
        self.assertEqual(self.cache.form_info('xyz')['bases'], [])
        self.assertEqual((self.cache.stats()['entries'], self.cache.stats()['forms']), (1, 4))

    def test_offline_answer_keeps_every_meaning_and_prefers_copies_with_audio(self):
        import sqlite3 as lite
        walk = entry('gå', 'go, walk', ['gikk'])
        leave = entry('gå', 'leave', ['gikk'])  # Another meaning: same headword and pronunciation id.
        with_audio = walk.replace('</td>', '<audio class="lexin-form-audio" src="a.mp3"></audio></td>', 1)
        raw = '<ul><span id="ordbank-speaker-id-25369-0"></span></ul>'
        self.cache.put('a', 'lexin', 'gå', walk + leave, '', docs(raw, raw), [])
        self.cache.put('b', 'lexin', 'gå', with_audio, '', docs(raw), [])
        with closing(lite.connect(self.cache.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(DISTINCT lexin_id) FROM entries').fetchone()[0], 1)
        entries = self.cache.form_entries('gikk', 'bokmal')
        self.assertEqual(len(entries), 2)  # walk (the copy with audio) and leave
        self.assertEqual(sum('<audio' in e['html'] for e in entries), 1)

    def test_form_index_answers_forms_but_never_a_stored_headword(self):
        self.cache.put('k', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])
        self.assertEqual([e['headword'] for e in self.cache.form_entries('gikk', 'bokmal')], ['gå'])
        self.assertEqual(self.cache.form_entries('gikk', 'nynorsk'), [])
        self.assertEqual(self.cache.form_entries('gå', 'bokmal'), [])  # A headword: ask Lexin.
        self.assertEqual(self.cache.form_entries('husene', 'bokmal'), [])


class OfflineLookupTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        self.data['media'] = {'anki_directory': ''}
        self.data['language']['source'] = 'no'
        self.data['sources']['lexin'].update(variant='bokmal', form_entries=3)
        self.data['sources']['lexin'].pop('offline_forms', None)
        self.data['dictionary_cache'] = {'enabled': True, 'path': str(Path(self.temp.name) / 'c.sqlite3')}
        self.data['audio']['directory'] = str(Path(self.temp.name) / 'Audio')
        self.contexts = []

    def tearDown(self):
        for ctx in self.contexts:
            ctx.close()
        self.temp.cleanup()

    def context(self):
        ctx = SourceContext(Config(ROOT / 'config.toml', self.data))
        self.contexts.append(ctx)
        return ctx

    def test_inflected_form_is_built_from_stored_entries_without_lexin(self):
        ctx = self.context()
        ctx.dictionary_cache.put('k', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])
        ctx.page = Mock(side_effect=AssertionError('Lexin must not be opened'))
        content = ctx.lexin('gikk', 1)
        self.assertTrue(ctx.last_offline)
        self.assertIn('gikk → <b>gå</b>', content)
        self.assertIn('go, walk', content)
        self.assertNotIn('highlight', content)  # The other search's highlight is removed.
        rows = ctx.dictionary_cache.search('gikk', status='offline')['rows']
        self.assertEqual([(r['word'], r['offline'], r['indirect']) for r in rows], [('gikk', True, ['gå'])])
        again = self.context()
        again.page = Mock(side_effect=AssertionError('cached'))
        self.assertEqual(again.lexin('gikk', 1), content)
        self.assertTrue(again.last_cache_hit)

    def test_index_answers_when_lexin_has_no_match_but_not_after_an_error(self):
        self.data['sources']['lexin']['offline_forms'] = False
        for absent, expected in ((False, ''), (True, 'go, walk')):  # The error case first: it saves nothing.
            with self.subTest(lexin_answered=absent):
                ctx = self.context()
                ctx.dictionary_cache.put('k', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])

                def lexin(word, number, audio, a_infinitive, written, ctx=ctx, absent=absent):
                    ctx.definitely_absent = absent  # True: "Ingen treff"; False: a timeout or error.
                    return ''
                with patch.object(ctx, '_lexin', side_effect=lexin):
                    content = ctx.lexin('gikk', 1)
                if expected:
                    self.assertIn(expected, content)
                    self.assertTrue(ctx.last_lexin_missed)
                    rows = ctx.dictionary_cache.search('gikk', status='offline')['rows']
                    self.assertTrue(rows[0]['lexin_missed'])
                else:
                    self.assertEqual(content, '')
                    self.assertEqual(ctx.dictionary_cache.search('gikk')['total'], 0)  # Errors are not saved.

    def test_offline_forms_can_be_turned_off(self):
        ctx = self.context()
        ctx.dictionary_cache.put('k', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])
        self.data['sources']['lexin']['offline_forms'] = False
        with patch.object(ctx, '_lexin', return_value='<p>online</p>') as online:
            self.assertEqual(ctx.lexin('gikk', 1), '<p>online</p>')
        online.assert_called_once()

    def test_refresh_offline_asks_lexin_for_each_offline_answer(self):
        import io
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        import main
        path = Path(self.temp.name) / 'config.toml'
        text = (ROOT / 'config.toml').read_text(encoding='utf-8')
        path.write_text(text.replace('path = "Cache/dictionaries.sqlite3"', 'path = "c.sqlite3"'), encoding='utf-8')
        store = DictionaryCache(Path(self.temp.name) / 'c.sqlite3')
        store.put('k-gaa', 'lexin', 'gå', GAA, '', docs('<ul>a</ul>'), [])
        store.put('k-gikk', 'lexin', 'gikk', NOTE + GAA, '', [{'offline_forms': True}], [])
        asked = []

        class FakeLookup:
            def __init__(self, config):
                self.config = config

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def word(self, word, sources=None, audio=True):
                asked.append((word, self.config.data['sources']['lexin']['offline_forms']))
                store.put('online', 'lexin', word, NOTE + GAA + NOTE + GAA2, '', docs('<ul>a</ul>', '<ul>b</ul>'), [])
                return SimpleNamespace(source=lambda name: SimpleNamespace(status='ok', message=''))
        with patch('app.api.Lookup', FakeLookup), patch('app.api.enabled_sources', return_value=['lexin']),                 redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main.main(['--config', str(path), '--refresh-offline']), 0)
        self.assertEqual(asked, [('gikk', False)])  # Lexin itself, never the offline index.
        self.assertEqual(store.search(status='offline')['total'], 0)
        self.assertIn('Done: 1 found', out.getvalue())

    def test_offline_forms_must_be_boolean(self):
        import tomlkit
        from app.app_config import ConfigError, load_config
        doc = tomlkit.parse((ROOT / 'config.toml').read_text(encoding='utf-8'))
        doc['sources']['lexin']['offline_forms'] = 'yes'
        path = Path(self.temp.name) / 'config.toml'
        path.write_text(tomlkit.dumps(doc), encoding='utf-8')
        with self.assertRaises(ConfigError):
            load_config(path, check_files=False)


if __name__ == '__main__':
    unittest.main()
