"""Load and validate the single user-facing configuration file."""

from dataclasses import dataclass
from pathlib import Path
import re
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
    from sources import SOURCE_SPECS

    path = Path(path).resolve()
    try:
        with path.open('rb') as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f'Cannot read {path}: {exc}') from exc
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
        if section != 'sources' and set(data[section]) - set(keys):
            raise ConfigError(f'Unknown setting in [{section}]: {set(data[section]) - set(keys)}')
    if set(data) - set(required):
        raise ConfigError(f'Unknown configuration section: {set(data) - set(required)}')
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
    for key in ['timeout_seconds', 'retry_delay_seconds', 'word_delay_seconds']:
        value = data['runtime'][key]
        if type(value) not in (int, float) or value < (1 if key == 'timeout_seconds' else 0):
            raise ConfigError(f'runtime.{key} must be a valid non-negative number (timeout >= 1)')
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
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2,4})?', data['language'][key]):
            raise ConfigError(f'language.{key} must be a language code such as no, en or fa')
    if data['audio']['english_accent'] not in ['us', 'uk']:
        raise ConfigError('audio.english_accent must be us or uk')
    if data['anki']['model_id'] in [1559328410, 1559328412]:
        raise ConfigError('V4 has a new field schema. Use its new model_id (1559328440), not a V3 model ID.')
    priority = data['audio']['priority']
    if not isinstance(priority, list) or any(item not in ['lexin', 'fastdic', 'google_tts'] for item in priority):
        raise ConfigError('audio.priority supports lexin, fastdic and google_tts')
    if data['audio']['enabled'] and not priority:
        raise ConfigError('audio.priority must not be empty when audio is enabled')
    if not data['info']['url'].startswith(('https://', 'http://')):
        raise ConfigError('info.url must be an http(s) URL')
    for name, settings in data['sources'].items():
        if name not in SOURCE_SPECS:
            raise ConfigError(f'Unknown source: {name}. Available: {", ".join(SOURCE_SPECS)}')
        if not isinstance(settings, dict) or type(settings.get('enabled')) is not bool:
            raise ConfigError(f'sources.{name}.enabled must be true or false')
        allowed = ({'enabled', 'count'} if name == 'images' else
                   {'enabled', 'examples_per_definition'} if name in ['fastdic', 'cambridge'] else {'enabled'})
        if set(settings) - allowed:
            raise ConfigError(f'Unknown option in sources.{name}')
        if name == 'images' and (type(settings.get('count', 3)) is not int or not 1 <= settings.get('count', 3) <= 10):
            raise ConfigError('sources.images.count must be between 1 and 10')
        if name in ['fastdic', 'cambridge'] and (type(settings.get('examples_per_definition', 3)) is not int
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
