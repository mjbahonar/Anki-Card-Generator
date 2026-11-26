"""Stopping a run saves finished words without interrupting a browser call (which can hang Playwright)."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import main
from app.app_config import load_config

ROOT = Path(__file__).resolve().parents[1]


class StopRequestTests(unittest.TestCase):
    def test_first_signal_only_sets_the_flag_second_stops_now(self):
        stop = main.StopRequest()
        with redirect_stdout(io.StringIO()):
            stop.handle(None, None)
        self.assertTrue(stop.requested)
        with self.assertRaises(KeyboardInterrupt):
            stop.handle(None, None)
        with self.assertRaises(KeyboardInterrupt):
            stop.check()

    def test_stop_file_is_noticed_at_the_next_check(self):
        with tempfile.TemporaryDirectory() as folder:
            flag = Path(folder) / 'stop'
            with patch.dict('os.environ', {main.STOP_FILE_ENV: str(flag)}):
                stop = main.StopRequest()
            stop.check()  # No file yet: keeps going.
            flag.write_text('stop')
            with redirect_stdout(io.StringIO()) as out, self.assertRaises(KeyboardInterrupt):
                stop.check()
            self.assertIn('Stop requested', out.getvalue())

    def test_run_stops_between_words_and_saves_a_partial_file(self):
        import openpyxl
        import tomlkit
        (ROOT / 'Output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'Output') as folder:
            folder = Path(folder)
            book = openpyxl.Workbook()
            book.active.append(['Word'])
            for word in ['hus', 'bil', 'båt', 'tog']:
                book.active.append([word])
            book.save(folder / 'words.xlsx')
            doc = tomlkit.parse((ROOT / 'config.toml').read_text(encoding='utf-8'))
            doc['input'].update(file='words.xlsx', sheet=0, header=True, word_column=0, max_words=0, order='excel')
            for key in ('first_row', 'last_row'):
                doc['input'][key] = 0
            doc['output']['formats'] = ['json']
            doc['output']['directory'] = 'out'
            doc['audio']['enabled'] = False
            doc['dictionary_cache']['enabled'] = False
            doc['media']['anki_directory'] = ''
            doc['runtime']['word_delay_seconds'] = 0
            doc['runtime']['keep_awake'] = False
            doc['style']['file'] = str(ROOT / 'Styles' / 'cards.css')
            (folder / 'config.toml').write_text(tomlkit.dumps(doc), encoding='utf-8')
            config = load_config(folder / 'config.toml')
            flag = folder / 'stop'

            def lookup(name, word, number, ctx):
                if word == 'bil':
                    flag.write_text('stop')  # The GUI's Stop while "bil" is being looked up.
                return f'<p>{word}</p>'
            from contextlib import nullcontext

            class Context:
                errors, media, last_cache_hit, last_not_found = [], set(), False, False

                def issue(self, word, source, message):
                    self.errors.append({'word': word, 'source': source, 'message': str(message)})

                def source_budget(self):
                    return nullcontext()

                def close(self):
                    pass
            context = Context()
            with patch.dict('os.environ', {main.STOP_FILE_ENV: str(flag)}), \
                    patch('main.dictionary_content', side_effect=lookup), redirect_stdout(io.StringIO()) as out:
                code = main.run(config, context_factory=lambda cfg: context)
            self.assertEqual(code, 2)
            self.assertIn('PARTIAL', out.getvalue())
            saved = list((folder / 'out').glob('*_partial.json'))
            self.assertEqual(len(saved), 1)
            words = [row['Words'] for row in json.loads(saved[0].read_text(encoding='utf-8'))['words']]
            self.assertEqual(words, ['hus', 'bil'])  # "bil" finished its step; "båt" was never started.


class GuiStopTests(unittest.TestCase):
    def test_stop_writes_the_stop_file_then_kills_on_second_press(self):
        from app.gui.server import GuiApp, Job
        with tempfile.TemporaryDirectory() as folder:
            app = GuiApp(ROOT / 'config.toml', ROOT / 'main.py')
            job = Job('run', Mock())
            job.stop_file = Path(folder) / 'stop'
            app.job = job
            self.assertTrue(app.stop())
            self.assertTrue(job.stop_file.exists())
            job.process.send_signal.assert_not_called()
            job.process.kill.assert_not_called()
            self.assertTrue(app.stop())
            job.process.kill.assert_called_once()

    def test_jobs_without_a_stop_file_still_get_the_console_signal(self):
        import signal
        from app.gui.server import GuiApp, Job
        app = GuiApp(ROOT / 'config.toml', ROOT / 'main.py')
        app.job = Job('run', Mock())  # As subclasses that start the process themselves create it.
        self.assertTrue(app.stop())
        expected = signal.CTRL_BREAK_EVENT if hasattr(signal, 'CTRL_BREAK_EVENT') else signal.SIGINT
        app.job.process.send_signal.assert_called_once_with(expected)


if __name__ == '__main__':
    unittest.main()
