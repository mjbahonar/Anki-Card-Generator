"""Run report: per-word outcomes, indirect (inflected-form) results, HTML content and PDF/PNG files."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import time
import tomllib
import unittest

from app.app_config import Config
from app.console_report import ConsoleReport
from app.run_report import build_html, summarize, word_outcomes, write_report

ROOT = Path(__file__).resolve().parents[1]
NOTE = '<div class="lexin-form-note">gikk → <b>gå</b></div><ul>go</ul>'


def sample_report():
    report = ConsoleReport(['lexin', 'oxford'], 5)
    with redirect_stdout(io.StringIO()):
        report.word(1, 'hus', 'normal')
        report.source('lexin', 'OK', time.monotonic(), cached=True)
        report.source('oxford', 'FAIL', time.monotonic(), 'Request timed out')
        report.audio('[sound:hus.mp3]')
        report.word(2, 'gikk', 'normal')
        report.source('lexin', 'OK', time.monotonic())
        report.source('oxford', 'EMPTY', time.monotonic(), 'No exact entry/content received')
        report.word(3, 'xqz', 'normal')
        report.source('lexin', 'EMPTY', time.monotonic(), 'No exact entry/content received', cached=True, not_found=True)
        report.source('oxford', 'EMPTY', time.monotonic(), 'No exact entry/content received', not_found=True)
        report.word(4, 'Jeg [...] her', 'gap')
        report.audio('')
        report.word(5, 'Hør', 'listen')
        report.skip('Listening card has no audio')
    rows = [{'Words': 'hus', 'Kind': 'normal', 'lexin': '<ul>house</ul>'},
            {'Words': 'gikk', 'Kind': 'normal', 'lexin': NOTE},
            {'Words': 'xqz', 'Kind': 'normal', 'lexin': ''},
            {'Words': 'Jeg [...] her', 'Kind': 'gap'}]
    return report, rows


class RunReportTests(unittest.TestCase):
    def setUp(self):
        self.data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        self.config = Config(ROOT / 'config.toml', self.data)

    def test_outcomes_tell_direct_indirect_not_found_and_failed_apart(self):
        report, rows = sample_report()
        outcomes = word_outcomes(report.words, rows, ['lexin', 'oxford'])
        cells = {o['word']: {k: v['state'] for k, v in o['cells'].items()} for o in outcomes}
        self.assertEqual(cells['hus'], {'lexin': 'found', 'oxford': 'failed'})
        self.assertEqual(cells['gikk'], {'lexin': 'form', 'oxford': 'empty'})
        self.assertEqual(outcomes[1]['cells']['lexin']['bases'], ['gå'])
        self.assertEqual(cells['xqz'], {'lexin': 'not_found', 'oxford': 'not_found'})
        summary = summarize(outcomes, ['lexin', 'oxford'], [{'row': 9, 'message': 'bad'}],
                            [{'word': 'hus', 'source': 'oxford', 'message': 'Request timed out'},
                             {'word': 'gikk', 'source': 'oxford', 'message': 'No exact entry/content received'}])
        self.assertEqual((summary['processed'], summary['normal'], summary['exercises']), (5, 3, 2))
        self.assertEqual((summary['found'], summary['via_form'], summary['not_found'], summary['failed']), (2, 1, 1, 1))
        self.assertEqual((summary['audio'], summary['saved'], summary['skipped_rows']), (1, 4, 1))
        self.assertEqual(len(summary['issues']), 1)  # "No exact entry" is expected, not an issue.
        self.assertEqual(summary['per_source']['lexin'], {'found': 1, 'form': 1, 'not_found': 1, 'empty': 0,
                                                          'failed': 0, 'cached': 2, 'total': 3})

    def test_html_has_summary_every_word_and_every_setting(self):
        report, rows = sample_report()
        outcomes = word_outcomes(report.words, rows, ['lexin', 'oxford'])
        summary = summarize(outcomes, ['lexin', 'oxford'], [], [])
        page = build_html(self.config, summary, outcomes, ['lexin', 'oxford'], 'COMPLETED WITH WARNINGS',
                          report.started_at, 75, ['Output/x.apkg'], [])
        for text in ('Run report', 'Completed with warnings', '1 min 15 s', 'x.apkg', '↪ gå', 'Hør',
                     'Listening card has no audio', '[sources.lexin]', 'form_entries', '[anki]',
                     self.data['anki']['deck_name']):
            self.assertIn(text, page)
        self.assertNotIn('<script', page)

    def test_report_format_is_accepted_and_skipped_by_plain_exports(self):
        import tomlkit
        from app.app_config import ConfigError, load_config
        with tempfile.TemporaryDirectory(dir=ROOT / 'Output') as folder:
            path = Path(folder) / 'config.toml'
            doc = tomlkit.parse((ROOT / 'config.toml').read_text(encoding='utf-8'))
            doc['output']['formats'] = ['html', 'report']
            path.write_text(tomlkit.dumps(doc), encoding='utf-8')
            self.assertIn('report', load_config(path, check_files=False).data['output']['formats'])
            doc['output']['formats'] = ['pdf']
            path.write_text(tomlkit.dumps(doc), encoding='utf-8')
            with self.assertRaises(ConfigError):
                load_config(path, check_files=False)

    def test_pdf_and_png_are_written(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                playwright.chromium.launch().close()
        except Exception as exc:  # pragma: no cover - machines without the browser
            self.skipTest(f'Chromium unavailable: {exc}')
        report, rows = sample_report()
        (ROOT / 'Output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'Output') as folder:
            self.data['output']['directory'] = folder
            paths = write_report(self.config, report, rows, [], [], [], [], False, 'run', ['lexin', 'oxford'])
            pdf, png = paths
            self.assertEqual(pdf.read_bytes()[:5], b'%PDF-')
            self.assertGreater(pdf.stat().st_size, 10_000)
            self.assertEqual(png.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')


if __name__ == '__main__':
    unittest.main()
