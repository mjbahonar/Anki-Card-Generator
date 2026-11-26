"""Lexin: an inflected form (gikk, husene, bøker) finds its base entry through the inflection table."""
from pathlib import Path
import tomllib
import unittest
from unittest.mock import Mock

from app.app_config import Config
from app.lexin_scraper import inflected_forms, scrape_and_process_lexin
from app.sources import lexin_absence_current
from tests import test_lexin_scraper

ROOT = Path(__file__).resolve().parents[1]


def table(*forms):
    cells = ''.join(f'<td><div><span>{form}</span></div></td>' for form in forms)
    return f'<div class="ordbank-table desktop"><table><tr>{cells}</tr></table></div>'


class InflectedFormTests(unittest.TestCase):
    def page(self, rows):
        page, entries = test_lexin_scraper.LexinTests.result_page(self, [[(word, meaning) for word, meaning, _ in rows]])
        for entry, (word, meaning, forms) in zip(entries[0], rows):
            entry.inner_html.return_value = (
                f'<li><dd data-type="LEM" lang="nb"><span class="grunnform">{word}</span></dd>'
                f'<dd lang="en">{meaning}</dd>{table(*forms)}</li>')
            entry.locator.return_value.first.locator.return_value.first.inner_text.return_value = word
        return page, entries

    def test_forms_come_from_the_table_without_articles_or_auxiliaries(self):
        html = (ROOT / 'tests' / 'fixtures' / 'lexin_hus_entry.html').read_text(encoding='utf-8')
        self.assertTrue({'hus', 'huset', 'husa', 'husene'} <= inflected_forms(html))
        verb = inflected_forms(table('å gå', 'går', 'gikk', 'har gått', 'gå!', '—'))
        self.assertEqual(verb, {'gå', 'går', 'gikk', 'gått'})
        self.assertIn('bok', inflected_forms(table('ei/en bok', 'boka')))

    def test_inflected_form_returns_every_matching_base_entry_with_a_note(self):
        page, _ = self.page([('bøk', 'beech', ['en bøk', 'bøken', 'bøker', 'bøkene']),
                             ('bok', 'book', ['en bok', 'boken', 'bøker', 'bøkene']),
                             ('abc-bok', 'primer', ['en abc-bok', 'abc-bøker'])])
        absent = Mock()
        content, sound = scrape_and_process_lexin('bøker', 1, page, download_audio=True, verbose=False,
                                                  form_entries=3, on_not_found=absent)
        self.assertIn('beech', content)
        self.assertIn('book', content)
        self.assertNotIn('primer', content)
        self.assertEqual(content.count('lexin-form-note'), 2)
        self.assertIn('bøker → <b>bok</b>', content)
        self.assertEqual(sound, '')  # The headword recording would say "bok", not "bøker".
        absent.assert_not_called()

    def test_exact_headword_wins_and_forms_are_off_at_zero(self):
        page, _ = self.page([('hus', 'house', ['et hus', 'huset', 'husene']), ('husene', 'x', ['husene'])])
        content, _ = scrape_and_process_lexin('husene', 1, page, download_audio=False, verbose=False, form_entries=3)
        self.assertNotIn('lexin-form-note', content)  # An exact headword exists, so no form matches.
        page, _ = self.page([('gå', 'go', ['å gå', 'gikk'])])
        absent = Mock()
        content, _ = scrape_and_process_lexin('gikk', 1, page, download_audio=False, verbose=False,
                                              form_entries=0, on_not_found=absent)
        self.assertEqual(content, '')
        absent.assert_called_once()

    def test_only_the_first_form_entries_results_are_checked(self):
        page, entries = self.page([('Redd Barna', 'charity', []), ('barn', 'child', ['et barn', 'barna']),
                                   ('barnehage', 'kindergarten', ['barnehagen'])])
        content, _ = scrape_and_process_lexin('barna', 1, page, download_audio=False, verbose=False,
                                              max_entries=1, form_entries=2)
        self.assertIn('child', content)
        page, _ = self.page([('Redd Barna', 'charity', []), ('barn', 'child', ['et barn', 'barna'])])
        content, _ = scrape_and_process_lexin('barna', 1, page, download_audio=False, verbose=False,
                                              max_entries=1, form_entries=1)
        self.assertEqual(content, '')

    def test_form_entries_never_changes_the_cache_key_and_older_keys_are_reused(self):
        import json
        import tempfile
        from app.dictionary_cache import cache_key
        from app.sources import SourceContext
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        keys = set()
        for value in (None, 0, 3, 7):
            data['sources']['lexin'].pop('form_entries', None)
            if value is not None:
                data['sources']['lexin']['form_entries'] = value
            keys.add(cache_key('lexin', 'bil', Config(ROOT / 'config.toml', data), True))
        self.assertEqual(len(keys), 1)
        (ROOT / 'Output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'Output') as folder:
            data['sources']['lexin']['form_entries'] = 3
            data['media'] = {'anki_directory': ''}
            data['dictionary_cache'] = {'enabled': True, 'path': str(Path(folder) / 'c.sqlite3')}
            data['audio']['directory'] = str(Path(folder) / 'Audio')
            ctx = SourceContext(Config(ROOT / 'config.toml', data))
            try:
                key = json.loads(cache_key('lexin', 'gikk', ctx.config, False))
                key[3]['form_entries'] = 3  # How 5.8.0-5.9.0 saved it.
                ctx.dictionary_cache.put(json.dumps(key, sort_keys=True, ensure_ascii=False), 'lexin', 'gikk',
                                         '<div class="lexin-form-note">gikk → <b>gå</b></div>', '', [], [])
                loader = Mock(return_value='<p>refetched</p>')
                self.assertIn('lexin-form-note', ctx.cache_result('lexin', 'gikk', loader))
                loader.assert_not_called()
            finally:
                ctx.close()

    def test_saved_not_found_is_rechecked_when_form_checking_changes(self):
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        config = Config(ROOT / 'config.toml', data)
        data['sources']['lexin']['form_entries'] = 3
        self.assertTrue(lexin_absence_current([{'not_found': True, 'form_entries': 3}], config))
        self.assertFalse(lexin_absence_current([], config))  # Saved by 5.7.x, before forms were checked.
        data['sources']['lexin']['form_entries'] = 0
        self.assertFalse(lexin_absence_current([{'not_found': True, 'form_entries': 3}], config))


if __name__ == '__main__':
    unittest.main()
