"""Mixed Excel -> Anki integration and exercise privacy/identity checks."""
import copy
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout, closing
from unittest.mock import patch
import zipfile

import pandas as pd
from app_config import Config, ConfigError
from exercises import read_records, render_exercise, exercise_audio, validate_cards, complete_gap
from anki_exporter import generate_anki_package, FIELDS, write_import_csv
from main import run
from sources import SourceContext

ROOT = Path(__file__).resolve().parent


class ExerciseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        data['practice'].update(question_language='en', answer_language='no')
        data['input']['file'] = str(self.directory / 'input.xlsx')
        data['output']['directory'] = str(self.directory)
        data['audio']['directory'] = str(self.directory / 'Audio')
        data['style']['file'] = str(ROOT / 'Styles/cards.css')
        data['runtime'].update(keep_awake=False, word_delay_seconds=0)
        data['sources'] = {}
        self.config = Config(ROOT / 'config.toml', data)

    def sheet(self, rows):
        pd.DataFrame(rows).to_excel(self.config.section('input')['file'], header=False, index=False)

    def rendered(self, kind, question='house', answer='hus'):
        return render_exercise(dict(Kind=kind, Words=question, Answer=answer, Sound='[sound:voice.mp3]', Tags=[kind]), self.config)

    def test_optional_columns_and_tags(self):
        self.sheet([['hus'], ['bok']])
        records, skipped = read_records(self.config)
        self.assertFalse(skipped)
        self.assertEqual([r['Kind'] for r in records], ['normal', 'normal'])
        self.assertEqual(records[0]['Tags'], ['normal'])
        self.sheet([['house', 'TYPE', 'A1, daily life,type', 'hus']])
        records, _ = read_records(self.config)
        self.assertEqual(records[0]['Tags'], ['type', 'A1', 'daily_life'])

    def test_shared_media_destination_copies_audio_and_image_keeps_originals(self):
        target = self.directory / 'collection.media'
        self.config.data['media'] = {'anki_directory': str(target)}
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        for name, data in [('voice.mp3', b'ID3' + b'x' * 200), ('photo.png', b'image-data')]:
            original = self.directory / name
            original.write_bytes(data)
            context.register_media(original)
            self.assertEqual(original.read_bytes(), data)
            self.assertEqual((target / name).read_bytes(), data)
            self.assertIn(original.resolve(), context.media)
        self.assertEqual(context.register_audio(self.directory / 'voice.mp3'), '[sound:voice.mp3]')

    def test_gap_alignment_is_explicit_for_ltr_and_rtl(self):
        row = self.rendered('gap', 'Jeg [...] her.', 'bor')
        self.assertIn('style="text-align: left;"', row['FrontField'])
        self.assertIn('style="text-align: left;"', row['BackField'])
        self.config.data['practice']['answer_language'] = 'fa'
        row = self.rendered('gap', 'من [...] هستم.', 'اینجا')
        self.assertIn('style="text-align: right;"', row['FrontField'])
        self.assertIn('style="text-align: right;"', row['BackField'])

    def test_random_order_keeps_answers_and_tags_with_their_questions(self):
        self.sheet([['house', 'type', 'home', 'hus'], ['book', 'type', 'reading', 'bok']])
        self.config.section('input')['order'] = 'random'
        with patch('random.shuffle', side_effect=lambda items: items.reverse()) as shuffle:
            records, _ = read_records(self.config)
        shuffle.assert_called_once()
        self.assertEqual([(r['Words'], r['Answer']) for r in records], [('book', 'bok'), ('house', 'hus')])
        self.assertEqual(records[0]['Tags'], ['type', 'reading'])

    def test_skip_bad_rows_and_allow_optional_listen_meaning(self):
        self.sheet([['house', 'type'], ['I live here.', 'sentence'], ['[…] jente', 'gap'],
                    ['oops', 'typo'], ['hus', 'listen'], ['[…] jente', 'gap', '', 'ei']])
        records, skipped = read_records(self.config)
        self.assertEqual([r['Kind'] for r in records], ['listen', 'gap'])
        self.assertEqual([r['row'] for r in skipped], [1, 2, 3, 4])

    def test_deduplication_keeps_different_types_and_stable_answer_updates(self):
        self.sheet([['house', 'type', '', 'hus'], ['house', 'sentence', '', 'hus'], ['house', 'type', '', 'hus']])
        records, _ = read_records(self.config)
        self.assertEqual(len(records), 2)
        first = self.rendered('type')
        second = self.rendered('type', answer='updated')
        self.assertEqual(first['Identity'], second['Identity'])
        self.assertNotEqual(first['Identity'], self.rendered('sentence')['Identity'])

    def test_persian_direction_language_and_front_does_not_leak_answer(self):
        self.config.data['practice']['answer_language'] = 'fa'
        row = self.rendered('type', answer='خانه')
        self.assertIn('English → Persian', row['FrontField'])
        self.assertIn('Write the equivalent in Persian.', row['FrontField'])
        self.assertNotIn('خانه', row['FrontField'])
        self.assertNotIn('[sound:', row['FrontField'])
        self.assertIn('dir="rtl" lang="fa"', row['BackField'])
        self.assertEqual(row['AnswerDirection'], 'rtl')

    def test_listen_hides_text_and_gap_completes_sentence(self):
        row = self.rendered('listen', question='Jeg bor her.', answer='I live here.')
        self.assertNotIn('Jeg bor her.', row['FrontField'])
        self.assertIn('[sound:voice.mp3]', row['FrontField'])
        self.assertIn('Jeg bor her.', row['BackField'])
        gap = self.rendered('gap', 'Ken [...] 23 år gammel.', 'er')
        from bs4 import BeautifulSoup
        self.assertIn('Ken er 23 år gammel.', BeautifulSoup(gap['BackField'], 'html.parser').get_text())

    def test_multi_gap_replaces_in_order_and_preserves_lines(self):
        question = 'Jeg [...] Ken.\nJeg […] fra England.'
        answer = 'heter\nkommer'
        self.assertEqual(complete_gap(question, answer), 'Jeg heter Ken.\nJeg kommer fra England.')
        row = self.rendered('gap', question, answer)
        self.assertEqual(row['FrontField'].count('class="exercise-gap exercise-gap-entry"'), 2)
        self.assertEqual(row['FrontField'].count('<input'), 2)
        self.assertIn('aria-label="Answer 2"', row['FrontField'])
        self.assertEqual(row['BackField'].count('class="exercise-gap-solution"'), 2)
        self.assertIn('<br>', row['FrontField'])
        self.assertIn('<br>', row['BackField'])
        self.assertIn('exercise-answer exercise-gap-text', row['BackField'])
        self.assertNotIn('heter', row['FrontField'])
        self.assertNotIn('kommer', row['FrontField'])

    def test_speaking_answer_has_no_sample_disclaimer(self):
        row = self.rendered('sentence', 'I live here.', 'Jeg bor her.')
        self.assertIn('Jeg bor her.', row['BackField'])
        self.assertNotIn('Sample answer', row['BackField'])

    def test_multi_gap_invalid_counts_and_empty_answers_are_skipped(self):
        self.sheet([['[...] and […]', 'gap', '', 'one'],
                    ['[...] and [...] and [...]', 'gap', '', 'one\n\nthree'],
                    ['[...] and […]', 'gap', '', 'one\ntwo']])
        records, skipped = read_records(self.config)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(skipped), 2)
        self.assertIn('2 blanks but 1 answer lines', skipped[0]['message'])
        self.assertIn('must not be blank', skipped[1]['message'])

    def test_multi_gap_answers_are_escaped_and_not_regex_replacements(self):
        self.assertEqual(complete_gap('[...] […]', r'\1' + '\n<b>'), r'\1 <b>')
        markup = complete_gap('[...] […]', r'\1' + '\n<b>', markup=True)
        self.assertIn('&lt;b&gt;', markup)
        self.assertNotIn('<b>', markup)

    def test_tts_uses_answer_language_and_reuses_cache(self):
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        with patch('gtts.gTTS') as tts:
            tts.return_value.write_to_fp.side_effect = lambda b: b.write(b'ID3' + b'x' * 200)
            first = exercise_audio('خانه', 'fa', context)
            self.assertEqual(first, exercise_audio('خانه', 'fa', context))
            tts.assert_called_once()
            self.assertEqual(tts.call_args.kwargs['lang'], 'fa')
            exercise_audio('hus', 'nn', context)
            self.assertEqual(tts.call_args.kwargs['lang'], 'no')

    def test_mixed_package_schema_templates_tags_and_media(self):
        self.config.data['practice']['answer_language'] = 'fa'
        rows = [dict(Words='bok', FrontField='bok', Tags=['normal']),
                self.rendered('type', answer='خانه'), self.rendered('sentence'),
                self.rendered('gap', '[...] jente', 'ei'), self.rendered('listen')]
        voice = self.directory / 'voice.mp3'
        voice.write_bytes(b'ID3' + b'x' * 200)
        table_voice = self.directory / 'table.mp3'
        table_voice.write_bytes(b'ID3' + b'y' * 200)
        rows[0]['lexin'] = '<audio controls src="table.mp3"></audio>'
        package = self.directory / 'mixed.apkg'
        generate_anki_package(rows, package, self.config, {voice, table_voice})
        with zipfile.ZipFile(package) as archive:
            database = self.directory / 'collection.anki2'
            database.write_bytes(archive.read('collection.anki2'))
            self.assertIn('voice.mp3', json.loads(archive.read('media')).values())
            self.assertIn('table.mp3', json.loads(archive.read('media')).values())
        with closing(sqlite3.connect(database)) as db:
            models = json.loads(db.execute('select models from col').fetchone()[0])
            notes = db.execute('select mid,tags from notes').fetchall()
            self.assertEqual(len(notes), 5)
            self.assertEqual(len(models), 5)
            self.assertEqual([f['name'] for f in models[str(self.config.section('anki')['model_id'])]['flds']], FIELDS)
            typed = next(m for m in models.values() if m['name'].endswith('type'))
            self.assertIn('{{type:Answer}}', typed['tmpls'][0]['qfmt'])
            self.assertIn('data-answer-direction', typed['tmpls'][0]['qfmt'])
            self.assertIn('data-answer-direction="rtl"', rows[1]['FrontField'])
            self.assertTrue(typed['tmpls'][0]['afmt'].endswith('{{#Info}}{{Info}}{{/Info}}'))
            self.assertTrue(all(tags.strip() for _, tags in notes))

    def test_import_csv_has_note_types_and_space_separated_tags(self):
        row = self.rendered('sentence', 'Hello, friend.', 'Hei, venn.')
        row['Tags'] = ['sentence', 'A1']
        path = self.directory / 'import.csv'
        write_import_csv([row], path, self.config)
        text = path.read_text(encoding='utf-8-sig')
        self.assertIn('#notetype column:1', text)
        parsed = list(csv.reader(line for line in text.splitlines() if not line.startswith('#')))
        self.assertEqual(parsed[0][0], 'Vocabulary Exercise · sentence')
        self.assertEqual(parsed[0][1], 'sentence A1')
        self.assertEqual(parsed[0][4], 'Hello, friend.')
        from anki_exporter import note_guid
        self.assertEqual(parsed[0][2], note_guid(row, self.config))
        self.assertIn('#guid column:3', text)

    def test_run_skips_missing_answers_and_no_audio_listen(self):
        self.sheet([['house', 'type', '', 'hus'], ['missing', 'sentence'], ['Jeg bor her.', 'listen']])
        self.config.section('audio')['enabled'] = False
        self.config.section('output')['formats'] = ['json', 'csv', 'apkg', 'html']
        with patch('main.dictionary_content') as dictionary, redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.config), 0)
        dictionary.assert_not_called()
        data = json.loads(next(p for p in self.directory.glob('words*.json') if not p.name.endswith('_errors.json')).read_text(encoding='utf-8'))
        self.assertEqual(len(data['words']), 1)
        self.assertEqual(len(data['errors']), 2)
        self.assertTrue(list(self.directory.glob('*_anki.csv')))

    def test_invalid_config_fails_before_network_work(self):
        for update in ({'audio': 'yes'}, {'instruction': '{unknown}'}, {'tag': 'two tags'}):
            data = copy.deepcopy(self.config.data)
            data['cards']['type'].update(update)
            with self.assertRaises(ConfigError):
                validate_cards(data)

    def test_norwegian_audio_cache_follows_explicit_variant_and_tts_support(self):
        self.config.data['language']['source'] = 'nn'
        self.config.data['sources']['lexin'] = {'enabled': True, 'variant': 'bokmal'}
        context = SourceContext(self.config)
        self.addCleanup(context.close)
        self.assertEqual(context.audio_language('lexin'), 'no')
        self.assertEqual(context.audio_language('google_tts'), 'no')
        self.config.data['sources']['lexin']['variant'] = 'both'
        self.assertEqual(context.audio_language('lexin'), 'nn')

    def test_all_invalid_rows_fail_check(self):
        from main import main
        self.sheet([['bad', 'type', '', '']])
        with patch('main.load_config', return_value=self.config), redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--check']), 1)

    def test_typing_multiline_answer_is_skipped(self):
        self.sheet([['house', 'type', '', 'hus\nhuset']])
        records, skipped = read_records(self.config)
        self.assertFalse(records)
        self.assertIn('single-line answer', skipped[0]['message'])


if __name__ == '__main__':
    unittest.main()
