"""Read config.toml into a form description and write edits back without losing comments.

config.toml stays the only settings file: the GUI edits existing keys in place
(comments, spacing and key order are kept) and validates the result with the
same loader that ``main.py`` uses before replacing the file.
"""
import hashlib
import json
import os
from pathlib import Path
import re

import tomlkit
from tomlkit.items import AoT, Array, Bool, Float, Integer, KeyType, SingleKey, String, Table

from app.app_config import ConfigError, load_config


class ConflictError(Exception):
    """config.toml changed on disk after the GUI loaded it."""


class EditError(ValueError):
    """An edit does not fit the existing setting."""


# Pages of the GUI and the top-level tables they show. Unknown tables go to "other".
TABS = [
    ('languages', ['language', 'practice']),
    ('input', ['input', 'meaning']),
    ('dictionaries', ['sources']),
    ('cards', ['cards']),
    ('audio', ['audio']),
    ('output', ['output', 'anki', 'media']),
    ('appearance', ['style', 'info']),
    ('advanced', ['runtime', 'dictionary_cache']),
]

LANGUAGE_CODES = ['no', 'nb', 'nn', 'en', 'fa', 'de', 'fr', 'es', 'ar', 'ru', 'uk']
AUDIO_PROVIDERS = ['lexin', 'fastdic', 'google_tts']

# Known choices. "select": one of the options; "suggest": free text with suggestions;
# "ordered": a list whose items come from the options and whose order matters.
CHOICES = {
    'language.source': ('suggest', ['no', 'en', 'fa']),
    'language.translation_target': ('suggest', LANGUAGE_CODES),
    'practice.question_language': ('suggest', LANGUAGE_CODES),
    'practice.answer_language': ('suggest', LANGUAGE_CODES),
    'input.order': ('select', ['excel', 'random']),
    'sources.lexin.variant': ('select', ['bokmal', 'nynorsk', 'both']),
    'sources.images.priority': ('ordered', ['bing', 'commons', 'google']),
    'audio.priority': ('ordered', AUDIO_PROVIDERS),
    'audio.word.*': ('ordered', AUDIO_PROVIDERS),
    'audio.english_accent': ('select', ['us', 'uk']),
    'output.formats': ('ordered', ['xlsx', 'csv', 'apkg', 'html', 'json', 'report']),
}
FILE_FIELDS = {'input.file': ('.xlsx', '.xlsm', '.xls'), 'style.file': ('.css',)}
LONG_TEXT = {'info.text'}
# Settings that take a name or a zero-based number (sheet name or index, column header or index).
NAME_OR_INDEX = {'input.sheet', 'input.word_column'}
DECKS = ['anki', 'saved_decks']  # Saved deck names and IDs; deck_name/deck_id hold the active one.


def version(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_text(path):
    return Path(path).read_bytes().decode('utf-8')


def _comment(item):
    trivia = getattr(item, 'trivia', None)
    text = (trivia.comment if trivia else '') or ''
    return text.lstrip('#').strip()


def _choice(dotted):
    if dotted in CHOICES:
        return CHOICES[dotted]
    parent = dotted.rsplit('.', 1)[0] + '.*'
    return CHOICES.get(parent)


def _kind(item, value):
    if isinstance(item, Bool) or isinstance(value, bool):
        return 'bool'
    if isinstance(item, Integer):
        return 'int'
    if isinstance(item, Float):
        return 'float'
    if isinstance(item, String):
        return 'str'
    if isinstance(item, Array) and all(isinstance(v, str) for v in value):
        return 'list'
    return 'raw'


def _field(path, item):
    value = item.unwrap() if hasattr(item, 'unwrap') else item
    dotted = '.'.join(path)
    kind = _kind(item, value)
    field = {'key': path[-1], 'path': path, 'type': kind, 'value': value, 'help': _comment(item)}
    if dotted in NAME_OR_INDEX and kind in ('int', 'str'):
        field['type'] = 'name_or_index'
        field['value'] = str(value)
    if kind == 'raw':
        field['value'] = json.dumps(value, ensure_ascii=False)
    if kind == 'str' and (dotted in LONG_TEXT or '\n' in value):
        field['type'] = 'text'
    choice = _choice(dotted)
    if choice and kind in ('str', 'list'):
        field['mode'], field['options'] = choice
    if dotted in FILE_FIELDS:
        field['mode'] = 'file'
        field['extensions'] = list(FILE_FIELDS[dotted])
    return field


def _groups(table, path):
    """One group per table that has plain settings; nested tables become their own groups."""
    fields, nested = [], []
    for key in table.keys():
        item = _raw(table, key)
        if isinstance(item, Table):
            nested.append((key, item))
        elif isinstance(item, AoT):
            continue  # Arrays of tables are not used by config.toml; leave them to text editing.
        else:
            fields.append(_field(path + [key], item))
    groups = []
    if fields:
        groups.append({'path': path, 'help': _comment(table), 'fields': fields})
    for key, item in nested:
        if path + [key] == DECKS:
            continue  # Shown by the deck picker instead of as plain fields.
        groups.extend(_groups(item, path + [key]))
    return groups


def describe(path):
    """Form description of config.toml for the GUI."""
    text = read_text(path)
    doc = tomlkit.parse(text)
    known = {name for _, names in TABS for name in names}
    tabs = []
    for tab, names in TABS + [('other', [k for k in doc.keys() if k not in known])]:
        groups = []
        for name in names:
            item = doc.get(name)
            if isinstance(item, Table):
                groups.extend(_groups(item, [name]))
            elif item is not None and not isinstance(item, AoT):
                groups.append({'path': [], 'help': '', 'fields': [_field([name], doc.item(name))]})
        if groups:
            tabs.append({'id': tab, 'groups': groups})
    sources = doc.get('sources')
    order = [k for k, v in sources.items() if isinstance(v, Table)] if isinstance(sources, Table) else []
    anki = doc.get('anki')
    saved = anki.get('saved_decks') if isinstance(anki, Table) else None
    decks = [[name, value] for name, value in saved.unwrap().items()] if isinstance(saved, Table) else []
    return {'version': version(text), 'tabs': tabs, 'sources_order': order, 'decks': decks}


def _coerce(path, existing, value):
    dotted = '.'.join(path)
    if dotted in NAME_OR_INDEX:
        # Digits mean a zero-based position; anything else is a sheet or column name.
        text = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
        if not text:
            raise EditError(f'{dotted} needs a name or a number (0 = first)')
        return int(text) if text.isdigit() else text
    kind = _kind(existing, existing.unwrap() if hasattr(existing, 'unwrap') else existing)
    if kind == 'bool':
        if not isinstance(value, bool):
            raise EditError(f'{dotted} must be true or false')
        return value
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
            raise EditError(f'{dotted} must be a whole number')
        return int(value)
    if kind == 'float':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EditError(f'{dotted} must be a number')
        return float(value)
    if kind == 'str':
        if not isinstance(value, str):
            raise EditError(f'{dotted} must be text')
        return value
    if kind == 'list':
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise EditError(f'{dotted} must be a list of text values')
        return value
    if isinstance(value, str):  # Raw values arrive as JSON text.
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise EditError(f'{dotted}: {exc}') from exc
    return value


def _raw(container, key):
    """The tomlkit item itself (with its type and comment), not the plain Python value."""
    return (container.value if isinstance(container, Table) else container).item(key)


def _container(doc, path):
    node = doc
    for key in path:
        if not hasattr(node, 'get') or key not in node:
            raise EditError('Unknown setting: ' + '.'.join(path))
        node = node[key]
    return node


def _reorder_sources(doc, order):
    sources = doc.get('sources')
    if not isinstance(sources, Table):
        raise EditError('config.toml has no [sources] tables to reorder')
    current = [k for k, v in sources.items() if isinstance(v, Table)]
    if sorted(order) != sorted(current):
        raise EditError('Dictionary order must list every [sources.*] table exactly once')
    if order == current:
        return False
    tables = {k: sources[k] for k in current}
    # Comments after the last dictionary introduce the next section; keep them at the end.
    tail = _detach_tail(tables[current[-1]])
    for key in current:
        del sources[key]
    for key in order:
        sources[key] = tables[key]
    tables[order[-1]].value.body.extend(tail)
    return True


def _detach_tail(table):
    """Remove trailing comments/blank lines (they introduce the next section) and return them."""
    body = table.value.body
    tail = []
    while body and body[-1][0] is None:
        tail.insert(0, body.pop())
    return tail


def _set_decks(doc, decks):
    if (not isinstance(decks, list) or not all(isinstance(d, list) and len(d) == 2 for d in decks)
            or not all(isinstance(n, str) and n.strip() and type(i) is int and 1 <= i <= 2**63 - 1 for n, i in decks)):
        raise EditError('Saved decks need a name and a whole-number deck ID >= 1')
    names = [n.strip() for n, _ in decks]
    if len(set(names)) != len(names) or len({i for _, i in decks}) != len(decks):
        raise EditError('Every saved deck needs its own name and deck ID')
    anki = doc.get('anki')
    if not isinstance(anki, Table):
        raise EditError('config.toml has no [anki] section')
    table = anki.get('saved_decks')
    if isinstance(table, Table):
        tail = _detach_tail(table)
        for key in list(table.keys()):
            del table[key]
    else:
        tail = _detach_tail(anki)
        table = tomlkit.table()
        table.add(tomlkit.comment('Saved decks (name = deck_id). Pick one in the GUI, or copy it into deck_name/deck_id.'))
        anki.append('saved_decks', table)
    for name, deck in decks:
        table.append(SingleKey(name.strip(), KeyType.Basic), deck)  # Always quoted, like hand-written names.
    table.value.body.extend(tail)  # The next section's heading comments stay after the list.


def apply_changes(text, changes, sources_order=None):
    """Return config text with changes applied; comments and layout are kept."""
    doc = tomlkit.parse(text)
    for change in changes:
        path = change.get('path')
        if path == DECKS and 'decks' in change:
            _set_decks(doc, change['decks'])
            continue
        if not isinstance(path, list) or not path or not all(isinstance(p, str) for p in path):
            raise EditError('Invalid setting path')
        parent = _container(doc, path[:-1]) if len(path) > 1 else doc
        if not hasattr(parent, 'get') or path[-1] not in parent:
            raise EditError('Unknown setting: ' + '.'.join(path))
        existing = _raw(parent, path[-1])
        if isinstance(existing, Table):
            raise EditError('Cannot replace a whole section: ' + '.'.join(path))
        parent[path[-1]] = _coerce(path, existing, change.get('value'))
    reordered = bool(sources_order) and _reorder_sources(doc, list(sources_order))
    result = tomlkit.dumps(doc)
    if reordered:
        result = re.sub(r'(\r?\n){3,}', lambda m: m.group(1) * 2, result)
    return result


def _write_atomic(path, text):
    temporary = path.with_name('.' + path.name + '.gui-save')
    temporary.write_bytes(text.encode('utf-8'))
    os.replace(temporary, path)


def save(path, changes, sources_order, expected_version):
    """Validate and write edits. Returns (new version, warning or '')."""
    path = Path(path).resolve()
    text = read_text(path)
    if version(text) != expected_version:
        raise ConflictError('config.toml changed on disk')
    updated = apply_changes(text, changes, sources_order)
    if updated == text:
        return version(text), ''
    check = path.with_name('.' + path.name + '.gui-check.toml')
    try:
        check.write_bytes(updated.encode('utf-8'))
        load_config(check, check_files=False)  # Same rules as main.py; relative paths resolve alike.
    finally:
        check.unlink(missing_ok=True)
    _write_atomic(path, updated)
    warning = ''
    try:
        load_config(path)  # Missing workbook or style file: saved, but worth telling the user.
    except ConfigError as exc:
        warning = str(exc)
    return version(updated), warning
