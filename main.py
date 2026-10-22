"""Unified application. Edit config.toml, then run python main.py."""
import argparse
from contextlib import nullcontext
from datetime import datetime
import html
import json
from pathlib import Path
import sys
import time

from app.anki_exporter import display_sources, generate_anki_package, info_html, row_back
from app.app_config import ConfigError, load_config
from app.sources import SOURCE_SPECS, SourceContext, dictionary_content, select_audio
from app.console_report import ConsoleReport, concise
from app.exercises import read_records, options, language_settings, exercise_audio, render_exercise, direction, complete_gap
from app.anki_exporter import write_import_csv

VERSION = '5.3.0'


def read_words(config):
    return [record['Words'] for record in read_records(config)[0]]


def html_preview(rows, config):
    css = config.resolve(config.section('style')['file']).read_text(encoding='utf-8')
    for font in (config.path.parent / 'fonts').glob('*'):
        if font.is_file():
            css = css.replace(f'url("{font.name}")', f'url("{font.resolve().as_uri()}")')
    cards = []
    audio_dir = config.resolve(config.section('audio')['directory'])
    for row in rows:
        front = row.get('FrontField', html.escape(row['Words']))
        if row.get('Kind') == 'type':
            front += '<div class="exercise-type-answer" dir="' + row['AnswerDirection'] + '"><input aria-label="Your answer" placeholder="Your answer"></div>'
        front_class = 'front' if row.get('Kind', 'normal') == 'normal' else 'exercise-preview-front'
        cards.append('<article class="preview-card"><div class="' + front_class + '">' + front
                     + '</div><hr>' + row_back(row, config) + '</article>')
    output = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    output += '<title>' + html.escape(config.section('anki')['deck_name']) + '</title><style>' + css + '</style><body>'
    import re
    body = re.sub(r'(<img[^>]+src=["\'])([^/"\']+)(["\'])', r'\1media/\2\3', ''.join(cards))
    body = re.sub(r'(<audio[^>]+src=["\'])([^/"\']+)(["\'])', lambda m: m[1] + html.escape((audio_dir / m[2]).as_uri(), quote=True) + m[3], body)
    body = re.sub(r'\[sound:([^\]]+)\]', lambda m: '<audio controls preload="none" src="' + html.escape((audio_dir / m[1]).as_uri(), quote=True) + '"></audio>', body)
    theme_script = '<script>const appearance=matchMedia("(prefers-color-scheme: dark)");function setTheme(){document.documentElement.dataset.theme=appearance.matches?"dark":"light";document.body.style.background=appearance.matches?"#202124":"#ffffff";}setTheme();appearance.addEventListener("change",setTheme);</script>'
    return output + body + theme_script + '</body></html>'


def export_outputs(rows, config, stem, context, recovery=False):
    import pandas as pd
    output = config.resolve(config.section('output')['directory'])
    columns = ['Words', 'Kind', 'Answer', 'Tags', 'Meaning', 'FrontField', 'BackField', 'Sound', *display_sources(config), 'Info']
    frame = pd.DataFrame(rows).reindex(columns=columns, fill_value='')
    frame['Tags'] = [' '.join(row.get('Tags', [])) for row in rows]
    formats = ['csv'] if recovery else list(dict.fromkeys(config.section('output')['formats']))
    paths, failures = [], []
    for format_name in formats:
        path, temporary = output / f'{stem}.{format_name}', output / f'{stem}.tmp.{format_name}'
        import_temp = output / f'{stem}_anki.tmp.csv'
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
            if format_name == 'csv' and not recovery:
                import_path = output / f'{stem}_anki.csv'
                write_import_csv(rows, import_temp, config)
                import_temp.replace(import_path)
                paths.append(import_path)
        except Exception as exc:
            failures.append(f'{format_name}: {exc}')
            print(f'  FAIL export {format_name}: {concise(exc)}', flush=True)
        finally:
            for leftover in (temporary, import_temp):
                if leftover.exists():
                    try:
                        leftover.unlink()
                    except OSError:
                        pass
    return paths, failures


def run(config, context_factory=SourceContext):
    records, input_skips = read_records(config)
    words, active = [record['Words'] for record in records], display_sources(config)
    for skipped_row in input_skips:
        print(f"SKIP Excel row {skipped_row['row']}: {skipped_row['message']}", flush=True)
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
    context.errors.extend(input_skips)
    report = ConsoleReport(active, len(words) + len(input_skips))
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
            for number, record in enumerate(records, 1):
                word = record['Words']
                print(f'\n[{number}/{len(words)}] {word}', flush=True)
                row = {**record, **{name: '' for name in SOURCE_SPECS}, 'Info': info_html(config)}
                if row['Kind'] != 'normal':
                    previous = len(context.errors)
                    row['Sound'] = ''
                    if config.section('audio')['enabled'] and options(config, row['Kind'])['audio']:
                        text = word if row['Kind'] == 'listen' else row['Answer']
                        if row['Kind'] == 'gap':
                            text = complete_gap(word, row['Answer'])
                        try:
                            with context.source_budget():
                                row['Sound'] = exercise_audio(text, language_settings(config)[1], context)
                        except Exception as exc:
                            context.issue(word, 'google_tts', exc)
                    print('  AUDIO ' + (row['Sound'][7:-1] if row['Sound'] else 'unavailable or disabled'), flush=True)
                    for issue in context.errors[previous:]:
                        print(f'  WARN  {issue["source"]}: {concise(issue["message"])}', flush=True)
                    if row['Kind'] == 'listen' and not row['Sound']:
                        context.issue(word, 'listen', 'Skipped: listening card has no audio')
                        print('  SKIP listening card has no audio', flush=True)
                        continue
                    rows.append(render_exercise(row, config))
                    every = config.section('output')['autosave_every']
                    if every and number % every == 0:
                        _, failed = export_outputs(rows, config, stem + '_recovery', context, recovery=True)
                        recovery_failures.extend(failed)
                    if number < len(words):
                        time.sleep(config.section('runtime')['word_delay_seconds'])
                    continue
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
                            if getattr(context, 'last_cache_hit', False):
                                print('  CACHE reused saved dictionary result', flush=True)
                            for issue in context.errors[previous:]:
                                print(f'  WARN  {issue["source"]}: {concise(issue["message"])}', flush=True)
                    except Exception as exc:
                        context.issue(word, name, exc)
                        row[name] = ''
                        report.source(name, 'FAIL', started, context.errors[-1]['message'])
                previous = len(context.errors)
                try:
                    with context.source_budget():
                        row['Sound'] = select_audio(word, number, context) if options(config, 'normal')['audio'] else ''
                except Exception as exc:
                    context.issue(word, 'audio', exc)
                    row['Sound'] = ''
                print('  AUDIO ' + (row['Sound'][7:-1] if row['Sound'] else
                      'unavailable' if config.section('audio')['enabled'] else 'disabled'), flush=True)
                for error in context.errors[previous:]:
                    print(f'  WARN  {error["source"]}: {concise(error["message"])}', flush=True)
                row['FrontField'] = f'<span dir="{direction(config.section("language")["source"])}">' + html.escape(word) + '</span>' + (' ' + row['Sound'] if row['Sound'] else '')
                normal_options = options(config, 'normal')
                if normal_options['title'] or normal_options['instruction']:
                    qlang, alang = language_settings(config)
                    from app.exercises import language_name
                    hint = normal_options['instruction'].format(question_language=language_name(config, qlang), answer_language=language_name(config, alang))
                    row['FrontField'] = '<div class="gt-title">' + html.escape(normal_options['title']) + '</div><div class="exercise-instruction">' + html.escape(hint) + '</div>' + row['FrontField']
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
        if context.errors:
            try:
                error_path = config.resolve(config.section('output')['directory']) / f'{stem}_errors.json'
                error_path.parent.mkdir(parents=True, exist_ok=True)
                error_path.write_text(json.dumps(context.errors, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f'Saved skipped-row report: {error_path}')
            except OSError as exc:
                print(f'Cannot save skipped-row report: {exc}')
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='Validate config and Excel without fetching sources')
    modes.add_argument('--clear-cache', metavar='WORD', help='Delete cached dictionary results for one word')
    parser.add_argument('--source', choices=list(SOURCE_SPECS), help='Restrict --clear-cache to one dictionary')
    args = parser.parse_args(argv)
    if args.source and args.clear_cache is None:
        parser.error('--source requires --clear-cache')
    try:
        if args.clear_cache is not None:
            if not args.clear_cache.strip():
                raise ConfigError('--clear-cache word must not be blank')
            # Cache maintenance does not require a readable Excel workbook or browser.
            import tomllib
            from app.dictionary_cache import DictionaryCache
            from app.app_config import Config
            path = args.config.resolve()
            with path.open('rb') as stream:
                data = tomllib.load(stream)
            cache = data.get('dictionary_cache', {})
            config = Config(path, data)
            count = DictionaryCache(config.resolve(cache.get('path', 'Cache/dictionaries.sqlite3'))).delete_word(
                args.clear_cache, args.source)
            print(f'Removed {count} cached results for {args.clear_cache!r} ({args.source or "all sources"}). Local media files retained.')
            return 0
        config = load_config(args.config)
        if args.check:
            records, skipped = read_records(config)
            words = [row['Words'] for row in records]
            for item in skipped:
                print(f"SKIP Excel row {item['row']}: {item['message']}")
            print(f'Configuration OK: {len(words)} words. Sources: {", ".join(display_sources(config))}')
            return 0 if records else 1
        return run(config)
    except (ConfigError, OSError, ValueError, ImportError) as exc:
        print(f'Cannot run: {exc}. Check config.toml and requirements.txt.', file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'Run failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
