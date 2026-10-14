"""Live diagnostic, isolated from user caches: python -m tests.benchmark_lexin."""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
import tomllib
from unittest.mock import patch

from app.app_config import Config
from app.sources import SourceContext, dictionary_content
from app.lexin_scraper import download_table_audio


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='baseline')
    parser.add_argument('words', nargs='*', default=['gift', 'hund', 'bil'])
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z_-]+', args.label):
        parser.error('label must use lowercase letters, underscores or hyphens')
    root = Path(__file__).resolve().parents[1]
    output = root / 'Output'
    output.mkdir(exist_ok=True)
    with (root / 'config.toml').open('rb') as stream:
        original = tomllib.load(stream)
    results = []
    with tempfile.TemporaryDirectory(dir=output, prefix='lexin_benchmark_') as temporary:
        data = copy.deepcopy(original)
        data['dictionary_cache'] = {'enabled': True, 'path': str(Path(temporary) / 'cache.sqlite3'), 'refresh': False}
        data['audio']['directory'] = str(Path(temporary) / 'Audio')
        data['media'] = {'anki_directory': ''}
        data['audio']['copy_to'] = ''
        data['output']['directory'] = temporary
        audio = Path(data['audio']['directory'])
        audio.mkdir()
        original_config = Config(root / 'config.toml', original)
        for path in original_config.resolve(original['audio']['directory']).glob('*.mp3'):
            shutil.copyfile(path, audio / path.name)
        config = Config(root / 'config.toml', data)
        ctx = SourceContext(config)
        try:
            for number, word in enumerate(args.words, 1):
                stats = {'word': word, 'archive_seconds': 0, 'table_seconds': 0, 'fallback_seconds': 0, 'fallback_forms': [], 'requests': []}
                original_capture, original_get = ctx.capture_entry, ctx.session.get
                original_fallback = ctx.table_audio_fallback
                def capture(*args, **kwargs):
                    started = time.monotonic()
                    try:
                        return original_capture(*args, **kwargs)
                    finally:
                        stats['archive_seconds'] += time.monotonic() - started
                def get(url, *args, **kwargs):
                    started = time.monotonic()
                    try:
                        return original_get(url, *args, **kwargs)
                    finally:
                        stats['requests'].append({'url': url, 'seconds': time.monotonic() - started})
                def table(*args, **kwargs):
                    started = time.monotonic()
                    try:
                        return download_table_audio(*args, **kwargs)
                    finally:
                        stats['table_seconds'] += time.monotonic() - started
                def fallback(form, language):
                    started = time.monotonic()
                    stats['fallback_forms'].append(form)
                    try:
                        return original_fallback(form, language)
                    finally:
                        stats['fallback_seconds'] += time.monotonic() - started
                print('Fetching', word, flush=True)
                started = time.monotonic()
                errors = len(ctx.errors)
                try:
                    with (patch.object(ctx, 'capture_entry', side_effect=capture),
                          patch.object(ctx.session, 'get', side_effect=get),
                          patch.object(ctx, 'table_audio_fallback', side_effect=fallback),
                          patch('app.lexin_scraper.download_table_audio', side_effect=table)):
                        with ctx.source_budget():
                            content = dictionary_content('lexin', word, number, ctx)
                    stats['entries'] = content.count('gt-container lexin-container')
                except Exception as exc:
                    stats['error'] = str(exc)
                stats['seconds'] = time.monotonic() - started
                stats['issues'] = ctx.errors[errors:]
                started = time.monotonic()
                try:
                    with ctx.source_budget():
                        dictionary_content('lexin', word, number, ctx)
                    stats['repeat_cache_hit'] = ctx.last_cache_hit
                except Exception as exc:
                    stats['repeat_error'] = str(exc)
                stats['repeat_seconds'] = time.monotonic() - started
                results.append(stats)
                print(json.dumps(stats, ensure_ascii=False), flush=True)
        finally:
            ctx.close()
    report = output / ('lexin_benchmark_' + args.label + '.json')
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved', report, flush=True)


if __name__ == '__main__':
    main()
