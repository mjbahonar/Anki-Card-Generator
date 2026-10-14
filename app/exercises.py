"""Excel exercise records and language-aware presentation, separate from vocabulary."""
import hashlib
import html
import re
from io import BytesIO
from string import Formatter

from app.lexin_scraper import audio_filename, normalize_headword

KINDS = ('normal', 'type', 'sentence', 'gap', 'listen')
EXERCISE_FIELDS = ['ID', 'Question', 'Answer', 'Front', 'Back', 'Sound', 'Info']
GAP_MARKER = re.compile(r'\[(?:…|\.\.\.)\]')


def gap_answers(question, answer):
    count = len(GAP_MARKER.findall(question))
    answers = [line.strip() for line in answer.splitlines()]
    if not count:
        raise ValueError('Gap question must contain […] or [...]')
    if len(answers) != count:
        raise ValueError(f'Gap has {count} blanks but {len(answers)} answer lines; write one answer per line')
    if any(not value for value in answers):
        raise ValueError('Gap answer lines must not be blank')
    return answers


def complete_gap(question, answer, markup=False):
    answers = iter(gap_answers(question, answer))
    if markup:
        # Escape source and inserted answers separately; replacement never interprets backslashes.
        return GAP_MARKER.sub(lambda _: '<strong class="exercise-gap-solution">' + html.escape(next(answers)) + '</strong>',
                              html.escape(question)).replace('\n', '<br>')
    return GAP_MARKER.sub(lambda _: next(answers), question)


LANGUAGES = {'en': 'English', 'no': 'Norwegian', 'nb': 'Norwegian (Bokmål)',
             'nn': 'Norwegian (Nynorsk)', 'fa': 'Persian', 'de': 'German',
             'fr': 'French', 'es': 'Spanish', 'ar': 'Arabic', 'sv': 'Swedish',
             'da': 'Danish', 'it': 'Italian', 'tr': 'Turkish'}
DEFAULTS = {
    'normal': dict(title='', instruction='', audio=True, tag='normal'),
    'type': dict(title='Spelling practice', instruction='Write the equivalent in {answer_language}.', audio=True, tag='type'),
    'sentence': dict(title='Speaking practice', instruction='Say this sentence in {answer_language}.', audio=True, tag='sentence'),
    'gap': dict(title='Fill in the blank', instruction='Complete the sentence in {answer_language}.', audio=True, tag='gap'),
    'listen': dict(title='Listening practice', instruction='Listen and repeat in {answer_language}.', audio=True, tag='listen'),
}


def options(config, kind):
    return {**DEFAULTS[kind], **config.data.get('cards', {}).get(kind, {})}


def language_settings(config):
    settings = config.data.get('practice', {})
    return (settings.get('question_language', 'en').lower(),
            settings.get('answer_language', config.section('language')['source']).lower())


def direction(language):
    return 'rtl' if language.split('-')[0] in ('fa', 'ar', 'he', 'ur') else 'ltr'


def language_name(config, code):
    return config.data.get('practice', {}).get('language_names', {}).get(code, LANGUAGES.get(code, code))


def validate_cards(data):
    from app.app_config import ConfigError
    practice = data.get('practice', {})
    if not isinstance(practice, dict) or set(practice) - {'question_language', 'answer_language', 'language_names', 'model_id_base'}:
        raise ConfigError('Unknown or invalid [practice] setting')
    for key in ('question_language', 'answer_language'):
        if key in practice:
            value = practice[key]
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?', value):
                raise ConfigError(f'practice.{key} must be a language code')
            practice[key] = value.lower()
    base = practice.get('model_id_base', 1559328500)
    if type(base) is not int or not 1 <= base <= 2**63 - 5 or data['anki']['model_id'] in range(base, base + 4):
        raise ConfigError('practice.model_id_base must reserve four IDs separate from anki.model_id')
    names = practice.get('language_names', {})
    if not isinstance(names, dict) or any(not isinstance(v, str) or not v.strip() for v in names.values()):
        raise ConfigError('practice.language_names must map codes to names')
    cards = data.get('cards', {})
    if not isinstance(cards, dict) or set(cards) - set(KINDS):
        raise ConfigError('cards supports normal, type, sentence, gap, listen')
    for kind, settings in cards.items():
        if not isinstance(settings, dict) or set(settings) - {'title', 'instruction', 'audio', 'tag'}:
            raise ConfigError(f'Invalid cards.{kind} setting')
        for key, value in settings.items():
            if key == 'audio':
                if type(value) is not bool:
                    raise ConfigError(f'cards.{kind}.audio must be true or false')
            elif not isinstance(value, str) or (key not in ('instruction', 'title') and not value.strip()):
                raise ConfigError(f'cards.{kind}.{key} must be text')
        if 'tag' in settings and re.search(r'[\s,]', settings['tag']):
            raise ConfigError(f'cards.{kind}.tag must be a single tag')
        try:
            for _, field, spec, conversion in Formatter().parse(settings.get('instruction', '')):
                if field is not None and (field not in ('question_language', 'answer_language') or spec or conversion):
                    raise ValueError('Only {question_language} and {answer_language} are supported')
        except ValueError as exc:
            raise ConfigError(f'cards.{kind}.instruction: {exc}') from exc


def read_records(config):
    import pandas as pd
    from app.app_config import ConfigError
    settings = config.section('input')
    try:
        frame = pd.read_excel(config.resolve(settings['file']), sheet_name=settings['sheet'],
                              header=0 if settings['header'] else None)
        column = settings['word_column']
        position = column if type(column) is int else frame.columns.get_loc(column)
        if not 0 <= position < len(frame.columns):
            raise IndexError('word column is outside the sheet')
    except Exception as exc:
        raise ConfigError(f'Cannot read input sheet/word column: {exc}') from exc
    def cell(row, offset):
        if position + offset >= len(frame.columns):
            return ''
        value = row.iloc[position + offset]
        return '' if pd.isna(value) else str(value).strip()
    records, skipped, seen = [], [], set()
    question_lang, answer_lang = language_settings(config)
    for index, row in frame.iterrows():
        question, kind, tags, answer, meaning = [cell(row, i) for i in range(5)]
        if not question:
            continue
        kind = kind.lower() or 'normal'
        line = int(index) + (2 if settings['header'] else 1)
        reason = ''
        if kind not in KINDS:
            reason = f'Unknown card type {kind!r}'
        elif kind in ('type', 'sentence', 'gap') and not answer:
            reason = 'Required answer is blank'
        elif kind == 'type' and len(answer.splitlines()) != 1:
            reason = 'Typing comparison requires a single-line answer'
        elif kind == 'gap':
            try:
                gap_answers(question, answer)
            except ValueError as exc:
                reason = str(exc)
        if reason:
            skipped.append({'row': line, 'word': question, 'source': 'input', 'message': reason})
            continue
        key = (kind, normalize_headword(question), question_lang, answer_lang) if kind != 'normal' else (kind, normalize_headword(question))
        if settings['deduplicate'] and key in seen:
            continue
        seen.add(key)
        import re
        tag_list = [re.sub(r'\s+', '_', tag.strip()) for tag in tags.replace('،', ',').split(',') if tag.strip()]
        tag_list = list(dict.fromkeys([options(config, kind)['tag'], *tag_list]))
        records.append(dict(Words=question, Kind=kind, Answer=answer, Meaning=meaning, Tags=tag_list, InputRow=line))
        if settings['max_words'] and len(records) >= settings['max_words']:
            break
    if not records and not skipped:
        raise ConfigError('The selected sheet/column contains no words')
    if any(record['Kind'] != 'normal' for record in records):
        from app.excel_formatting import read_question_formats
        try:
            formats = read_question_formats(config, records, position)
        except Exception as exc:
            raise ConfigError(f'Cannot read Excel prompt formatting: {exc}') from exc
        for record in records:
            if record['InputRow'] in formats:
                record['QuestionRuns'] = formats[record['InputRow']]
    if any(record['Meaning'] for record in records):
        from app.excel_formatting import read_question_formats
        try:
            formats = read_question_formats(config, records, position + 4, field='Meaning', include_normal=True)
        except Exception as exc:
            raise ConfigError(f'Cannot read Excel meaning formatting: {exc}') from exc
        for record in records:
            if record['InputRow'] in formats:
                record['MeaningRuns'] = formats[record['InputRow']]
    if settings.get('order', 'excel') == 'random':
        import random
        random.shuffle(records)
    return records, skipped


def identity(row, config):
    qlang, alang = language_settings(config)
    content = '\0'.join((row['Kind'], qlang, alang, normalize_headword(row['Words'])))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def meaning_html(row, config=None):
    """Optional personal meaning, independent of dictionary caching and note IDs."""
    if (config is not None and not config.data.get('meaning', {}).get('enabled', True)) or not row.get('Meaning', '').strip():
        return ''
    from app.excel_formatting import formatted_question
    text = formatted_question({'Words': row['Meaning'], 'QuestionRuns': row.get('MeaningRuns')})
    return ('<div class="gt-container custom-meaning-container"><div class="gt-title">meaning</div>'
            '<hr class="gt-separator"><div class="source-content" dir="auto">' + text + '</div></div>')


def cached_exercise_audio(text, language, ctx):
    """Return only an existing valid TTS file; never generate or request audio."""
    spoken = 'no' if language in ('nb', 'nn') else language
    path = ctx.audio_dir / audio_filename(text, 'google_tts', spoken)
    if ctx.config.section('audio')['cache'] and path.is_file():
        data = path.read_bytes()
        if len(data) >= 128 and (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
            return ctx.register_audio(path)
    return ''


def exercise_audio(text, language, ctx):
    """TTS cache is keyed by text AND spoken language; no dictionary lookup."""
    cached = cached_exercise_audio(text, language, ctx)
    if cached:
        return cached
    from gtts import gTTS
    spoken = 'no' if language in ('nb', 'nn') else language
    path = ctx.audio_dir / audio_filename(text, 'google_tts', spoken)
    buffer = BytesIO()
    gTTS(text=text, lang=spoken, timeout=ctx.timeout).write_to_fp(buffer)
    data = buffer.getvalue()
    if len(data) < 128 or not (data.startswith(b'ID3') or (data[0] == 255 and data[1] & 224 == 224)):
        raise ValueError('TTS response is not an MP3')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return ctx.register_audio(path)


def render_exercise(row, config):
    kind = row['Kind']
    settings = options(config, kind)
    qlang, alang = language_settings(config)
    qname, aname = language_name(config, qlang), language_name(config, alang)
    instruction = settings['instruction'].format(question_language=qname, answer_language=aname)
    label = f'{qname} → {aname}' if kind in ('type', 'sentence') else aname
    from app.excel_formatting import formatted_question
    question = formatted_question(row)
    if kind == 'gap':
        number = 0
        def input_box(match):
            nonlocal number
            number += 1
            return (f'<input class="exercise-gap exercise-gap-entry" aria-label="Answer {number}" '
                    f'dir="{direction(alang)}" lang="{alang}" autocomplete="off" '
                    'autocapitalize="off" spellcheck="false" placeholder="…">')
        question = formatted_question(row, input_box)
    lang = qlang if kind in ('type', 'sentence') else alang
    header = ('<div class="gt-container exercise-container" dir="ltr">'
              f'<div class="gt-title">{html.escape(settings["title"])}</div>'
              f'<div class="exercise-language">{html.escape(label)}</div><hr class="gt-separator">'
              f'<div class="exercise-instruction">{html.escape(instruction)}</div>')
    if kind == 'listen':
        body = '<div class="exercise-audio">' + row.get('Sound', '') + '</div><div class="exercise-hint">Listen, then repeat aloud.</div>'
    else:
        gap_class = ' exercise-gap-text' if kind == 'gap' else ''
        alignment = f' style="text-align: {"right" if direction(lang) == "rtl" else "left"};"' if kind == 'gap' else ''
        body = f'<div class="exercise-question{gap_class}" dir="{direction(lang)}" lang="{lang}"{alignment}>{question}</div>'
        if kind == 'sentence':
            body += '<div class="exercise-hint">Say your answer aloud.</div>'
    row['FrontField'] = header + body + '</div>'
    if kind == 'type':
        row['FrontField'] = row['FrontField'].replace('dir="ltr">', f'dir="ltr" data-answer-direction="{direction(alang)}">', 1)
    answer = row['Words'] if kind == 'listen' else row['Answer']
    if kind == 'gap':
        answer = complete_gap(row['Words'], row['Answer'])
    answer_html = complete_gap(row['Words'], row['Answer'], markup=True) if kind == 'gap' else html.escape(answer).replace('\n', '<br>')
    gap_class = ' exercise-gap-text' if kind == 'gap' else ''
    alignment = f' style="text-align: {"right" if direction(alang) == "rtl" else "left"};"' if kind == 'gap' else ''
    back = (f'<div class="gt-container exercise-container"><div class="exercise-answer{gap_class}" dir="{direction(alang)}" lang="{alang}"{alignment}>'
            + answer_html + '</div>')
    if kind == 'listen' and row['Answer']:
        back += f'<div class="exercise-meaning" dir="{direction(qlang)}">{html.escape(row["Answer"]).replace(chr(10), "<br>")}</div>'
    # FrontSide does not replay front audio on the back; repeat it explicitly.
    back += '<div class="exercise-audio">' + row.get('Sound', '') + '</div></div>'
    row['BackField'] = meaning_html(row, config) + back
    row['Identity'] = identity(row, config)
    row['AnswerDirection'] = direction(alang)
    return row
