"""Settings GUI: config.toml round trips and the local server's safety checks."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import tomllib
import unittest

from app.app_config import ConfigError
from app.gui import config_doc, i18n
from app.gui.server import create_server

ROOT = Path(__file__).resolve().parents[1]


class ConfigDocTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.path = Path(self.temp.name) / 'config.toml'
        self.text = (ROOT / 'config.toml').read_bytes().decode('utf-8')
        self.path.write_bytes(self.text.encode('utf-8'))

    def tearDown(self):
        self.temp.cleanup()

    def test_describe_covers_every_setting_with_types_choices_and_comments(self):
        schema = config_doc.describe(self.path)
        fields = {'.'.join(f['path']): f for tab in schema['tabs'] for g in tab['groups'] for f in g['fields']}
        data = tomllib.loads(self.text)

        def leaves(node, prefix=()):
            for key, value in node.items():
                if isinstance(value, dict):
                    yield from leaves(value, prefix + (key,))
                else:
                    yield '.'.join(prefix + (key,))
        self.assertEqual(set(fields), {k for k in leaves(data) if not k.startswith('anki.saved_decks.')})
        self.assertEqual(fields['sources.lexin.enabled']['type'], 'bool')
        self.assertEqual(fields['sources.lexin.variant']['mode'], 'select')
        self.assertEqual(fields['output.formats']['mode'], 'ordered')
        self.assertEqual(fields['input.file']['mode'], 'file')
        self.assertIn('bokmal, nynorsk or both', fields['sources.lexin.variant']['help'])
        self.assertEqual(schema['sources_order'][0], 'lexin')
        self.assertEqual(schema['version'], config_doc.version(self.text))

    def test_edits_keep_comments_and_untouched_lines(self):
        changed = config_doc.apply_changes(self.text, [
            {'path': ['sources', 'lexin', 'entries'], 'value': 3},
            {'path': ['output', 'formats'], 'value': ['html', 'apkg']},
            {'path': ['runtime', 'word_delay_seconds'], 'value': 2},
        ])
        old, new = self.text.splitlines(), changed.splitlines()
        self.assertEqual(len(old), len(new))
        differing = [(a, b) for a, b in zip(old, new) if a != b]
        self.assertEqual(len(differing), 3)
        for before, after in differing:
            self.assertEqual(before.partition('#')[2], after.partition('#')[2])  # Same comment.
        data = tomllib.loads(changed)
        self.assertEqual(data['sources']['lexin']['entries'], 3)
        self.assertEqual(data['output']['formats'], ['html', 'apkg'])
        self.assertEqual(data['runtime']['word_delay_seconds'], 2.0)

    def test_reordering_dictionaries_keeps_section_comments_in_place(self):
        order = config_doc.describe(self.path)['sources_order']
        new_order = [order[-1]] + order[:-1]
        changed = config_doc.apply_changes(self.text, [], new_order)
        self.assertEqual(list(tomllib.loads(changed)['sources']), new_order)
        # The comment block introducing card types still follows the dictionaries.
        cards_header = changed.index('# 04. CARD TYPES')
        self.assertGreater(cards_header, changed.index('[sources.' + order[-2] + ']'))
        self.assertLess(cards_header, changed.index('[cards.normal]'))
        self.assertEqual(self.text.count('#'), changed.count('#'))
        self.assertNotIn('\n\n\n', changed.replace('\r', ''))

    def test_sheet_and_column_accept_a_name_or_a_number(self):
        fields = {'.'.join(f['path']): f for tab in config_doc.describe(self.path)['tabs']
                  for g in tab['groups'] for f in g['fields']}
        self.assertEqual(fields['input.sheet']['type'], 'name_or_index')
        self.assertEqual(fields['input.word_column']['type'], 'name_or_index')
        named = config_doc.apply_changes(self.text, [{'path': ['input', 'sheet'], 'value': 'FINAL'},
                                                     {'path': ['input', 'word_column'], 'value': 'Word'}])
        self.assertEqual(tomllib.loads(named)['input']['sheet'], 'FINAL')
        self.assertEqual(tomllib.loads(named)['input']['word_column'], 'Word')
        back = config_doc.apply_changes(named, [{'path': ['input', 'sheet'], 'value': '2'}])
        self.assertEqual(tomllib.loads(back)['input']['sheet'], 2)  # Digits are a position, not a sheet named "2".
        self.assertIn('# First worksheet, or its name', named)
        with self.assertRaises(config_doc.EditError):
            config_doc.apply_changes(self.text, [{'path': ['input', 'sheet'], 'value': '  '}])

    def test_wrong_types_unknown_keys_and_bad_order_are_refused(self):
        bad = [
            [{'path': ['sources', 'lexin', 'enabled'], 'value': 'yes'}],
            [{'path': ['anki', 'deck_id'], 'value': 1.5}],
            [{'path': ['output', 'formats'], 'value': 'html'}],
            [{'path': ['nothing', 'here'], 'value': 1}],
            [{'path': ['sources', 'lexin'], 'value': 1}],
        ]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(config_doc.EditError):
                config_doc.apply_changes(self.text, changes)
        with self.assertRaises(config_doc.EditError):
            config_doc.apply_changes(self.text, [], ['lexin'])

    def test_saved_decks_are_created_replaced_and_validated(self):
        decks = [['My Vocabulary', 2059400451], ['Grammar: verbs', 2059400452]]
        base = config_doc.apply_changes(self.text, [{'path': ['anki', 'saved_decks'], 'decks': []}])
        changed = config_doc.apply_changes(base, [{'path': ['anki', 'saved_decks'], 'decks': decks}])
        self.assertEqual(tomllib.loads(changed)['anki']['saved_decks'],
                         {'My Vocabulary': 2059400451, 'Grammar: verbs': 2059400452})
        # The next section's heading comments stay after the list.
        self.assertLess(changed.index('Grammar: verbs'), changed.index('# 07. APPEARANCE'))
        self.path.write_bytes(changed.encode('utf-8'))
        self.assertEqual(config_doc.describe(self.path)['decks'], decks)
        replaced = config_doc.apply_changes(changed, [{'path': ['anki', 'saved_decks'], 'decks': [['Only', 5]]}])
        self.assertEqual(tomllib.loads(replaced)['anki']['saved_decks'], {'Only': 5})
        self.assertEqual(replaced.count('# 07. APPEARANCE'), 1)
        for bad in ([['A', 1], ['B', 1]], [['A', 1], ['A', 2]], [['', 1]], [['A', 0]], [['A', '1']], 'A'):
            with self.subTest(decks=bad), self.assertRaises(config_doc.EditError):
                config_doc.apply_changes(self.text, [{'path': ['anki', 'saved_decks'], 'decks': bad}])

    def test_main_accepts_saved_decks_and_rejects_shared_ids(self):
        from app.app_config import load_config
        text = config_doc.apply_changes(self.text, [{'path': ['anki', 'saved_decks'], 'decks': [['A', 7], ['B', 8]]}])
        self.path.write_bytes(text.encode('utf-8'))
        self.assertEqual(load_config(self.path, check_files=False).data['anki']['saved_decks'], {'A': 7, 'B': 8})
        self.path.write_bytes(text.replace('"B" = 8', '"B" = 7').encode('utf-8'))
        with self.assertRaises(ConfigError):
            load_config(self.path, check_files=False)

    def test_save_validates_with_main_rules_and_detects_outside_edits(self):
        version = config_doc.version(self.text)
        with self.assertRaises(ConfigError):
            config_doc.save(self.path, [{'path': ['input', 'order'], 'value': 'sideways'}], None, version)
        self.assertEqual(self.path.read_bytes().decode('utf-8'), self.text)
        other = 'excel' if tomllib.loads(self.text)['input'].get('order', 'excel') == 'random' else 'random'
        new_version, warning = config_doc.save(
            self.path, [{'path': ['input', 'order'], 'value': other}], None, version)
        self.assertIn('Input file not found', warning)  # Saved; the workbook is not in the temp folder.
        self.assertEqual(tomllib.loads(self.path.read_text(encoding='utf-8'))['input']['order'], other)
        with self.assertRaises(config_doc.ConflictError):
            config_doc.save(self.path, [{'path': ['input', 'max_words'], 'value': 7}], None, version)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ['config.toml'])
        self.assertNotEqual(new_version, version)


class ServerTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.path = Path(self.temp.name) / 'config.toml'
        self.path.write_bytes((ROOT / 'config.toml').read_bytes())
        self.server, self.app = create_server(self.path, ROOT / 'main.py')
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, url, body=None, token=True, host=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        headers = {'Host': host or f'127.0.0.1:{self.port}', 'Content-Type': 'application/json'}
        if token:
            headers['X-GUI-Token'] = self.app.token
        if origin:
            headers['Origin'] = origin
        connection.request(method, url, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data

    def test_page_is_public_but_api_needs_token_local_host_and_same_origin(self):
        status, page = self.request('GET', '/', token=False)
        self.assertEqual(status, 200)
        self.assertIn(b'app.js', page)
        self.assertEqual(self.request('GET', '/api/state', token=False)[0], 403)
        self.assertEqual(self.request('GET', '/', host='evil.example:80')[0], 403)
        self.assertEqual(self.request('POST', '/api/run', {'kind': 'check'}, origin='http://evil.example')[0], 403)
        self.assertEqual(self.request('GET', '/static/../config_doc.py')[0], 404)
        self.assertIsNone(self.app.job)

    def test_state_and_save_round_trip(self):
        status, data = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        state = json.loads(data)
        self.assertEqual(state['strings']['action.run'], 'Run')
        self.assertIn('lexin', state['cache_sources'])
        body = {'changes': [{'path': ['runtime', 'headless'], 'value': False}],
                'sources_order': None, 'version': state['schema']['version']}
        status, data = self.request('POST', '/api/save', body)
        self.assertEqual(status, 200, data)
        self.assertFalse(tomllib.loads(self.path.read_text(encoding='utf-8'))['runtime']['headless'])
        self.assertEqual(self.request('POST', '/api/save', body)[0], 409)  # Old version: conflict.
        status, data = self.request('GET', '/api/files?check=' + 'config.toml')
        self.assertEqual((status, json.loads(data)['exists']), (200, True))
        status, data = self.request('GET', '/api/files?check=' + 'missing%20book.xlsx')
        self.assertFalse(json.loads(data)['exists'])
        self.assertEqual(self.request('POST', '/api/browse', {'kind': 'anything'})[0], 400)
        self.assertEqual(self.request('POST', '/api/run', {'kind': 'format_disk'})[0], 400)
        self.assertEqual(self.request('POST', '/api/run', {'kind': 'clear_cache', 'source': '../x'})[0], 400)


class DatabaseEndpointTests(ServerTests):
    def test_database_tab_reads_the_configured_cache_and_waits_for_runs(self):
        from unittest.mock import Mock
        from app.dictionary_cache import DictionaryCache
        self.assertFalse(json.loads(self.request('GET', '/api/db/stats')[1])['exists'])
        store = DictionaryCache(self.path.parent / 'Cache' / 'dictionaries.sqlite3')
        store.put('k1', 'lexin', 'hus', '<p>house</p>', '', [], [])
        store.put('k2', 'lexin', 'xqz', '', '', [], [])
        stats = json.loads(self.request('GET', '/api/db/stats')[1])
        self.assertEqual((stats['results'], stats['not_found']), (2, 1))
        found = json.loads(self.request('GET', '/api/db/search?q=hu&status=found')[1])
        self.assertEqual([r['word'] for r in found['rows']], ['hus'])
        self.assertEqual(self.request('GET', '/api/db/search?status=bogus')[0], 400)
        self.assertEqual(json.loads(self.request('GET', '/api/db/entry?key=k1')[1])['content'], '<p>house</p>')
        self.assertEqual(self.request('GET', '/api/db/entry?key=nope')[0], 404)
        self.app.job = Mock(running=True)
        self.assertEqual(self.request('POST', '/api/db/delete', {'keys': ['k1']})[0], 409)
        self.app.job = None
        self.assertEqual(json.loads(self.request('POST', '/api/db/delete', {'keys': ['k1']})[1])['removed'], 1)
        store.put('k3', 'oxford', 'bil', '<p>car</p>', '', [], [])
        self.assertEqual(self.request('POST', '/api/db/delete_matching', {'status': 'bogus'})[0], 400)
        self.assertEqual(json.loads(self.request('POST', '/api/db/delete_matching',
                                                 {'q': 'bi', 'source': 'oxford'})[1])['removed'], 1)
        self.assertEqual(json.loads(self.request('POST', '/api/db/forget_not_found', {})[1])['removed'], 1)
        self.assertEqual(self.request('POST', '/api/db/compact', {})[0], 200)
        self.assertEqual(self.request('POST', '/api/run', {'kind': 'refresh_word', 'word': ' '})[0], 400)


class StringsTests(unittest.TestCase):
    def test_other_languages_fall_back_to_english(self):
        self.assertEqual(i18n.strings('xx')['action.run'], 'Run')
        self.assertEqual(i18n.languages()[0]['code'], i18n.DEFAULT_LANGUAGE)
        for language, table in i18n.STRINGS.items():
            self.assertIn(table['_meta']['dir'], ('ltr', 'rtl'), language)


if __name__ == '__main__':
    unittest.main()
