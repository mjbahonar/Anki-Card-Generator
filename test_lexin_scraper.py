import unittest
from unittest.mock import Mock

from lexin_scraper import (normalize_headword, render_lexin_entry,
                           save_lexin_audio, choose_norwegian_audio, audio_filename)


class LexinTests(unittest.TestCase):
    def test_headword_requires_whole_word_and_preserves_accents(self):
        self.assertEqual(normalize_headword(' BOK '), 'bok')
        self.assertNotEqual(normalize_headword('barnebok'), 'bok')
        self.assertNotEqual(normalize_headword('bøk'), 'bok')
        self.assertEqual(normalize_headword('bla\u030a'), normalize_headword('blå'))

    def test_complete_entry_retains_one_inflection_table_without_site_controls(self):
        output = render_lexin_entry('''<li><dl><dt>Bokmål</dt><dd>bok</dd></dl>
            <details><summary>Show</summary><div class="dictionary-ordbank">
            <div class="ordbank-table desktop"><table><tr><td rowspan="2">bøker</td></tr></table></div>
            <div class="ordbank-table mobile"><table><tr><td>bøker</td></tr></table></div>
            </div></details><p onclick="bad()">Explanation</p><a class="tts-btn">Play</a>
            <script>bad()</script></li>''')
        self.assertEqual(output.count('<table'), 1)
        self.assertIn('rowspan="2"', output)
        self.assertIn('Explanation', output)
        self.assertNotIn('onclick', output)
        self.assertNotIn('<script', output)
        self.assertNotIn('tts-btn', output)

    def test_html_error_is_not_saved_as_audio(self):
        response = Mock(ok=True)
        response.body.return_value = b'<html>Error</html>' * 20
        with self.assertRaises(ValueError):
            save_lexin_audio(response, 'bok')

    def test_audio_prefers_lexin_then_google_and_handles_both_failing(self):
        google = Mock(return_value='<audio><source src="google.mp3"></audio>')
        self.assertEqual(choose_norwegian_audio('bok', 1, '[sound:lexin.mp3]', google), '[sound:lexin.mp3]')
        google.assert_not_called()
        self.assertEqual(choose_norwegian_audio('bok', 1, '', google), '[sound:google.mp3]')
        google.return_value = ''
        self.assertEqual(choose_norwegian_audio('bok', 1, '', google), '')

    def test_audio_filename_is_safe_and_distinguishes_words(self):
        self.assertNotIn('/', audio_filename('../bok', 'lexin'))
        self.assertNotEqual(audio_filename('a b', 'lexin'), audio_filename('a_b', 'lexin'))


if __name__ == '__main__':
    unittest.main()
