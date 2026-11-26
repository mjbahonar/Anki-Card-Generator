"""Readable progress and final run summary, without external dependencies."""
from collections import Counter
from datetime import datetime
import time


def concise(message):
    text = str(message).strip()
    if 'Source time limit exceeded' in text:
        return 'Source time limit exceeded; skipped'
    if 'ERR_NAME_NOT_RESOLVED' in text:
        return 'DNS lookup failed; source address unavailable'
    if 'Timeout' in text or 'timed out' in text:
        return 'Request timed out'
    return (text.splitlines() or ['Unknown error'])[0][:180]


class ConsoleReport:
    def __init__(self, sources, total):
        self.started = time.monotonic()
        self.started_at = datetime.now()
        self.total = total
        self.counts = {source: Counter() for source in sources}
        self.words = []  # One record per processed input row, for the PDF/PNG run report.

    def word(self, number, word, kind):
        self.words.append({'number': number, 'word': word, 'kind': kind, 'sources': {}, 'audio': False,
                           'saved': True, 'note': ''})

    def audio(self, available):
        if self.words:
            self.words[-1]['audio'] = bool(available)

    def skip(self, reason):
        if self.words:
            self.words[-1].update(saved=False, note=reason)

    def source(self, name, status, started, detail='', cached=False, not_found=False):
        self.counts[name][status] += 1
        seconds = time.monotonic() - started
        if self.words:
            self.words[-1]['sources'][name] = {'status': status, 'seconds': round(seconds, 1),
                                               'detail': concise(detail) if detail else '',
                                               'cached': bool(cached), 'not_found': bool(not_found)}
        suffix = ' | ' + concise(detail) if detail else ''
        print(f'  {status:<5} {name:<20} {seconds:5.1f}s{suffix}', flush=True)

    def status(self, rows, errors, failures, partial=False):
        return ('PARTIAL' if partial else 'FAILED' if failures or not rows
                else 'COMPLETED WITH WARNINGS' if errors else 'COMPLETED')

    def finish(self, rows, errors, paths, failures, partial=False):
        print('\n' + '=' * 64)
        print('FINAL REPORT' + (' | PARTIAL RUN' if partial else ''))
        print(f'Words saved: {len(rows)}/{self.total} | Time: {time.monotonic() - self.started:.1f}s')
        print(f'{"Source":<22} {"OK":>6} {"Empty":>6} {"Failed":>6}')
        for name, counts in self.counts.items():
            print(f'{name:<22} {counts["OK"]:>6} {counts["EMPTY"]:>6} {counts["FAIL"]:>6}')
        audio = sum(bool(row.get('Sound')) for row in rows)
        print(f'Audio: {audio} words with audio, {len(rows) - audio} without audio')
        print(f'Issues: {len(errors)} | Export/report failures: {len(failures)}')
        for path in paths:
            print(f'Saved: {path}')
        for failure in failures:
            print('FAILED: ' + concise(failure))
        print('Status: ' + ('PARTIAL' if partial else 'FAILED' if failures else 'COMPLETED WITH WARNINGS' if errors else 'COMPLETED'))
        self.elapsed = time.monotonic() - self.started
        print('=' * 64, flush=True)
