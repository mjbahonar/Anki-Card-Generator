"""Interface text for the settings GUI.

The GUI is English today. To add a language later, copy the ``'en'`` dictionary
below under a new code (for example ``'fa'``), translate the values and set
``_meta.dir`` to ``'rtl'`` for right-to-left scripts. Missing keys fall back to
English, labels fall back to the config key name and help text falls back to
the comment written next to the setting in config.toml. A language selector
appears in the GUI automatically once more than one language exists.
"""

DEFAULT_LANGUAGE = 'en'

STRINGS = {
    'en': {
        '_meta': {'name': 'English', 'dir': 'ltr'},
        'app.title': 'Anki Card Generator',
        'app.subtitle': 'Settings',
        'app.config_file': 'Settings file',

        'tab.languages': 'Languages',
        'tab.input': 'Excel input',
        'tab.dictionaries': 'Dictionaries',
        'tab.cards': 'Card types',
        'tab.audio': 'Audio',
        'tab.output': 'Output & deck',
        'tab.appearance': 'Appearance',
        'tab.advanced': 'Advanced',
        'tab.other': 'Other',

        'tab.languages.desc': 'Vocabulary direction and the exercise language pair.',
        'tab.input.desc': 'The workbook to read and how its rows are used.',
        'tab.dictionaries.desc': 'Turn dictionaries on or off. Cards show them in this order.',
        'tab.cards.desc': 'Titles, instructions, tags and audio for each Excel card type.',
        'tab.audio.desc': 'Pronunciation providers, tried in order until one succeeds.',
        'tab.output.desc': 'Output files, the Anki deck and the Anki media folder.',
        'tab.appearance.desc': 'Card style and the Info section shown last on every card.',
        'tab.advanced.desc': 'Time limits, browser behaviour and the dictionary cache.',
        'tab.other.desc': 'Settings without a dedicated page.',

        'group.language': 'Vocabulary',
        'group.practice': 'Exercises',
        'group.practice.language_names': 'Exercise language names',
        'group.input': 'Workbook',
        'group.meaning': 'Personal meaning column',
        'group.audio': 'Audio',
        'group.audio.word': 'Headword audio per input language',
        'group.output': 'Output files',
        'group.anki': 'Anki deck',
        'group.media': 'Anki media folder',
        'group.style': 'Card style',
        'group.info': 'Info section',
        'group.runtime': 'Runtime',
        'group.dictionary_cache': 'Dictionary cache',
        'group.cards.normal': 'Normal (dictionary word)',
        'group.cards.type': 'Type (spelling)',
        'group.cards.sentence': 'Sentence (speaking)',
        'group.cards.gap': 'Gap (fill in the blank)',
        'group.cards.listen': 'Listen',

        'source.lexin': 'Lexin',
        'source.bokmalsordboka': 'Bokmålsordboka',
        'source.nynorskordboka': 'Nynorskordboka',
        'source.google_translate': 'Google Translate',
        'source.dict_com': 'Dict.com',
        'source.fastdic': 'Fastdic',
        'source.faraazin': 'Faraazin',
        'source.b_amooz': 'B-Amooz',
        'source.dictionary_com': 'Dictionary.com',
        'source.thesaurus': 'Thesaurus.com',
        'source.google_dictionary': 'Google Dictionary',
        'source.cambridge': 'Cambridge',
        'source.images': 'Images',
        'source.oxford': 'Oxford',

        'field.enabled': 'Enabled',
        'field.media.anki_directory': 'Anki media folder',
        'field.dictionary_cache.path': 'Database file',
        'field.dictionary_cache.refresh': 'Fetch again (ignore cache)',
        'field.meaning.html': 'Read cells as HTML',
        'field.language.source': 'Input language',
        'field.language.translation_target': 'Translation language',
        'field.practice.question_language': 'Question language',
        'field.practice.answer_language': 'Answer language',
        'field.practice.model_id_base': 'Exercise model ID base',
        'field.input.file': 'Workbook file',
        'field.input.sheet': 'Worksheet',
        'field.input.header': 'First row is a header',
        'field.input.word_column': 'Input column',
        'field.input.deduplicate': 'Remove duplicates',
        'field.input.order': 'Word order',
        'field.input.max_words': 'Maximum words',
        'field.output.directory': 'Output folder',
        'field.output.formats': 'File formats',
        'field.output.filename_prefix': 'File name prefix',
        'field.output.autosave_every': 'Recovery save every N words',
        'field.anki.deck_name': 'Deck name',
        'field.anki.deck_id': 'Deck ID',
        'field.anki.model_id': 'Model ID',
        'field.audio.priority': 'Providers for other languages',
        'field.audio.directory': 'Audio folder',
        'field.audio.cache': 'Reuse downloaded audio',
        'field.audio.english_accent': 'English accent',
        'field.style.file': 'Style sheet',
        'field.runtime.timeout_seconds': 'Page timeout (s)',
        'field.runtime.source_timeout_seconds': 'Time budget per source (s)',
        'field.runtime.translation_attempts': 'Translation attempts',
        'field.runtime.retry_delay_seconds': 'Retry delay (s)',
        'field.runtime.word_delay_seconds': 'Delay between words (s)',
        'field.runtime.keep_awake': 'Keep the computer awake',
        'field.runtime.headless': 'Hide the browser window',

        'help.media.anki_directory': 'Audio and images are copied here. Leave blank to skip copying.',
        'help.dictionary_cache.enabled': 'Reuse saved dictionary results so repeated words are fast.',

        'list.add': 'Add…',
        'list.empty': 'Nothing selected',
        'list.add_value': 'Type and press Enter',
        'list.move_left': 'Move earlier',
        'list.remove': 'Remove',
        'source.up': 'Move up',
        'source.down': 'Move down',
        'source.settings': 'Settings',
        'source.on': 'On',
        'source.off': 'Off',
        'source.enabled_count': '{count} of {total} enabled',

        'deck.active': 'Active deck',
        'deck.active_help': 'Cards go to this deck. Choosing another one switches deck_name and deck_id together.',
        'deck.saved': 'Saved decks',
        'deck.saved_help': 'Stored in config.toml under [anki.saved_decks]. Removing one here does not touch Anki.',
        'deck.add': 'Add deck',
        'deck.add_help': 'Every deck needs its own ID; the next free one is suggested. The new deck becomes the active one.',
        'deck.name': 'Deck name',
        'deck.id': 'Deck ID',
        'deck.add_button': 'Add',
        'deck.use': 'Use',
        'deck.in_use': 'In use',
        'deck.remove': 'Remove',
        'deck.remove_confirm': 'Remove "{name}" from the saved list? The deck in Anki is not affected.',
        'deck.error_name': 'Enter a deck name that is not already in the list.',
        'deck.error_id': 'Enter a whole-number deck ID (1 or more) that no other saved deck uses.',

        'file.browse': 'Browse…',
        'file.refresh': 'Refresh the file list and check the file again',
        'file.found': '✓ File found',
        'file.missing': '✗ File not found — Check and Run will stop until it exists',
        'field.input.first_row': 'First Excel row',
        'field.input.last_row': 'Last Excel row',

        'cache.title': 'Cache maintenance',
        'cache.desc': 'Delete every cached result of one dictionary and shrink the database. Other dictionaries keep their cache.',
        'cache.source': 'Dictionary',
        'cache.clear': 'Clear cache',
        'cache.confirm': 'Delete all cached results for {source}? They are fetched again the next time this dictionary is used.',

        'action.save': 'Save',
        'action.revert': 'Discard changes',
        'action.reload': 'Reload',
        'action.check': 'Check',
        'action.run': 'Run',
        'action.stop': 'Stop',
        'action.open_output': 'Open output folder',
        'action.show_log': 'Log',
        'action.clear_log': 'Clear',

        'status.saved': 'All changes saved',
        'status.unsaved': '{count} unsaved changes',
        'status.saving': 'Saving…',
        'status.saved_now': 'Saved to config.toml',
        'status.running': 'Running…',
        'status.checking': 'Checking…',
        'status.stopping': 'Stopping — finished words are being saved…',
        'status.done': 'Finished',
        'status.failed': 'Finished with errors (exit code {code})',
        'status.stopped': 'Stopped — finished words were saved as a partial file',
        'status.progress': 'Word {current} of {total}: {word}',

        'error.conflict': 'config.toml was changed outside the GUI. Reload to see the new version; your unsaved edits will be lost.',
        'error.invalid_json': '{field}: invalid value',
        'error.busy': 'A task is already running.',
        'error.network': 'The GUI server is not responding. Is the terminal still open?',
        'warning.title': 'Saved, with a warning',

        'confirm.discard': 'Discard all unsaved changes?',
        'confirm.reload': 'Reload config.toml from disk? Unsaved changes will be lost.',
        'language.label': 'Interface language',
    },
}


def strings(language=None):
    """English merged with the requested language, so untranslated keys still show text."""
    merged = dict(STRINGS[DEFAULT_LANGUAGE])
    if language and language in STRINGS and language != DEFAULT_LANGUAGE:
        merged.update(STRINGS[language])
    return merged


def languages():
    return [{'code': code, 'name': data['_meta']['name'], 'dir': data['_meta']['dir']}
            for code, data in STRINGS.items()]
