"""Load and validate the single user-facing configuration file."""

from dataclasses import dataclass
from pathlib import Path
import re
import math
import tomllib


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    path: Path
    data: dict

    def section(self, name):
        return self.data[name]

    def resolve(self, value):
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (self.path.parent / path).resolve()


def load_config(path):
    from app.sources import SOURCE_SPECS

    path = Path(path).resolve()
    try:
        with path.open('rb') as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f'Cannot read {path}: {exc}') from exc
    # Accept old audio.copy_to configurations without requiring the legacy key in new files.
    if isinstance(data.get('audio'), dict):
        data['audio'].setdefault('copy_to', '')
    media = data.get('media', {})
    if not isinstance(media, dict) or set(media) - {'anki_directory'} or not isinstance(media.get('anki_directory', ''), str):
        raise ConfigError('media.anki_directory must be a path string')
    required = {
        'language': ['source', 'translation_target'],
        'input': ['file', 'sheet', 'header', 'word_column', 'deduplicate', 'max_words'],
        'output': ['directory', 'formats', 'filename_prefix', 'autosave_every'],
        'anki': ['deck_name', 'deck_id', 'model_id'], 'style': ['file'],
        'audio': ['enabled', 'priority', 'directory', 'copy_to', 'cache', 'english_accent'],
        'runtime': ['timeout_seconds', 'translation_attempts', 'retry_delay_seconds',
                    'word_delay_seconds', 'keep_awake', 'headless'],
        'info': ['enabled', 'title', 'text', 'link_text', 'url'], 'sources': [],
    }
    for section, keys in required.items():
        if not isinstance(data.get(section), dict):
            raise ConfigError(f'Missing [{section}] section')
        for key in keys:
            if key not in data[section]:
                raise ConfigError(f'Missing {section}.{key}')
        optional = ({'source_timeout_seconds'} if section == 'runtime' else
                    {'order'} if section == 'input' else {'word'} if section == 'audio' else set())
        if section != 'sources' and set(data[section]) - set(keys) - optional:
            raise ConfigError(f'Unknown setting in [{section}]: {set(data[section]) - set(keys) - optional}')
    cache = data.setdefault('dictionary_cache', {'enabled': True, 'path': 'Cache/dictionaries.sqlite3', 'refresh': False})
    if (not isinstance(cache, dict) or set(cache) - {'enabled', 'path', 'refresh'}
            or type(cache.get('enabled', True)) is not bool or type(cache.get('refresh', False)) is not bool
            or not isinstance(cache.get('path', 'Cache/dictionaries.sqlite3'), str)
            or not cache.get('path', 'Cache/dictionaries.sqlite3').strip()):
        raise ConfigError('dictionary_cache requires enabled/refresh booleans and a non-empty path')
    meaning = data.setdefault('meaning', {'enabled': True})
    if (not isinstance(meaning, dict) or set(meaning) - {'enabled', 'html'}
            or type(meaning.get('enabled', True)) is not bool or type(meaning.get('html', False)) is not bool):
        raise ConfigError('meaning.enabled and meaning.html must be true or false')
    unknown = set(data) - set(required) - {'practice', 'cards', 'media', 'dictionary_cache', 'meaning'}
    if unknown:
        raise ConfigError(f'Unknown configuration section: {unknown}')
    from app.exercises import validate_cards
    validate_cards(data)
    if data['input'].get('order', 'excel') not in ('excel', 'random'):
        raise ConfigError('input.order must be excel or random')
    for section, keys in {
        'input': ['header', 'deduplicate'], 'audio': ['enabled', 'cache'],
        'runtime': ['keep_awake', 'headless'], 'info': ['enabled'],
    }.items():
        for key in keys:
            if type(data[section][key]) is not bool:
                raise ConfigError(f'{section}.{key} must be true or false')
    for section, keys in {
        'language': ['source', 'translation_target'], 'input': ['file'],
        'output': ['directory', 'filename_prefix'], 'anki': ['deck_name'], 'style': ['file'],
        'audio': ['directory', 'copy_to', 'english_accent'],
        'info': ['title', 'text', 'link_text', 'url'],
    }.items():
        for key in keys:
            value = data[section][key]
            if not isinstance(value, str) or (not value.strip() and key != 'copy_to'):
                raise ConfigError(f'{section}.{key} must be a non-empty string')
    for section, key, minimum in [('input', 'max_words', 0), ('output', 'autosave_every', 0),
                                  ('anki', 'deck_id', 1), ('anki', 'model_id', 1),
                                  ('runtime', 'translation_attempts', 1)]:
        value = data[section][key]
        if type(value) is not int or value < minimum:
            raise ConfigError(f'{section}.{key} must be an integer >= {minimum}')
        if section == 'anki' and value > 2**63 - 1:
            raise ConfigError(f'anki.{key} exceeds the supported SQLite integer range')
    for key in ['timeout_seconds', 'retry_delay_seconds', 'word_delay_seconds']:
        value = data['runtime'][key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < (1 if key == 'timeout_seconds' else 0):
            raise ConfigError(f'runtime.{key} must be a valid non-negative number (timeout >= 1)')
    limit = data['runtime'].get('source_timeout_seconds', 30)
    if type(limit) not in (int, float) or not math.isfinite(limit) or limit < 0:
        raise ConfigError('runtime.source_timeout_seconds must be finite and >= 0 (0 disables the source budget)')
    for key in ['sheet', 'word_column']:
        value = data['input'][key]
        if not ((type(value) is int and value >= 0) or (isinstance(value, str) and value.strip())):
            raise ConfigError(f'input.{key} must be a name or a zero-based index')
    if isinstance(data['input']['word_column'], str) and not data['input']['header']:
        raise ConfigError('A named word_column requires input.header = true')
    formats = data['output']['formats']
    if not isinstance(formats, list) or not formats or any(f not in ['xlsx', 'csv', 'apkg', 'html', 'json'] for f in formats):
        raise ConfigError('output.formats must contain xlsx, csv, apkg, html and/or json')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', data['output']['filename_prefix']):
        raise ConfigError('output.filename_prefix may contain letters, digits, underscores and hyphens')
    for key in ['source', 'translation_target']:
        data['language'][key] = data['language'][key].lower()
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2,4})?', data['language'][key]):
            raise ConfigError(f'language.{key} must be a language code such as no, en or fa')
    if data['audio']['english_accent'] not in ['us', 'uk']:
        raise ConfigError('audio.english_accent must be us or uk')
    if data['anki']['model_id'] in [1559328410, 1559328412, 1559328440, 1559328450]:
        raise ConfigError('The final V5 schema needs a new model_id (1559328451); do not reuse V3/V4/draft V5 IDs.')
    priority = data['audio']['priority']
    if not isinstance(priority, list) or any(item not in ['lexin', 'fastdic', 'google_tts'] for item in priority):
        raise ConfigError('audio.priority supports lexin, fastdic and google_tts')
    word = data['audio'].get('word', {})
    if not isinstance(word, dict):
        raise ConfigError('[audio.word] must map language codes to provider lists')
    for code, providers in word.items():
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2,4})?', code):
            raise ConfigError(f'audio.word.{code} must be a lowercase language code such as no or en')
        if not isinstance(providers, list) or any(item not in ['lexin', 'fastdic', 'google_tts'] for item in providers):
            raise ConfigError(f'audio.word.{code} supports lexin, fastdic and google_tts; [] disables')
    if data['audio']['enabled'] and not priority and not word:
        raise ConfigError('audio.priority must not be empty when audio is enabled')
    if not data['info']['url'].startswith(('https://', 'http://')):
        raise ConfigError('info.url must be an http(s) URL')
    for name, settings in data['sources'].items():
        if name not in SOURCE_SPECS:
            raise ConfigError(f'Unknown source: {name}. Available: {", ".join(SOURCE_SPECS)}')
        if not isinstance(settings, dict) or type(settings.get('enabled')) is not bool:
            raise ConfigError(f'sources.{name}.enabled must be true or false')
        allowed = ({'enabled', 'variant', 'table_audio', 'entries'} if name == 'lexin' else
                   {'enabled', 'count', 'priority'} if name == 'images' else
                   {'enabled', 'examples_per_definition'} if name in ['fastdic', 'cambridge', 'oxford'] else {'enabled'})
        if set(settings) - allowed:
            raise ConfigError(f'Unknown option in sources.{name}')
        if name == 'lexin' and settings.get('variant', 'bokmal') not in ('bokmal', 'nynorsk', 'both'):
            raise ConfigError('sources.lexin.variant must be bokmal, nynorsk or both')
        if name == 'lexin' and type(settings.get('table_audio', False)) is not bool:
            raise ConfigError('sources.lexin.table_audio must be true or false')
        if name == 'lexin' and (type(settings.get('entries', 2)) is not int or not 1 <= settings.get('entries', 2) <= 10):
            raise ConfigError('sources.lexin.entries must be between 1 and 10')
        if name == 'images' and (type(settings.get('count', 3)) is not int or not 1 <= settings.get('count', 3) <= 10):
            raise ConfigError('sources.images.count must be between 1 and 10')
        if name == 'images':
            priority = settings.get('priority', ['google', 'commons'])
            if not isinstance(priority, list) or not priority or any(p not in ['google', 'commons'] for p in priority):
                raise ConfigError('sources.images.priority must contain google and/or commons')
        if name in ['fastdic', 'cambridge', 'oxford'] and (type(settings.get('examples_per_definition', 3)) is not int
                                                 or settings.get('examples_per_definition', 3) < 0):
            raise ConfigError(f'sources.{name}.examples_per_definition must be an integer >= 0')
    config = Config(path, data)
    if not config.resolve(data['input']['file']).is_file():
        raise ConfigError(f'Input file not found: {config.resolve(data["input"]["file"])}')
    if not config.resolve(data['style']['file']).is_file():
        raise ConfigError(f'Style file not found: {config.resolve(data["style"]["file"])}')
    if config.resolve(data['input']['file']).suffix.lower() not in ['.xlsx', '.xls']:
        raise ConfigError('input.file must be an Excel .xlsx or .xls file')
    return config
