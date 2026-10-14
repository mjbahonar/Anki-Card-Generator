"""Stable V4 Anki schema, configurable presentation and referenced media only."""
import html
from pathlib import Path
import re
from app.lexin_scraper import normalize_headword
from app.sources import SOURCE_SPECS, supported
from app.exercises import EXERCISE_FIELDS, KINDS, meaning_html

FIELDS = ['Word', 'FrontField', *SOURCE_SPECS, 'Info']


def display_sources(config):
    return [name for name, options in config.section('sources').items()
            if options['enabled'] and supported(name, config.section('language')['source'])]


def info_html(config):
    info = config.section('info')
    if not info['enabled']:
        return ''
    return ('<div class="gt-container info-container"><div class="gt-title">'
            + html.escape(info['title']) + '</div><hr class="gt-separator">'
            '<div class="gt-text info-text">' + html.escape(info['text'])
            + '<div class="info-link-wrapper"><a class="info-link" href="'
            + html.escape(info['url'], quote=True) + '" target="_blank" rel="noopener">'
            + html.escape(info['link_text']) + '</a></div></div></div>')


def answer_template(config):
    body = '\n'.join('{{#' + name + '}}{{' + name + '}}{{/' + name + '}}'
                     for name in (display_sources(config) or [next(iter(SOURCE_SPECS))]))
    return '{{FrontSide}}<hr id="answer">\n' + body + '\n{{#Info}}{{Info}}{{/Info}}'


def row_back(row, config):
    if row.get('Kind', 'normal') != 'normal':
        return row.get('BackField', '') + str(row.get('Info', '') or '')
    return meaning_html(row, config) + ''.join(str(row.get(name, '') or '') for name in display_sources(config)) + str(row.get('Info', '') or '')


def exercise_model_id(kind, config):
    return config.data.get('practice', {}).get('model_id_base', 1559328500) + KINDS.index(kind) - 1


def exercise_model_name(kind):
    return 'Vocabulary Exercise · ' + kind


def note_values(row, config):
    if row.get('Kind', 'normal') != 'normal':
        return [row['Identity'], html.escape(row['Words']), html.escape(row['Answer']), row['FrontField'],
                row['BackField'], row.get('Sound', ''), row.get('Info', '')]
    values = {'Word': html.escape(row['Words']), 'FrontField': row['FrontField'],
              **{name: row.get(name, '') for name in SOURCE_SPECS}, 'Info': row.get('Info', '')}
    # Reuse the first displayed source field to keep the published schema intact.
    # With all sources disabled, the existing first source field holds only meaning.
    active = display_sources(config)
    first = next(iter(active or SOURCE_SPECS))
    personal_meaning = meaning_html(row, config)
    if personal_meaning:
        values[first] = personal_meaning + (str(values.get(first, '') or '') if active else '')
    return [str(values.get(name, '') or '') for name in FIELDS]


def note_guid(row, config):
    import genanki
    settings = config.section('anki')
    kind = row.get('Kind', 'normal')
    if kind != 'normal':
        return genanki.guid_for(exercise_model_id(kind, config), settings['deck_id'], row['Identity'])
    return genanki.guid_for(settings['model_id'], settings['deck_id'],
                           config.section('language')['source'], normalize_headword(row['Words']))


def write_import_csv(rows, path, config):
    """Positional field mapping supports distinct existing note types in one file."""
    import csv
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        stream.write('#separator:Comma\n#html:true\n#notetype column:1\n#tags column:2\n#guid column:3\n')
        writer = csv.writer(stream)
        for row in rows:
            kind = row.get('Kind', 'normal')
            name = 'Unified Vocabulary V5' if kind == 'normal' else exercise_model_name(kind)
            values = note_values(row, config)
            writer.writerow([name, ' '.join(row.get('Tags', [])), note_guid(row, config), *values, *([''] * (len(FIELDS) - len(values)))])


def generate_anki_package(rows, output_path, config, media_files):
    import genanki
    settings = config.section('anki')
    css = config.resolve(config.section('style')['file']).read_text(encoding='utf-8')
    model = genanki.Model(settings['model_id'], 'Unified Vocabulary V5',
                         fields=[{'name': name} for name in FIELDS],
                         templates=[{'name': 'Vocabulary', 'qfmt': '<div class="front">{{FrontField}}</div>',
                                     'afmt': answer_template(config)}], css=css, sort_field_index=0)
    deck = genanki.Deck(settings['deck_id'], settings['deck_name'])
    exercise_models = {}
    references = set()
    for row in rows:
        word = row['Words']
        values = note_values(row, config)
        kind = row.get('Kind', 'normal')
        selected_model = model
        if kind != 'normal':
            if kind not in exercise_models:
                typed = ('<div class="exercise-type-answer">{{type:Answer}}</div>'
                         '<script>(function(){var front=document.querySelector("[data-answer-direction]");'
                         'var answer=document.getElementById("typeans");if(front&&answer){'
                         'var direction=front.getAttribute("data-answer-direction");answer.setAttribute("dir",direction);'
                         'answer.style.direction=direction;answer.style.textAlign=direction==="rtl"?"right":"left";}})();</script>') if kind == 'type' else ''
                exercise_models[kind] = genanki.Model(
                    exercise_model_id(kind, config), exercise_model_name(kind),
                    fields=[{'name': name} for name in EXERCISE_FIELDS],
                    templates=[{'name': kind, 'qfmt': '{{Front}}' + typed,
                                'afmt': '{{FrontSide}}<hr id="answer">{{Back}}{{#Info}}{{Info}}{{/Info}}'}],
                    css=css, sort_field_index=1)
            selected_model = exercise_models[kind]
        guid = note_guid(row, config)
        deck.add_note(genanki.Note(model=selected_model, fields=values, guid=guid, tags=row.get('Tags', [])))
        content = ''.join(values)
        references.update(re.findall(r'\[sound:([^\]]+)\]', content))
        references.update(re.findall(r'<(?:img|audio)[^>]+src=["\']([^"\']+)', content))
    references.update(re.findall(r'url\(["\']?([^"\')]+)', css))
    package = genanki.Package(deck)
    package.media_files = [str(Path(path).resolve()) for path in sorted(set(media_files))
                           if Path(path).is_file() and Path(path).name in references]
    package.write_to_file(str(output_path))
