import unittest
from unittest.mock import Mock, patch

from app.lexin_scraper import (normalize_headword, render_lexin_entry,
                           save_lexin_audio, choose_norwegian_audio, audio_filename, scrape_and_process_lexin)


class LexinTests(unittest.TestCase):
    def result_page(self, pages):
        page = Mock()
        state = {'index': 0}
        candidates = []
        for rows in pages:
            current = []
            for word, meaning in rows:
                entry = Mock()
                entry.inner_html.return_value = (
                    f'<li><dd data-type="LEM" lang="nb"><span class="grunnform">{word}</span></dd>'
                    f'<dd lang="en">{meaning}</dd><div class="ordbank-table desktop"><table><tr><td>'
                    f'<div><span>{word}</span></div></td></tr></table></div></li>')
                lemmas = entry.locator.return_value
                lemmas.count.return_value = 1
                forms = lemmas.first.locator.return_value
                forms.count.return_value = 1
                forms.all_text_contents.return_value = [word]
                forms.nth.return_value.inner_text.return_value = word
                current.append(entry)
            candidates.append(current)
        entries = page.locator.return_value
        entries.count.side_effect = lambda: len(candidates[state['index']])
        entries.nth.side_effect = lambda i: candidates[state['index']][i]
        entries.evaluate_all.side_effect = lambda *args: [e.inner_html() for e in candidates[state['index']]]
        next_button = page.get_by_role.return_value
        next_button.count.return_value = 1
        next_button.is_enabled.side_effect = lambda: state['index'] < len(candidates) - 1
        next_button.click.side_effect = lambda **kwargs: state.update(index=state['index'] + 1)
        return page, candidates

    def test_all_exact_homographs_include_both_meanings_and_exclude_english_matches(self):
        page, entries = self.result_page([[('gift', 'poison'), ('gift', 'married'), ('gave', 'gift, present'), ('giftig', 'poisonous')]])
        archive = Mock()
        content, sound = scrape_and_process_lexin('gift', 1, page, download_audio=False, verbose=False, on_entry=archive)
        self.assertIn('poison', content)
        self.assertIn('married', content)
        self.assertNotIn('present', content)
        self.assertNotIn('poisonous', content)
        self.assertEqual(content.count('gt-container lexin-container'), 2)
        self.assertEqual(archive.call_count, 2)
        self.assertEqual(sound, '')

    def test_later_pages_are_never_visited(self):
        page, entries = self.result_page([[('gift', 'poison')], [('gave', 'gift, present'), ('gift', 'married')], [('gift', 'poison')]])
        content, _ = scrape_and_process_lexin('gift', 1, page, download_audio=False, verbose=False)
        self.assertEqual(content.count('poison'), 1)
        self.assertNotIn('married', content)
        page.get_by_role.assert_not_called()
        page.wait_for_function.assert_not_called()

    def test_table_audio_is_processed_for_each_matching_entry_headword_only_once(self):
        page, entries = self.result_page([[('gift', 'poison'), ('gift', 'married')]])
        pending = Mock()
        page.expect_response.return_value.__enter__ = Mock(return_value=pending)
        page.expect_response.return_value.__exit__ = Mock(return_value=False)
        with (patch('app.lexin_scraper.download_table_audio', return_value={'gift': 'table.mp3'}) as table,
              patch('app.lexin_scraper.save_lexin_audio', return_value='[sound:gift.mp3]') as sound):
            content, audio = scrape_and_process_lexin('gift', 1, page, table_audio=True, verbose=False)
        self.assertEqual(table.call_count, 2)
        self.assertIs(table.call_args_list[0].kwargs['native_state'], table.call_args_list[1].kwargs['native_state'])
        sound.assert_called_once()
        self.assertEqual(content.count('src="table.mp3"'), 2)
        self.assertEqual(audio, '[sound:gift.mp3]')

    def test_only_first_two_results_are_inspected_and_exact_match_is_still_required(self):
        page, entries = self.result_page([[('gave', 'gift, present'), ('gift', 'married'), ('gift', 'poison')]])
        entries[0][2].inner_html.side_effect = AssertionError('Third result must never be read')
        error = Mock()
        content, _ = scrape_and_process_lexin('gift', 1, page, download_audio=False, verbose=False, on_error=error)
        self.assertNotIn('poison', content)
        self.assertIn('married', content)
        self.assertNotIn('present', content)
        error.assert_not_called()

    def test_configured_entry_count_keeps_only_exact_matches_within_limit(self):
        rows = [('reise', 'trip'), ('reise', 'travel'), ('reise', 'raise'), ('reisesyk', 'sick')]
        page, _ = self.result_page([rows])
        content, _ = scrape_and_process_lexin('reise', 1, page, download_audio=False, verbose=False, max_entries=4)
        self.assertEqual(content.count('gt-container lexin-container'), 3)
        self.assertNotIn('sick', content)
        page, _ = self.result_page([rows])
        content, _ = scrape_and_process_lexin('reise', 1, page, download_audio=False, verbose=False, max_entries=1)
        self.assertIn('trip', content)
        self.assertNotIn('travel', content)

    def test_table_audio_controls_are_inserted_only_for_table_forms(self):
        markup = '<div class="ordbank-table desktop"><table><tr><td><div><span>et hus</span><a class="tts-btn">Play</a></div></td></tr></table></div><p>et hus</p>'
        rendered = render_lexin_entry(markup, table_sounds={'et hus': 'table.mp3'})
        self.assertEqual(rendered.count('<audio'), 1)
        self.assertEqual(rendered.count('class="lexin-form-play"'), 1)
        self.assertNotIn('controls', rendered)
        self.assertIn('src="table.mp3"', rendered)
        self.assertNotIn('autoplay', rendered)
        self.assertNotIn('tts-btn', rendered)
        self.assertNotIn('<audio', render_lexin_entry(markup))

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

    def test_nynorsk_uses_nn_lemma_and_correct_route(self):
        page = Mock()
        entries = page.locator.return_value
        entries.count.return_value = 1
        candidate = entries.nth.return_value
        lemma = candidate.locator.return_value
        lemma.count.return_value = 1
        lemma.first.locator.return_value.count.return_value = 1
        lemma.first.locator.return_value.all_text_contents.return_value = ['hus']
        candidate.inner_html.return_value = '<li><dd lang="nn">hus</dd></li>'
        content, sound = scrape_and_process_lexin(
            'hus', 1, page, variant='nynorsk', download_audio=False, verbose=False)
        self.assertIn('message.nynorsk-english?q=hus', page.goto.call_args.args[0])
        candidate.locator.assert_called_with('dd[data-type="LEM"][lang="nn"]')
        self.assertIn('Lexin · Nynorsk–English', content)
        self.assertEqual(sound, '')

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
