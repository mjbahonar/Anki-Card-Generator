"""Run report: one A4 PDF (summary, every word, every setting) and a PNG of the summary page.

Enabled with "report" in output.formats. The page is plain HTML/CSS rendered by the
Playwright Chromium the dictionaries already use, so no extra dependency is needed.
"""
from datetime import datetime
import html
from pathlib import Path

from app import __version__

EMPTY_MESSAGE = 'No exact entry/content received'

STATUS_LABELS = {
    'COMPLETED': ('Completed', 'ok'),
    'COMPLETED WITH WARNINGS': ('Completed with warnings', 'warn'),
    'PARTIAL': ('Stopped early — partial results saved', 'warn'),
    'FAILED': ('Failed', 'bad'),
}


def form_base(content):
    """Base words named by "gikk → gå" notes: the result is an indirect translation."""
    from app.dictionary_cache import indirect_bases
    return indirect_bases(content)


def word_outcomes(words, rows, sources):
    """Per word and dictionary: found / form / not_found / empty / failed, plus cache and audio."""
    normal_rows = iter(row for row in rows if row.get('Kind', 'normal') == 'normal')
    outcomes = []
    for record in words:
        row = next(normal_rows, {}) if record['kind'] == 'normal' else {}
        cells = {}
        for name in sources:
            result = record['sources'].get(name)
            if result is None:
                cells[name] = {'state': 'none'}
                continue
            if result['status'] == 'OK':
                bases = form_base(row.get(name, '')) if name == 'lexin' else []
                cells[name] = {'state': 'form' if bases else 'found', 'bases': bases, 'cached': result['cached']}
            elif result['status'] == 'FAIL':
                cells[name] = {'state': 'failed', 'detail': result['detail'], 'cached': False}
            else:
                cells[name] = {'state': 'not_found' if result['not_found'] else 'empty',
                               'cached': result['cached'], 'detail': result['detail']}
        outcomes.append({**record, 'cells': cells})
    return outcomes


def summarize(outcomes, sources, input_skips, errors):
    normal = [o for o in outcomes if o['kind'] == 'normal']
    found = [o for o in normal if any(c['state'] in ('found', 'form') for c in o['cells'].values())]
    per_source = {}
    for name in sources:
        states = [o['cells'][name]['state'] for o in normal if name in o['cells']]
        per_source[name] = {state: states.count(state) for state in ('found', 'form', 'not_found', 'empty', 'failed')}
        per_source[name]['cached'] = sum(1 for o in normal if o['cells'].get(name, {}).get('cached'))
        per_source[name]['total'] = len([s for s in states if s != 'none'])
    issues = [e for e in errors if e.get('message') != EMPTY_MESSAGE]
    return {
        'processed': len(outcomes), 'normal': len(normal), 'exercises': len(outcomes) - len(normal),
        'found': len(found), 'via_form': sum(1 for o in normal if any(c['state'] == 'form' for c in o['cells'].values())),
        'not_found': sum(1 for o in normal if o['cells'] and all(c['state'] in ('not_found', 'empty') for c in o['cells'].values())),
        'failed': sum(1 for o in normal if any(c['state'] == 'failed' for c in o['cells'].values())),
        'cached': sum(1 for o in normal if o['cells'] and all(c.get('cached') for c in o['cells'].values() if c['state'] != 'none')),
        'audio': sum(1 for o in outcomes if o['audio']), 'saved': sum(1 for o in outcomes if o['saved']),
        'skipped_rows': len(input_skips), 'issues': issues, 'per_source': per_source,
    }


# ------------------------------------------------------------------ HTML

def _e(value):
    return html.escape(str(value))


def _value(value):
    if isinstance(value, bool):
        return '<span class="v-bool %s">%s</span>' % ('on' if value else 'off', 'true' if value else 'false')
    if isinstance(value, (list, tuple)):
        return ''.join(f'<span class="v-chip">{_e(v)}</span>' for v in value) or '<span class="v-muted">[ ]</span>'
    if isinstance(value, dict):
        return ''.join(f'<div class="v-pair"><span class="v-key">{_e(k)}</span> {_value(v)}</div>' for k, v in value.items())             or '<span class="v-muted">{ }</span>'
    if value == '':
        return '<span class="v-muted">(blank)</span>'
    return _e(value)


def _settings_html(data):
    blocks = []

    def table(path, values):
        rows = ''.join(f'<tr><th>{_e(k)}</th><td>{_value(v)}</td></tr>'
                       for k, v in values.items() if not isinstance(v, dict) or not v or not all(isinstance(x, dict) for x in v.values()))
        if rows:
            blocks.append(f'<div class="set-block"><h4>[{_e(path)}]</h4><table>{rows}</table></div>')
        for key, value in values.items():
            if isinstance(value, dict) and value and all(isinstance(x, dict) for x in value.values()):
                for sub, sub_values in value.items():
                    table(f'{path}.{key}.{sub}', sub_values)
            elif isinstance(value, dict) and value and any(isinstance(x, dict) for x in value.values()):
                table(f'{path}.{key}', value)

    for section, values in data.items():
        if isinstance(values, dict):
            if section in ('sources', 'cards'):
                for name, sub in values.items():
                    table(f'{section}.{name}', sub if isinstance(sub, dict) else {'value': sub})
            else:
                table(section, values)
    return ''.join(blocks)


CELL = {
    'found': ('✓', 'found', 'Found'),
    'form': ('↪', 'form', 'Indirect: inflected form of'),
    'not_found': ('✕', 'nf', 'Not in dictionary'),
    'empty': ('–', 'empty', 'Empty'),
    'failed': ('!', 'fail', 'Failed'),
    'none': ('', 'none', ''),
}


def _cell(cell):
    symbol, css, title = CELL[cell['state']]
    text = symbol
    if cell['state'] == 'form':
        text += ' ' + _e(', '.join(cell['bases']))
    cached = ' <span class="cache" title="From cache">⟲</span>' if cell.get('cached') else ''
    tip = title + (': ' + cell['detail'] if cell.get('detail') and cell['state'] == 'failed' else '')
    return f'<td class="st {css}" title="{_e(tip)}">{text}{cached}</td>'


def build_html(config, summary, outcomes, sources, status, started_at, elapsed, paths, input_skips):
    data = config.data
    section = config.section
    label, tone = STATUS_LABELS.get(status, (status.title(), 'warn'))
    source_titles = {}
    try:
        from app.sources import SOURCE_SPECS
        source_titles = {name: SOURCE_SPECS[name].title for name in sources if name in SOURCE_SPECS}
    except Exception:
        pass
    inp = section('input')
    first, last = inp.get('first_row', 0), inp.get('last_row', 0)
    rows_text = 'all rows' if not first and not last else f'rows {first or 1}–{last or "end"}'
    minutes, seconds = divmod(int(elapsed or 0), 60)
    duration = f'{minutes} min {seconds:02d} s' if minutes else f'{seconds} s'
    total_normal = max(summary['normal'], 1)
    pct = lambda n: round(100 * n / total_normal)  # noqa: E731

    tiles = [
        ('Words processed', summary['processed'], f"{summary['normal']} vocabulary · {summary['exercises']} exercises", 'accent'),
        ('Found', summary['found'], f"{pct(summary['found'])}% of vocabulary words", 'ok'),
        ('Indirect', summary['via_form'], 'via inflected form, e.g. gikk → gå', 'form'),
        ('Not found', summary['not_found'], 'in any enabled dictionary', 'nf'),
        ('Failed lookups', summary['failed'], 'network, timeout or browser', 'bad'),
        ('With audio', summary['audio'], f"{summary['processed'] - summary['audio']} without", 'plain'),
        ('From cache', summary['cached'], 'no network needed', 'plain'),
        ('Skipped rows', summary['skipped_rows'], 'invalid Excel rows', 'plain'),
    ]
    tiles_html = ''.join(f'<div class="tile {tone_}"><span class="t-label">{_e(name)}</span>'
                         f'<strong>{value}</strong><span class="t-sub">{_e(sub)}</span></div>'
                         for name, value, sub, tone_ in tiles)

    bars = []
    for name in sources:
        stats = summary['per_source'][name]
        total = max(stats['total'], 1)
        parts = ''.join(f'<span class="seg {css}" style="width:{100 * stats[key] / total:.2f}%"></span>'
                        for key, css in (('found', 'found'), ('form', 'form'), ('not_found', 'nf'),
                                         ('empty', 'empty'), ('failed', 'fail')) if stats[key])
        legend = ' · '.join(f'{stats[key]} {text}' for key, text in (('found', 'found'), ('form', 'indirect'),
                            ('not_found', 'not found'), ('empty', 'empty'), ('failed', 'failed')) if stats[key])
        bars.append(f'<div class="bar-row"><div class="bar-name">{_e(source_titles.get(name, name))}</div>'
                    f'<div class="bar">{parts}</div><div class="bar-legend">{_e(legend or "no lookups")}'
                    f'{" · %d cached" % stats["cached"] if stats["cached"] else ""}</div></div>')

    meta = [
        ('Workbook', f"{Path(str(inp['file'])).name} · sheet {inp['sheet']} · {rows_text}"),
        ('Languages', f"{section('language')['source']} → {section('language')['translation_target']}"
                      f" · exercises {data.get('practice', {}).get('question_language', '')} → {data.get('practice', {}).get('answer_language', '')}"),
        ('Anki deck', f"{section('anki')['deck_name']} · ID {section('anki')['deck_id']}"),
        ('Dictionaries', ', '.join(source_titles.get(n, n) for n in sources) or 'none'),
        ('Started', started_at.strftime('%Y-%m-%d %H:%M')),
        ('Duration', duration),
        ('Order', f"{inp.get('order', 'excel')}{' · max ' + str(inp['max_words']) if inp.get('max_words') else ''}"),
        ('Version', f'Anki Card Generator v{__version__}'),
    ]
    meta_html = ''.join(f'<div><span>{_e(k)}</span><b>{_e(v)}</b></div>' for k, v in meta)
    outputs = ''.join(f'<li>{_e(Path(p).name)}</li>' for p in paths) or '<li>—</li>'

    head_cells = ''.join(f'<th class="src">{_e(source_titles.get(n, n).split(" ·")[0])}</th>' for n in sources)
    word_rows = []
    for o in outcomes:
        kind = '' if o['kind'] == 'normal' else f'<span class="kind">{_e(o["kind"])}</span>'
        cells = ''.join(_cell(o['cells'].get(n, {'state': 'none'})) for n in sources) if o['kind'] == 'normal' \
            else f'<td class="st none" colspan="{len(sources)}">{_e(o["note"] or "exercise card")}</td>'
        word_rows.append(f'<tr class="{"skipped" if not o["saved"] else ""}"><td class="num">{o["number"]}</td>'
                         f'<td class="w">{_e(o["word"])}{kind}</td>{cells}'
                         f'<td class="st {"found" if o["audio"] else "empty"}">{"♪" if o["audio"] else "–"}</td></tr>')

    issues = summary['issues']
    issue_rows = ''.join(f'<tr><td>{_e(i.get("word", ""))}</td><td>{_e(i.get("source", ""))}</td><td>{_e(i.get("message", ""))[:220]}</td></tr>'
                         for i in issues[:60])
    issues_html = (f'<h3>Issues <small>{len(issues)}</small></h3><table class="issues"><thead><tr><th>Word</th><th>Source</th>'
                   f'<th>Message</th></tr></thead><tbody>{issue_rows}</tbody></table>'
                   + (f'<p class="muted">… and {len(issues) - 60} more (see the _errors.json file).</p>' if len(issues) > 60 else '')
                   if issues else '<h3>Issues</h3><p class="muted">No issues.</p>')
    skipped_html = ''.join(f'<li>Excel row {_e(s.get("row"))}: {_e(s.get("word", ""))} — {_e(s.get("message", ""))}</li>'
                           for s in input_skips[:40])

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Run report</title>
<style>{CSS}</style></head><body>
<section class="summary">
  <header class="hero">
    <div class="brand"><div class="logo"><i></i><i></i></div><div><div class="app">Anki Card Generator</div><h1>Run report</h1></div></div>
    <div class="status {tone}">{_e(label)}</div>
  </header>
  <div class="meta">{meta_html}</div>
  <div class="tiles">{tiles_html}</div>
  <h3>Dictionaries</h3>
  <div class="bars">{''.join(bars) or '<p class="muted">No dictionary lookups in this run.</p>'}</div>
  <div class="legend"><span class="sw found"></span>Found (direct) <span class="sw form"></span>Indirect (inflected form)
    <span class="sw nf"></span>Not in dictionary <span class="sw empty"></span>Empty <span class="sw fail"></span>Failed</div>
  <div class="two">
    <div><h3>Output files</h3><ul class="files">{outputs}</ul></div>
    <div><h3>Notes</h3><ul class="files">{skipped_html or '<li>No skipped Excel rows.</li>'}</ul></div>
  </div>
  <footer class="sumfoot">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {_e(Path(str(config.path)).name)}</footer>
</section>
<section class="page">
  <h2>Words <small>{len(outcomes)}</small></h2>
  <p class="muted">✓ found (direct) · ↪ indirect: inflected form of the base word shown · ✕ not in the dictionary · – empty · ! failed · ⟲ from cache · ♪ audio</p>
  <table class="words"><thead><tr><th class="num">#</th><th>Word</th>{head_cells}<th class="src">Audio</th></tr></thead>
  <tbody>{''.join(word_rows)}</tbody></table>
</section>
<section class="page">{issues_html}</section>
<section class="page">
  <h2>Settings</h2>
  <p class="muted">Everything in {_e(Path(str(config.path)).name)} for this run.</p>
  <div class="settings">{_settings_html(data)}</div>
</section>
</body></html>"""


CSS = """
@page { size: A4; margin: 14mm 13mm 16mm; }
* { box-sizing: border-box; }
html, body { margin: 0; }
body { font: 10.5pt/1.45 "Segoe UI", "Inter", system-ui, -apple-system, Roboto, sans-serif; color: #1c2033; }
h1, h2, h3, h4 { margin: 0; letter-spacing: -.01em; }
h2 { font-size: 17pt; margin-bottom: 4px; }
h2 small, h3 small { font-size: .6em; color: #6b7189; font-weight: 600; margin-left: 6px; }
h3 { font-size: 11.5pt; margin: 18px 0 8px; }
.muted { color: #6b7189; font-size: 9pt; margin: 4px 0 10px; }
.page { break-before: page; }
.summary { padding: 0; }
.hero { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 18px 20px;
  border-radius: 16px; color: #fff; background: linear-gradient(120deg, #4f46e5, #7c3aed 55%, #db2777); }
.brand { display: flex; align-items: center; gap: 14px; }
.logo { position: relative; width: 40px; height: 40px; }
.logo i { position: absolute; width: 25px; height: 30px; border-radius: 7px; }
.logo i:first-child { left: 2px; top: 8px; background: rgba(255,255,255,.95); }
.logo i:last-child { left: 13px; top: 1px; background: rgba(255,255,255,.45); border: 1px solid rgba(255,255,255,.8); }
.app { font-size: 9pt; opacity: .85; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.hero h1 { font-size: 22pt; font-weight: 750; }
.status { padding: 6px 14px; border-radius: 99px; font-weight: 700; font-size: 10pt; background: rgba(255,255,255,.18);
  border: 1px solid rgba(255,255,255,.45); white-space: nowrap; }
.status::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; }
.status.ok::before { background: #4ade80; } .status.warn::before { background: #fbbf24; } .status.bad::before { background: #f87171; }
.meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 22px; margin: 14px 4px 4px; font-size: 9.5pt; }
.meta div { display: flex; gap: 8px; border-bottom: 1px solid #eceef5; padding: 4px 0; min-width: 0; }
.meta span { color: #6b7189; width: 86px; flex: none; }
.meta b { font-weight: 600; overflow-wrap: anywhere; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin-top: 14px; }
.tile { border: 1px solid #e4e7ef; border-radius: 12px; padding: 10px 12px; display: grid; gap: 1px; background: #fafbfe;
  border-top: 4px solid #cfd3e3; }
.tile strong { font-size: 21pt; font-weight: 750; letter-spacing: -.02em; line-height: 1.15; }
.t-label { color: #4b5066; font-weight: 650; font-size: 8.5pt; }
.t-sub { color: #8a8fa6; font-size: 7.8pt; }
.tile.accent { border-top-color: #5b5bd6; } .tile.ok { border-top-color: #16a34a; } .tile.form { border-top-color: #0ea5e9; }
.tile.nf { border-top-color: #f59e0b; } .tile.bad { border-top-color: #dc2626; }
.bars { display: grid; gap: 9px; }
.bar-row { display: grid; grid-template-columns: 200px 1fr; gap: 3px 12px; align-items: center; }
.bar-name { font-weight: 650; font-size: 9.5pt; }
.bar { height: 14px; border-radius: 99px; background: #eef0f6; overflow: hidden; display: flex; }
.seg { height: 100%; }
.bar-legend { grid-column: 2; color: #6b7189; font-size: 8.3pt; }
.found { --c: #16a34a; } .form { --c: #0ea5e9; } .nf { --c: #f59e0b; } .empty { --c: #a3a8bd; } .fail { --c: #dc2626; }
.seg, .sw { background: var(--c); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: center; margin-top: 10px; font-size: 8.5pt; color: #4b5066; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: -9px; vertical-align: -1px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.files { margin: 0; padding-left: 16px; font-size: 8.8pt; color: #3a3f55; }
.files li { margin: 2px 0; overflow-wrap: anywhere; }
.sumfoot { margin-top: 16px; padding-top: 8px; border-top: 1px solid #eceef5; color: #8a8fa6; font-size: 8pt; }
table { width: 100%; border-collapse: collapse; }
.words { font-size: 9pt; }
.words thead { display: table-header-group; }
.words th { text-align: left; font-size: 8pt; color: #6b7189; text-transform: uppercase; letter-spacing: .04em;
  border-bottom: 1.5px solid #d9dce8; padding: 6px 6px; }
.words td { padding: 4px 6px; border-bottom: 1px solid #eef0f5; vertical-align: top; }
.words tr { break-inside: avoid; }
.words tbody tr:nth-child(even) td { background: #fafbfe; }
.words .num { width: 34px; color: #8a8fa6; text-align: right; }
.words .w { font-weight: 600; }
.words .src { text-align: left; }
.st { white-space: nowrap; font-weight: 650; color: var(--c, #a3a8bd); }
.st.none { color: #8a8fa6; font-weight: 400; font-style: italic; }
.cache { color: #8a8fa6; font-weight: 400; font-size: .9em; }
.kind { margin-left: 6px; font-size: 7.5pt; font-weight: 650; color: #5b5bd6; background: #ececfd; border-radius: 99px; padding: 1px 6px; }
tr.skipped .w { text-decoration: line-through; color: #8a8fa6; }
.issues { font-size: 8.5pt; }
.issues th { text-align: left; color: #6b7189; border-bottom: 1.5px solid #d9dce8; padding: 5px; }
.issues td { padding: 4px 5px; border-bottom: 1px solid #eef0f5; vertical-align: top; overflow-wrap: anywhere; }
.settings { columns: 2; column-gap: 18px; }
.set-block { break-inside: avoid; margin: 0 0 12px; border: 1px solid #e4e7ef; border-radius: 10px; padding: 8px 10px; background: #fcfcfe; }
.set-block h4 { font: 700 8.8pt/1.3 "Cascadia Code", Consolas, monospace; color: #5b5bd6; margin-bottom: 4px; }
.set-block table { font-size: 8.3pt; }
.set-block th { text-align: left; font-weight: 600; color: #4b5066; padding: 2px 8px 2px 0; width: 44%; vertical-align: top; overflow-wrap: anywhere; }
.set-block td { padding: 2px 0; overflow-wrap: anywhere; }
.v-bool { font-weight: 700; } .v-bool.on { color: #16a34a; } .v-bool.off { color: #a3a8bd; }
.v-chip { display: inline-block; margin: 0 3px 2px 0; padding: 0 6px; border-radius: 99px; background: #eef0f8; font-size: 7.8pt; }
.v-muted { color: #a3a8bd; } .v-code { font-family: Consolas, monospace; font-size: 7.8pt; }
.v-pair { margin: 0 0 2px; } .v-key { font-family: Consolas, monospace; font-size: 7.8pt; color: #4b5066; margin-right: 4px; }
@media screen { body { width: 850px; background: #fff; } .summary { padding: 26px; background: #fff; } .page { padding: 26px; } }
"""


def write_report(config, console_report, rows, input_skips, errors, paths, failures, partial, stem, sources):
    """Write <stem>_report.pdf and <stem>_report.png into the output folder; returns their paths."""
    status = console_report.status(rows, errors, failures, partial)
    outcomes = word_outcomes(console_report.words, rows, sources)
    summary = summarize(outcomes, sources, input_skips, errors)
    import time
    elapsed = time.monotonic() - console_report.started
    output = config.resolve(config.section('output')['directory'])
    output.mkdir(parents=True, exist_ok=True)
    pdf, png = output / f'{stem}_report.pdf', output / f'{stem}_report.png'
    page_html = build_html(config, summary, outcomes, sources, status, console_report.started_at, elapsed,
                           [*paths, pdf, png], input_skips)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 850, 'height': 1200}, device_scale_factor=2)
            page.set_content(page_html, wait_until='load')
            page.locator('section.summary').screenshot(path=str(png))
            page.emulate_media(media='print')
            page.pdf(path=str(pdf), format='A4', print_background=True, display_header_footer=True,
                     header_template='<span></span>',
                     footer_template='<div style="width:100%;font:8px Segoe UI,sans-serif;color:#8a8fa6;padding:0 13mm;'
                                     'display:flex;justify-content:space-between"><span>Anki Card Generator · run report</span>'
                                     '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
                     margin={'top': '14mm', 'bottom': '16mm', 'left': '13mm', 'right': '13mm'})
        finally:
            browser.close()
    return [pdf, png]
