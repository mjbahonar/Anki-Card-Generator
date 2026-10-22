"""Offline cache integration: repeat runs, media recovery and incomplete results."""
import copy
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from app.app_config import Config
from app.dictionary_cache import cache_key
from app.sources import SourceContext, dictionary_content


ROOT = Path(__file__).resolve().parents[1]
MP3 = b'ID3' + b'x' * 200


class CacheTests(unittest.TestCase):
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

    def context(self, data=None):
        ctx = SourceContext(Config(self.root / 'config.toml', copy.deepcopy(data or self.data)))
        self.contexts.append(ctx)
        ctx.session.get = Mock(side_effect=AssertionError('Unexpected network'))
        return ctx

    def test_oxford_repeat_across_languages_has_no_requests_and_retains_raw_media(self):
        ctx = self.context()
        markup = '<div class="entry"><h1 class="headword">book</h1><div class="sense"><span class="def">a book</span></div><div data-src-mp3="/book.mp3"></div><img src="/book.png"></div>'
        ctx.fetch = Mock(return_value=Mock(text=markup, url='https://www.oxfordlearnersdictionaries.com/definition/english/book'))
        image = BytesIO()
        Image.new('RGB', (100, 100)).save(image, format='PNG')
        ctx.session.get = Mock(side_effect=[Mock(content=MP3), Mock(content=image.getvalue())])
        first = dictionary_content('oxford', 'book', 1, ctx)
        self.assertEqual(ctx.session.get.call_count, 2)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            documents = db.execute('SELECT documents FROM results').fetchone()[0]
            self.assertIn('data-src-mp3', documents)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 2)
        for path in (ctx.dictionary_cache.path.parent / 'media').iterdir():
            path.unlink()
        data = copy.deepcopy(self.data)
        data['language']['source'] = 'fa'
        other = self.context(data)
        other.fetch = Mock(side_effect=AssertionError('Oxford must be cached'))
        self.assertEqual(dictionary_content('oxford', 'BOOK', 2, other), first)
        self.assertTrue(other.last_cache_hit)
        self.assertEqual(len(list((other.dictionary_cache.path.parent / 'media').iterdir())), 2)

    def test_lexin_restores_sound_and_table_media_after_deletion(self):
        ctx = self.context()
        def load():
            ctx.audio_dir.mkdir()
            path = ctx.audio_dir / 'table.mp3'
            path.write_bytes(MP3)
            ctx.register_audio(path)
            ctx.lexin_results['bok'] = ('<audio src="table.mp3"></audio>', '[sound:table.mp3]')
            return ctx.lexin_results['bok'][0]
        with patch.object(ctx, '_lexin', side_effect=lambda *args: load()) as loader:
            first = ctx.lexin('bok', 1, audio=True)
            loader.assert_called_once()
        (ctx.audio_dir / 'table.mp3').unlink()
        other = self.context()
        with patch.object(other, '_lexin', side_effect=AssertionError('Must reuse')):
            self.assertEqual(other.lexin('bok', 2, audio=True), first)
        self.assertEqual(other.lexin_results['bok'][1], '[sound:table.mp3]')
        self.assertIn('bok', other.lexin_audio_attempted)
        self.assertEqual((other.audio_dir / 'table.mp3').read_bytes(), MP3)
        self.assertIn((other.audio_dir / 'table.mp3').resolve(), other.media)

    def test_images_reuse_exact_markup_and_restore_to_changed_output(self):
        ctx = self.context()
        def load():
            ctx.images_dir.mkdir(parents=True)
            path = ctx.images_dir / 'image.png'
            path.write_bytes(b'original image bytes')
            ctx.register_media(path)
            return '<img src="image.png"><p>original credit</p>'
        with patch('app.sources._dictionary_content', side_effect=lambda *args: load()) as loader:
            first = dictionary_content('images', 'house', 1, ctx)
            loader.assert_called_once()
        data = copy.deepcopy(self.data)
        data['output']['directory'] = str(self.root / 'new_output')
        other = self.context(data)
        with patch('app.sources._dictionary_content', side_effect=AssertionError('No image search')):
            self.assertEqual(dictionary_content('images', 'house', 1, other), first)
        self.assertEqual((other.images_dir / 'image.png').read_bytes(), b'original image bytes')

    def test_effective_options_and_translation_languages_are_isolated(self):
        config = self.context().config
        changed = copy.deepcopy(config.data)
        changed['language']['source'] = 'fa'
        changed = Config(config.path, changed)
        self.assertEqual(cache_key('oxford', 'book', config), cache_key('oxford', 'book', changed))
        self.assertNotEqual(cache_key('google_translate', 'book', config), cache_key('google_translate', 'book', changed))
        changed.data['sources']['lexin']['variant'] = 'nynorsk'
        self.assertNotEqual(cache_key('lexin', 'bok', config), cache_key('lexin', 'bok', changed))
        changed.data['sources']['oxford']['examples_per_definition'] = 9
        self.assertNotEqual(cache_key('oxford', 'book', config), cache_key('oxford', 'book', changed))
        self.assertNotEqual(cache_key('lexin', 'bok', config, True), cache_key('lexin', 'bok', config, False))

    def test_image_search_original_bytes_and_credit_survive_offline_reuse(self):
        ctx = self.context()
        ctx.config.data['sources']['images'] = {'enabled': True, 'count': 1, 'priority': ['commons']}
        original = BytesIO()
        Image.new('RGB', (1000, 900), 'blue').save(original, format='JPEG')
        ctx.fetch = Mock(return_value=Mock(content=original.getvalue()))
        with patch('app.image_sources.candidates', return_value=[('https://example.com/photo.jpg', 'Artist / License')]):
            first = dictionary_content('images', 'house', 1, ctx)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            assets = [row[0] for row in db.execute('SELECT data FROM assets')]
            self.assertIn(original.getvalue(), assets)
            self.assertEqual(len(assets), 2)
        other = self.context(ctx.config.data)
        other.fetch = Mock(side_effect=AssertionError('No downloads'))
        with patch('app.image_sources.candidates', side_effect=AssertionError('No search')):
            self.assertEqual(dictionary_content('images', 'house', 1, other), first)
        self.assertIn('Artist / License', first)
        self.assertEqual(len(other.media), 1)

    def test_empty_error_partial_and_timeout_do_not_become_cache_hits(self):
        for mode in ('empty', 'error', 'partial', 'timeout'):
            with self.subTest(mode=mode):
                ctx = self.context()
                def load():
                    if mode == 'error':
                        raise ValueError('offline')
                    if mode == 'partial':
                        ctx.issue(mode, 'oxford', 'second entry failed')
                    if mode == 'timeout':
                        ctx.source_deadline = 0
                    return '' if mode == 'empty' else '<p>partial</p>'
                if mode in ('error', 'timeout'):
                    with self.assertRaises((ValueError, TimeoutError)):
                        ctx.cache_result('oxford', mode, load)
                else:
                    ctx.cache_result('oxford', mode, load)
                self.assertIsNone(ctx.cache_capture)
                loader = Mock(return_value='complete')
                other = self.context()
                self.assertEqual(other.cache_result('oxford', mode, loader), 'complete')
                loader.assert_called_once()

    def test_svg_entry_images_are_backed_up_losslessly(self):
        ctx = self.context()
        svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
        ctx.session.get = Mock(return_value=Mock(content=svg))
        def load():
            ctx.capture_entry('<img src="/image.svg">', 'https://example.com/entry')
            return '<p>definition</p>'
        ctx.cache_result('oxford', 'book', load)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            self.assertEqual(db.execute('SELECT data FROM assets').fetchone()[0], svg)
            self.assertTrue(db.execute('SELECT filename FROM result_media').fetchone()[0].endswith('.svg'))
        self.assertEqual(ctx.errors, [])
        other = self.context()
        self.assertEqual(other.cache_result('oxford', 'book', lambda: 'unexpected'), '<p>definition</p>')
        self.assertTrue(other.last_cache_hit)

    def test_optional_bad_image_does_not_discard_lexin_text_and_sound(self):
        ctx = self.context()
        ctx.session.get = Mock(return_value=Mock(content=b'<html>image unavailable</html>'))
        def load(*args):
            ctx.capture_entry('<img src="/broken.png">', 'https://example.com/entry')
            ctx.audio_dir.mkdir()
            path = ctx.audio_dir / 'headword.mp3'
            path.write_bytes(MP3)
            sound = ctx.register_audio(path)
            ctx.lexin_results['bok'] = ('<p>book</p>', sound)
            return '<p>book</p>'
        with patch.object(ctx, '_lexin', side_effect=load):
            self.assertEqual(ctx.lexin('bok', 1, audio=True), '<p>book</p>')
        self.assertIn('https://example.com/broken.png', ctx.errors[0]['message'])
        self.assertNotIn('BytesIO', ctx.errors[0]['message'])
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            self.assertIn('media_errors', db.execute('SELECT documents FROM results').fetchone()[0])
        other = self.context()
        with patch.object(other, '_lexin', side_effect=AssertionError('Must not revisit Lexin')):
            self.assertEqual(other.lexin('bok', 2, audio=True), '<p>book</p>')
        self.assertTrue(other.last_cache_hit)
        self.assertEqual(other.lexin_results['bok'][1], '[sound:headword.mp3]')
        other.session.get.assert_not_called()

    def test_refresh_replaces_success_but_failure_keeps_previous_result(self):
        ctx = self.context()
        ctx.cache_result('oxford', 'book', lambda: 'old')
        ctx.config.data['dictionary_cache']['refresh'] = True
        ctx.cache_result('oxford', 'book', lambda: 'new')
        with self.assertRaises(ValueError):
            ctx.cache_result('oxford', 'book', lambda: (_ for _ in ()).throw(ValueError('offline')))
        other = self.context()
        self.assertEqual(other.cache_result('oxford', 'book', lambda: 'unexpected'), 'new')

    def test_disabled_and_broken_cache_allow_dictionary_lookup(self):
        ctx = self.context()
        ctx.dictionary_cache.path.parent.mkdir(parents=True)
        ctx.dictionary_cache.path.write_bytes(b'not a database')
        self.assertEqual(ctx.cache_result('oxford', 'book', lambda: 'definition'), 'definition')
        self.assertTrue(ctx.errors)
        data = copy.deepcopy(self.data)
        data['dictionary_cache']['enabled'] = False
        other = self.context(data)
        loader = Mock(return_value='definition')
        other.cache_result('oxford', 'book', loader)
        other.cache_result('oxford', 'book', loader)
        self.assertEqual(loader.call_count, 2)

    def test_corrupted_media_backup_triggers_fetch(self):
        ctx = self.context()
        def load():
            ctx.audio_dir.mkdir()
            path = ctx.audio_dir / 'test.mp3'
            path.write_bytes(MP3)
            ctx.register_audio(path)
            return 'definition'
        ctx.cache_result('oxford', 'book', load)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            db.execute('UPDATE assets SET data=?', (b'corrupt',))
            db.commit()
        other = self.context()
        loader = Mock(return_value='refetched')
        self.assertEqual(other.cache_result('oxford', 'book', loader), 'refetched')
        loader.assert_called_once()

    def test_lexin_legacy_results_reuse_existing_cache_until_word_is_explicitly_cleared(self):
        import json
        ctx = self.context()
        key = cache_key('lexin', 'gift', ctx.config)
        old = json.loads(key)
        old[3].pop('adapter_revision')
        old_key = json.dumps(old, sort_keys=True, ensure_ascii=False)
        ctx.dictionary_cache.put(old_key, 'lexin', 'gift', 'poison only', '', [], [])
        ctx.cache_result('oxford', 'gift', lambda: 'Oxford entry')
        loader = Mock(return_value='poison and married')
        self.assertEqual(ctx.cache_result('lexin', 'gift', loader), 'poison only')
        loader.assert_not_called()
        self.assertTrue(ctx.last_cache_hit)
        self.assertEqual(ctx.dictionary_cache.delete_word('gift', 'lexin'), 1)
        self.assertEqual(ctx.cache_result('lexin', 'gift', loader), 'poison and married')
        loader.assert_called_once()
        self.assertEqual(ctx.cache_result('lexin', 'gift', lambda: 'unexpected'), 'poison and married')
        self.assertEqual(ctx.cache_result('oxford', 'gift', lambda: 'unexpected'), 'Oxford entry')

    def test_all_exact_lexin_entries_are_saved_and_reused_without_browser(self):
        import json
        from contextlib import nullcontext
        from tests.test_lexin_scraper import LexinTests
        ctx = self.context()
        ctx.config.data['audio']['enabled'] = False
        ctx.config.data['sources']['lexin']['table_audio'] = False
        page, _ = LexinTests().result_page([[('gift', 'poison'), ('gift', 'married'), ('gave', 'gift, present')]])
        page.url = 'https://lexin.oslomet.no/#/findwords/message.bokmal-english?q=gift'
        with patch.object(ctx, 'page', return_value=nullcontext(page)):
            first = dictionary_content('lexin', 'gift', 1, ctx)
        self.assertIn('poison', first)
        self.assertIn('married', first)
        self.assertNotIn('present', first)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            content, documents = db.execute('SELECT content, documents FROM results').fetchone()
        self.assertEqual(content, first)
        self.assertEqual(len(json.loads(documents)), 2)
        other = self.context(ctx.config.data)
        with patch.object(other, 'page', side_effect=AssertionError('Cache must not open browser')):
            self.assertEqual(dictionary_content('lexin', 'gift', 1, other), first)
        self.assertTrue(other.last_cache_hit)

    def test_delete_word_removes_all_selected_variants_preserving_other_sources_and_media(self):
        ctx = self.context()
        ctx.audio_dir.mkdir()
        shared = ctx.audio_dir / 'shared.mp3'
        shared.write_bytes(MP3)
        unique = ctx.audio_dir / 'unique.mp3'
        unique.write_bytes(b'ID3' + b'y' * 200)
        cache = ctx.dictionary_cache
        cache.put('old', 'lexin', 'Gift', 'old', '', [], [(shared, 'audio'), (unique, 'audio')])
        cache.put('new', 'lexin', 'gift', 'new', '', [], [(shared, 'audio')])
        cache.put('other-source', 'oxford', 'gift', 'Oxford', '', [], [(shared, 'audio')])
        cache.put('other-word', 'lexin', 'giftig', 'poisonous', '', [], [])
        self.assertEqual(cache.delete_word(' GIFT ', 'lexin'), 2)
        with closing(sqlite3.connect(cache.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM results').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM result_media').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertTrue(unique.is_file())
        self.assertTrue(shared.is_file())
        self.assertEqual(cache.delete_word('gift'), 1)
        self.assertEqual(cache.delete_word('gift'), 0)
        with closing(sqlite3.connect(cache.path)) as db:
            self.assertEqual(db.execute('SELECT word FROM results').fetchone()[0], 'giftig')

    def test_clear_cache_cli_needs_neither_excel_nor_network_and_missing_db_is_noop(self):
        import io
        from contextlib import redirect_stdout
        from main import main
        ctx = self.context()
        ctx.cache_result('lexin', 'gift', lambda: 'both entries')
        path = self.root / 'maintenance.toml'
        path.write_text('[dictionary_cache]\npath = "' + ctx.dictionary_cache.path.as_posix() + '"\n', encoding='utf-8')
        output = io.StringIO()
        with patch('main.run', side_effect=AssertionError('Must not run')), redirect_stdout(output):
            self.assertEqual(main(['--config', str(path), '--clear-cache', 'gift', '--source', 'lexin']), 0)
        self.assertIn('Removed 1 cached results', output.getvalue())
        missing = self.context()
        missing.dictionary_cache.path = self.root / 'missing.sqlite3'
        self.assertEqual(missing.dictionary_cache.delete_word('gift'), 0)
        self.assertFalse(missing.dictionary_cache.path.exists())

    def test_cached_tts_table_pronunciation_skips_lexin_wait_and_registers_media(self):
        from app.lexin_scraper import audio_filename, download_table_audio
        ctx = self.context()
        ctx.audio_dir.mkdir()
        path = ctx.audio_dir / audio_filename('gift', 'google_tts', 'no')
        path.write_bytes(MP3)
        entry, page = Mock(), Mock()
        buttons = entry.locator.return_value
        buttons.count.return_value = 1
        buttons.nth.return_value.locator.return_value.locator.return_value.first.inner_text.return_value = 'gift'
        fallback = Mock(side_effect=AssertionError('Must not regenerate cached TTS'))
        sounds = download_table_audio(entry, page, ctx.audio_dir, 'no', lambda: 1000,
                                      on_media=ctx.register_audio, fallback=fallback,
                                      cached_fallback=ctx.cached_table_audio_fallback)
        self.assertEqual(sounds, {'gift': path.name})
        page.expect_response.assert_not_called()
        buttons.nth.return_value.click.assert_not_called()
        self.assertIn(path.resolve(), ctx.media)
        fallback.assert_not_called()

    def test_original_cached_lexin_table_audio_is_preferred_to_tts(self):
        from app.lexin_scraper import audio_filename, download_table_audio
        ctx = self.context()
        ctx.audio_dir.mkdir()
        path = ctx.audio_dir / audio_filename('gift', 'lexin_table', 'no')
        path.write_bytes(MP3)
        entry, page = Mock(), Mock()
        buttons = entry.locator.return_value
        buttons.count.return_value = 1
        buttons.nth.return_value.locator.return_value.locator.return_value.first.inner_text.return_value = 'gift'
        cached_fallback = Mock(side_effect=AssertionError('Original Lexin file should win'))
        sounds = download_table_audio(entry, page, ctx.audio_dir, 'no', lambda: 1000,
                                      on_media=ctx.register_audio, cached_fallback=cached_fallback)
        self.assertEqual(sounds, {'gift': path.name})
        self.assertIn(path.resolve(), ctx.media)
        cached_fallback.assert_not_called()
        page.expect_response.assert_not_called()

    def test_bad_cached_tts_audio_is_not_reused(self):
        from app.lexin_scraper import audio_filename
        ctx = self.context()
        ctx.audio_dir.mkdir()
        path = ctx.audio_dir / audio_filename('gift', 'google_tts', 'no')
        path.write_bytes(b'<html>Not audio</html>')
        self.assertEqual(ctx.cached_table_audio_fallback('gift', 'no'), '')
        self.assertEqual(ctx.media, set())

    def test_replay_icons_are_not_archived_but_entry_illustrations_are(self):
        ctx = self.context()
        image = BytesIO()
        Image.new('RGB', (100, 100)).save(image, format='PNG')
        ctx.session.get = Mock(return_value=Mock(content=image.getvalue()))
        def load():
            ctx.capture_entry('<button class="tts-btn"><img src="/speaker.svg"></button>'
                              '<img src="/real-illustration.png">', 'https://example.com/entry')
            return 'definition'
        ctx.cache_result('lexin', 'gift', load)
        ctx.session.get.assert_called_once()
        self.assertEqual(ctx.session.get.call_args.args[0], 'https://example.com/real-illustration.png')

    def test_slow_table_service_is_waited_for_only_once_per_word(self):
        from app.lexin_scraper import download_table_audio
        ctx = self.context()
        entry, page = Mock(), Mock()
        buttons = entry.locator.return_value
        buttons.count.return_value = 2
        controls = [Mock(), Mock()]
        buttons.nth.side_effect = lambda i: controls[i]
        for button, text in zip(controls, ('en hund', 'hunder')):
            button.locator.return_value.locator.return_value.first.inner_text.return_value = text
        page.expect_response.side_effect = TimeoutError('Table service unavailable')
        fallback = Mock(side_effect=lambda form, language: '[sound:' + form.replace(' ', '_') + '.mp3]')
        state = {'unavailable': False}
        sounds = download_table_audio(entry, page, ctx.audio_dir, 'no', lambda: 10000,
                                      fallback=fallback, native_state=state)
        self.assertEqual(len(sounds), 2)
        page.expect_response.assert_called_once()
        self.assertEqual(page.expect_response.call_args.kwargs['timeout'], 1500)
        self.assertEqual(fallback.call_count, 2)
        self.assertTrue(state['unavailable'])

    def test_native_service_failure_does_not_override_existing_original_table_audio(self):
        from app.lexin_scraper import audio_filename, download_table_audio
        ctx = self.context()
        ctx.audio_dir.mkdir()
        original = ctx.audio_dir / audio_filename('hunder', 'lexin_table', 'no')
        original.write_bytes(MP3)
        entry, page = Mock(), Mock()
        buttons = entry.locator.return_value
        buttons.count.return_value = 1
        buttons.nth.return_value.locator.return_value.locator.return_value.first.inner_text.return_value = 'hunder'
        fallback = Mock(side_effect=AssertionError('Original file must remain preferred'))
        sounds = download_table_audio(entry, page, ctx.audio_dir, 'no', lambda: 10000,
                                      fallback=fallback, native_state={'unavailable': True}, on_media=ctx.register_audio)
        self.assertEqual(sounds, {'hunder': original.name})
        page.expect_response.assert_not_called()
        fallback.assert_not_called()

    def test_refetch_repairs_corrupted_shared_media_blob(self):
        ctx = self.context()
        ctx.audio_dir.mkdir()
        media = ctx.audio_dir / 'voice.mp3'
        media.write_bytes(MP3)
        key = cache_key('oxford', 'book', ctx.config)
        ctx.dictionary_cache.put(key, 'oxford', 'book', 'definition', '', [], [(media, 'audio')])
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            db.execute('UPDATE assets SET data=?', (b'bad bytes',))
            db.commit()
        self.assertIsNone(ctx.dictionary_cache.get(key, ctx))
        ctx.dictionary_cache.put(key, 'oxford', 'book', 'definition', '', [], [(media, 'audio')])
        self.assertEqual(ctx.dictionary_cache.get(key, ctx)[0], 'definition')

    def test_google_image_results_page_thumbnails_are_not_downloaded_for_archive(self):
        ctx = self.context()
        ctx.config.data['sources']['images'] = {'enabled': True, 'count': 1, 'priority': ['google']}
        image = BytesIO()
        Image.new('RGB', (100, 100), 'red').save(image, format='PNG')
        results = ''.join(f'<img src="https://images.example/{i}.png">' for i in range(20))
        def get(url, **kwargs):
            if 'google.com/search' in url:
                return Mock(url=url, text=results, headers={'Content-Type': 'text/html'})
            return Mock(url=url, content=image.getvalue(), headers={'Content-Type': 'image/png'})
        ctx.session.get = Mock(side_effect=get)
        dictionary_content('images', 'apple', 1, ctx)
        self.assertEqual(ctx.session.get.call_count, 2)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            documents = json.loads(db.execute('SELECT documents FROM results').fetchone()[0])
        self.assertEqual([document['url'] for document in documents], ['https://images.example/0.png'])

    def test_translation_archives_only_the_result_without_page_images(self):
        ctx = self.context()
        page = '<img src="https://translate.example/logo.png"><div class="result-container">book</div>'
        ctx.session.get = Mock(return_value=Mock(url='https://translate.google.com/m', text=page))
        self.assertIn('book', dictionary_content('google_translate', 'bok', 1, ctx))
        self.assertEqual(ctx.session.get.call_count, 1)
        with closing(sqlite3.connect(ctx.dictionary_cache.path)) as db:
            documents = json.loads(db.execute('SELECT documents FROM results').fetchone()[0])
        self.assertEqual([document['html'] for document in documents], ['<div class="result-container">book</div>'])


if __name__ == '__main__':
    unittest.main()
