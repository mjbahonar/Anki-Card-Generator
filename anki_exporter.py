"""Stable V4 Anki schema, configurable presentation and referenced media only."""
import html
from pathlib import Path
import re
from lexin_scraper import normalize_headword
from sources import SOURCE_SPECS, supported

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
                     for name in display_sources(config))
    return '{{FrontSide}}<hr id="answer">\n' + body + '\n{{#Info}}{{Info}}{{/Info}}'


def row_back(row, config):
    return ''.join(str(row.get(name, '') or '') for name in display_sources(config)) + str(row.get('Info', '') or '')


def generate_anki_package(rows, output_path, config, media_files):
    import genanki
    settings = config.section('anki')
    css = config.resolve(config.section('style')['file']).read_text(encoding='utf-8')
    model = genanki.Model(settings['model_id'], 'Unified Vocabulary V5',
                         fields=[{'name': name} for name in FIELDS],
                         templates=[{'name': 'Vocabulary', 'qfmt': '<div class="front">{{FrontField}}</div>',
                                     'afmt': answer_template(config)}], css=css, sort_field_index=0)
    deck = genanki.Deck(settings['deck_id'], settings['deck_name'])
    references = set()
    for row in rows:
        word = row['Words']
        field_values = {'Word': html.escape(word), 'FrontField': row['FrontField'],
                        **{name: row.get(name, '') for name in SOURCE_SPECS}, 'Info': row.get('Info', '')}
        values = [str(field_values.get(name, '') or '') for name in FIELDS]
        deck.add_note(genanki.Note(model=model, fields=values,
                                 guid=genanki.guid_for(settings['model_id'], settings['deck_id'],
                                                      config.section('language')['source'], normalize_headword(word))))
        content = ''.join(values)
        references.update(re.findall(r'\[sound:([^\]]+)\]', content))
        references.update(re.findall(r'<img[^>]+src=["\']([^"\']+)', content))
    references.update(re.findall(r'url\(["\']?([^"\')]+)', css))
    package = genanki.Package(deck)
    package.media_files = [str(Path(path).resolve()) for path in sorted(set(media_files))
                           if Path(path).is_file() and Path(path).name in references]
    package.write_to_file(str(output_path))
