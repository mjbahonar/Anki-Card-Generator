"""å / en / ei / et and a final "!" guide the Lexin lookup; the card may hide them."""
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch

from app.app_config import Config
from app.dictionary_cache import cache_key
from app.lexin_scraper import scrape_and_process_lexin, split_lookup
from app.sources import SourceContext
from tests import test_lexin_scraper

ROOT = Path(__file__).resolve().parents[1]


def entry(word, kat, meaning, forms=()):
    cells = ''.join(f'<td><div><span>{f}</span></div></td>' for f in forms)
    return (f'<li><dd data-type="LEM" lang="nb"><span class="grunnform">{word}</span></dd>'
            f'<dd data-type="KAT" lang="en"><span>{kat}</span></dd><dd lang="en">{meaning}</dd>'
            f'<div class="ordbank-table desktop"><table><tr>{cells}</tr></table></div></li>')


class MarkerTests(unittest.TestCase):
    def test_split_lookup(self):
        cases = {'å kjøpa': ('kjøpa', 'verb'), 'ei jul': ('jul', 'noun:feminine'), 'en skål!': ('skål', 'noun:masculine'),
                 'et spøkelse': ('spøkelse', 'noun:neuter'), 'ei/en bok': ('bok', 'noun:feminine'),
                 'skål!': ('skål', None), '  hus  ': ('hus', None), 'en': ('en', None), 'Å  lese': ('lese', 'verb')}
        for text, expected in cases.items():
            self.assertEqual(split_lookup(text, 'no'), expected, text)
        self.assertEqual(split_lookup('en skål', 'en'), ('en skål', None))  # English "en" is not a marker.
        self.assertEqual(split_lookup('hello!', 'en'), ('hello', None))

    def page(self, rows):
        page, entries = test_lexin_scraper.LexinTests.result_page(self, [[(w, m) for w, _, m, _ in rows]])
        for mock, (word, kat, meaning, forms) in zip(entries[0], rows):
            mock.inner_html.return_value = entry(word, kat, meaning, forms)
            mock.locator.return_value.first.locator.return_value.first.inner_text.return_value = word
        return page

    def test_markers_never_filter_meanings(self):
        rows = [('skål', 'interjection', 'cheers', []), ('skål', 'noun masculine or feminine', 'bowl', ['skåla'])]
        word, marker = split_lookup('en skål', 'no')
        content, _ = scrape_and_process_lexin(word, 1, self.page(rows), download_audio=False, verbose=False)
        self.assertIn('cheers', content)
        self.assertIn('bowl', content)


class LookupTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        self.data['media'] = {'anki_directory': ''}
        self.data['language']['source'] = 'no'
        self.data['dictionary_cache'] = {'enabled': True, 'path': str(Path(self.temp.name) / 'c.sqlite3')}
        self.data['audio']['directory'] = str(Path(self.temp.name) / 'Audio')
        self.ctx = SourceContext(Config(ROOT / 'config.toml', self.data))

    def tearDown(self):
        self.ctx.close()
        self.temp.cleanup()

    def test_marked_and_bare_words_share_the_cache_except_a_infinitives(self):
        from unittest.mock import Mock
        loader = Mock(return_value='<ul>to read</ul>')
        self.ctx.cache_result('lexin', 'lese', loader, False)
        self.ctx.page = Mock(side_effect=AssertionError('must come from the cache'))
        self.assertEqual(self.ctx.lexin('å lese', 1), '<ul>to read</ul>')
        config = self.ctx.config
        self.assertNotEqual(cache_key('lexin', 'kjøpa', config, False, 'a_infinitive'), cache_key('lexin', 'kjøpa', config, False))

    def test_a_infinitive_shows_its_own_results_and_the_e_infinitive_verb(self):
        calls = []

        def scrape(word, *args, **kwargs):
            calls.append(word)
            if word == 'kjøpa':
                return '<div class="lexin-form-note">kjøpa → <b>kjøp</b></div><ul>purchase</ul>', ''
            return '<ul>to buy</ul>', '[sound:lexin_no_kjøpe.mp3]'
        self.ctx.page = Mock(return_value=Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False)))
        with patch('app.sources.scrape_and_process_lexin', side_effect=scrape):
            content = self.ctx.lexin('å kjøpa!', 1)
        self.assertEqual(calls, ['kjøpa', 'kjøpe'])
        self.assertIn('purchase', content)  # Every meaning: the noun form ...
        self.assertIn('kjøpa → <b>kjøpe</b>', content)  # ... and the verb.
        self.assertLess(content.index('purchase'), content.index('to buy'))
        self.assertEqual(self.ctx.lexin_results['å kjøpa!'][1], '')  # The recording would say "kjøpe".
        rows = self.ctx.dictionary_cache.search('kjøpa')['rows']
        self.assertEqual([(r['word'], r['indirect']) for r in rows], [('kjøpa', ['kjøp', 'kjøpe'])])

    def test_show_markers_and_spoken_audio(self):
        import main
        self.data.setdefault('cards', {}).setdefault('normal', {})['show_markers'] = True
        self.assertEqual(main.front_word('en skål!', self.ctx.config), 'en skål!')
        self.data.setdefault('cards', {}).setdefault('normal', {})['show_markers'] = False
        self.assertEqual(main.front_word('en skål!', self.ctx.config), 'skål')
        self.assertEqual(main.front_word('å lese', self.ctx.config), 'lese')
        from app.sources import select_audio
        self.data['audio']['word'] = {'no': ['google_tts']}
        with patch('gtts.gTTS') as tts:
            tts.return_value.write_to_fp.side_effect = lambda buffer: buffer.write(b'ID3' + b'x' * 300)
            sound = select_audio('en skål!', 1, self.ctx, spoken='skål')
        self.assertEqual(tts.call_args.kwargs['text'], 'skål')
        self.assertIn('skål', sound)

    def test_show_markers_must_be_boolean_and_only_for_normal_cards(self):
        import tomlkit
        from app.app_config import ConfigError, load_config
        base = (ROOT / 'config.toml').read_text(encoding='utf-8')
        path = Path(self.temp.name) / 'config.toml'
        for kind, value, valid in [('normal', False, True), ('normal', 'no', False), ('type', True, False)]:
            doc = tomlkit.parse(base)
            doc['cards'][kind]['show_markers'] = value
            path.write_text(tomlkit.dumps(doc), encoding='utf-8')
            with self.subTest(kind=kind, value=value):
                if valid:
                    load_config(path, check_files=False)
                else:
                    with self.assertRaises(ConfigError):
                        load_config(path, check_files=False)


if __name__ == '__main__':
    unittest.main()
