"""input.first_row / input.last_row: an Excel row range that stops the run when it is wrong."""
import copy
from pathlib import Path
import tempfile
import tomllib
import unittest

import openpyxl

from app.app_config import Config, ConfigError, load_config
from app.exercises import read_records

ROOT = Path(__file__).resolve().parents[1]


class InputRangeTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'Output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'Output')
        folder = Path(self.temp.name)
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(['Word'])
        for word in ['hus', 'bil', '', 'gå', 'få', 'rett']:  # Rows 2-7; row 4 is empty.
            sheet.append([word])
        book.save(folder / 'words.xlsx')
        self.data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        self.data['input'].update(file=str(folder / 'words.xlsx'), sheet=0, header=True, word_column=0,
                                  deduplicate=True, max_words=0, order='excel')
        self.data['input'].pop('first_row', None)
        self.data['input'].pop('last_row', None)
        self.config_path = folder / 'config.toml'

    def tearDown(self):
        self.temp.cleanup()

    def words(self, **settings):
        data = copy.deepcopy(self.data)
        data['input'].update(settings)
        return [(r['InputRow'], r['Words']) for r in read_records(Config(self.config_path, data))[0]]

    def test_range_uses_excel_row_numbers_and_zero_means_no_limit(self):
        self.assertEqual(self.words(), [(2, 'hus'), (3, 'bil'), (5, 'gå'), (6, 'få'), (7, 'rett')])
        self.assertEqual(self.words(first_row=3, last_row=5), [(3, 'bil'), (5, 'gå')])
        self.assertEqual(self.words(first_row=6), [(6, 'få'), (7, 'rett')])
        self.assertEqual(self.words(last_row=3), [(2, 'hus'), (3, 'bil')])
        self.assertEqual(self.words(first_row=3, max_words=2), [(3, 'bil'), (5, 'gå')])

    def test_range_without_words_stops_with_the_last_used_row(self):
        with self.assertRaisesRegex(ConfigError, 'No words in Excel rows 50–end.*row 7'):
            self.words(first_row=50)
        with self.assertRaisesRegex(ConfigError, 'No words in Excel rows 4–4'):
            self.words(first_row=4, last_row=4)

    def test_loader_rejects_reversed_or_negative_ranges_and_keeps_old_configs_valid(self):
        import tomlkit
        base = (ROOT / 'config.toml').read_text(encoding='utf-8')
        for settings, valid in [({}, True), ({'first_row': 2, 'last_row': 9}, True), ({'first_row': 9, 'last_row': 2}, False),
                                ({'first_row': -1}, False), ({'last_row': 1.5}, False)]:
            doc = tomlkit.parse(base)
            for key in ('first_row', 'last_row'):
                if key in doc['input']:
                    del doc['input'][key]
            for key, value in settings.items():
                doc['input'][key] = value
            self.config_path.write_text(tomlkit.dumps(doc), encoding='utf-8')
            with self.subTest(settings=settings):
                if valid:
                    load_config(self.config_path, check_files=False)
                else:
                    with self.assertRaises(ConfigError):
                        load_config(self.config_path, check_files=False)


if __name__ == '__main__':
    unittest.main()
