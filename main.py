"""Version 4. Edit config.toml, then run python main.py."""
import argparse
from contextlib import nullcontext
from datetime import datetime
import html
import json
from pathlib import Path
import sys
import time

from anki_exporter import display_sources, generate_anki_package, info_html, row_back
from app_config import ConfigError, load_config
from sources import SOURCE_SPECS, SourceContext, dictionary_content, select_audio
from lexin_scraper import normalize_headword
from console_report import ConsoleReport, concise

VERSION = '5.1.0'


def read_words(config):
    import pandas as pd
    settings = config.section('input')
    try:
        frame = pd.read_excel(config.resolve(settings['file']), sheet_name=settings['sheet'],
                              header=0 if settings['header'] else None)
        column = settings['word_column']
        series = frame.iloc[:, column] if type(column) is int else frame[column]
    except Exception as exc:
        raise ConfigError(f'Cannot read input sheet/word column: {exc}') from exc
    words, seen = [], set()
    for value in series.dropna():
        word = str(value).strip()
        if not word:
            continue
        key = normalize_headword(word)
        if settings['deduplicate'] and key in seen:
            continue
        seen.add(key)
        words.append(word)
        if settings['max_words'] and len(words) >= settings['max_words']:
            break
    if not words:
        raise ConfigError('The selected sheet/column contains no words')
    return words


def html_preview(rows, config):
    css = config.resolve(config.section('style')['file']).read_text(encoding='utf-8')
    for font in (config.path.parent / 'fonts').glob('*'):
        if font.is_file():
            css = css.replace(f'url("{font.name}")', f'url("{font.resolve().as_uri()}")')
    cards = []
    audio_dir = config.resolve(config.section('audio')['directory'])
    for row in rows:
        front = html.escape(row['Words'])
        if row['Sound']:
            url = html.escape((audio_dir / row['Sound'][7:-1]).as_uri(), quote=True)
            front += f' <audio controls preload="none" src="{url}"></audio>'
        cards.append('<article class="preview-card"><div class="front">' + front
                     + '</div><hr>' + row_back(row, config) + '</article>')
    output = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    output += '<title>' + html.escape(config.section('anki')['deck_name']) + '</title><style>' + css + '</style><body>'
    import re
    body = re.sub(r'(<img[^>]+src=["\'])([^/"\']+)(["\'])', r'\1media/\2\3', ''.join(cards))
    return output + body + '</body></html>'


def export_outputs(rows, config, stem, context, recovery=False):
    import pandas as pd
    output = config.resolve(config.section('output')['directory'])
    columns = ['Words', 'FrontField', 'Sound', *display_sources(config), 'Info']
    frame = pd.DataFrame(rows).reindex(columns=columns, fill_value='')
    formats = ['csv'] if recovery else list(dict.fromkeys(config.section('output')['formats']))
    paths, failures = [], []
    for format_name in formats:
        path, temporary = output / f'{stem}.{format_name}', output / f'{stem}.tmp.{format_name}'
        try:
            output.mkdir(parents=True, exist_ok=True)
            if format_name == 'csv':
                frame.to_csv(temporary, index=False, encoding='utf-8-sig')
            elif format_name == 'xlsx':
                frame.to_excel(temporary, index=False)
            elif format_name == 'json':
                temporary.write_text(json.dumps({'version': VERSION, 'language': config.section('language'),
                                                'errors': context.errors, 'words': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
            elif format_name == 'html':
                temporary.write_text(html_preview(rows, config), encoding='utf-8')
            elif format_name == 'apkg':
                fonts = list((config.path.parent / 'fonts').glob('*'))
                generate_anki_package(rows, temporary, config, context.media | set(fonts))
            temporary.replace(path)
            paths.append(path)
        except Exception as exc:
            failures.append(f'{format_name}: {exc}')
            print(f'  FAIL export {format_name}: {concise(exc)}', flush=True)
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
    return paths, failures


def run(config, context_factory=SourceContext):
    words, active = read_words(config), display_sources(config)
    requested = [name for name, options in config.section('sources').items() if options['enabled']]
    skipped = [name for name in requested if name not in active]
    print(f'Anki Card Generator V{VERSION} | {config.section("language")["source"]} | {len(words)} words', flush=True)
    print('Sources: ' + (', '.join(active) or 'none'), flush=True)
    limit = config.section('runtime').get('source_timeout_seconds', 30)
    print(f'Source time budget: {limit}s' if limit else 'Source time budget: disabled', flush=True)
    if skipped:
        print('Skipped sources incompatible with this language: ' + ', '.join(skipped), flush=True)
    stem = config.section('output')['filename_prefix'] + '_' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')
    rows, context = [], context_factory(config)
    report = ConsoleReport(active, len(words))
    recovery_failures = []
    keep_awake = nullcontext()
    if config.section('runtime')['keep_awake']:
        try:
            from wakepy import keep
            keep_awake = keep.running(on_fail='pass')
        except Exception as exc:
            print(f'Keep-awake unavailable: {exc}', flush=True)
    interrupted = False
    fatal = False
    try:
        with keep_awake:
            for number, word in enumerate(words, 1):
                print(f'\n[{number}/{len(words)}] {word}', flush=True)
                row = {'Words': word, **{name: '' for name in SOURCE_SPECS}, 'Info': info_html(config)}
                rows.append(row)
                for name in active:
                    started = time.monotonic()
                    previous = len(context.errors)
                    try:
                        with context.source_budget():
                            row[name] = dictionary_content(name, word, number, context)
                        if not row[name]:
                            if len(context.errors) == previous:
                                context.issue(word, name, 'No exact entry/content received')
                            failed = any(error['source'] == name for error in context.errors[previous:]
                                         if error['message'] != 'No exact entry/content received')
                            report.source(name, 'FAIL' if failed else 'EMPTY', started,
                                          context.errors[-1]['message'])
                        else:
                            report.source(name, 'OK', started)
                            for issue in context.errors[previous:]:
                                print(f'  WARN  {issue["source"]}: {concise(issue["message"])}', flush=True)
                    except Exception as exc:
                        context.issue(word, name, exc)
                        row[name] = ''
                        report.source(name, 'FAIL', started, context.errors[-1]['message'])
                previous = len(context.errors)
                try:
                    row['Sound'] = select_audio(word, number, context)
                except Exception as exc:
                    context.issue(word, 'audio', exc)
                    row['Sound'] = ''
                print('  AUDIO ' + (row['Sound'][7:-1] if row['Sound'] else
                      'unavailable' if config.section('audio')['enabled'] else 'disabled'), flush=True)
                for error in context.errors[previous:]:
                    print(f'  WARN  {error["source"]}: {concise(error["message"])}', flush=True)
                row['FrontField'] = html.escape(word) + (' ' + row['Sound'] if row['Sound'] else '')
                every = config.section('output')['autosave_every']
                if every and number % every == 0:
                    _, autosave_failures = export_outputs(rows, config, stem + '_recovery', context, recovery=True)
                    recovery_failures.extend(autosave_failures)
                if number < len(words):
                    time.sleep(config.section('runtime')['word_delay_seconds'])
    except KeyboardInterrupt:
        interrupted = True
        print('Interrupted; saving completed and partial words.', flush=True)
    except Exception as exc:
        fatal = True
        context.issue('', 'runtime', exc)
        print('Run stopped; saving available words: ' + concise(exc), flush=True)
    finally:
        try:
            context.close()
        except Exception as exc:
            context.issue('', 'cleanup', exc)
    for row in rows:
        row.setdefault('Sound', '')
        row.setdefault('FrontField', html.escape(row['Words']))
    if not rows:
        report.finish(rows, context.errors, [], ['No words saved'], partial=interrupted or fatal)
        return 2 if interrupted else 1
    paths, failures = export_outputs(rows, config, stem + ('_partial' if interrupted or fatal else ''), context)
    failures.extend(recovery_failures)
    if context.errors:
        error_path = config.resolve(config.section('output')['directory']) / f'{stem}_errors.json'
        try:
            error_path.write_text(json.dumps(context.errors, ensure_ascii=False, indent=2), encoding='utf-8')
            paths.append(error_path)
        except Exception as exc:
            failures.append('Error report: ' + str(exc))
    report.finish(rows, context.errors, paths, failures, partial=interrupted or fatal)
    return 2 if interrupted else (1 if failures or fatal else 0)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Unified Anki Card Generator')
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.toml'))
    parser.add_argument('--check', action='store_true', help='Validate config and Excel without fetching sources')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.check:
            words = read_words(config)
            print(f'Configuration OK: {len(words)} words. Sources: {", ".join(display_sources(config))}')
            return 0
        return run(config)
    except (ConfigError, OSError, ValueError, ImportError) as exc:
        print(f'Cannot run: {exc}. Check config.toml and requirements.txt.', file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'Run failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
