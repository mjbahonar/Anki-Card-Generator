'use strict';
// Settings GUI for config.toml. All interface text comes from app/gui/i18n.py.

const $ = (selector) => document.querySelector(selector);
const state = {
  token: '', lang: localStorage.getItem('gui.lang') || 'en', strings: {}, info: null,
  schema: null, fields: new Map(), baseline: new Map(), values: new Map(), invalid: new Set(),
  order: [], baseOrder: [], decks: [], baseDecks: [], tab: localStorage.getItem('gui.tab') || 'languages', open: new Set(),
  job: { running: false }, logNext: 0, poller: null, busy: false,
};

const ICONS = {
  languages: '<path d="M3 5h12M9 3v2m1.5 0c-1 4-3.5 7-6.5 8.5M6 9c1.2 2 3.2 3.6 5.5 4.5"/><path d="M13 21l4-9 4 9m-6.8-3h5.6"/>',
  input: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 3v18"/>',
  dictionaries: '<path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v17H7.5A2.5 2.5 0 0 0 5 21.5z"/><path d="M5 19.5V4.5M9 7h6M9 11h4"/>',
  cards: '<rect x="3" y="6" width="13" height="15" rx="2"/><path d="M8 3h11a2 2 0 0 1 2 2v12"/>',
  audio: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
  output: '<path d="M12 3v12m0 0-4-4m4 4 4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
  appearance: '<circle cx="12" cy="12" r="9"/><circle cx="8.5" cy="10" r="1.2"/><circle cx="12" cy="7.5" r="1.2"/><circle cx="15.5" cy="10" r="1.2"/><path d="M12 21a2.5 2.5 0 0 1 0-5h2a3 3 0 0 0 3-3"/>',
  advanced: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  other: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
};
const CHEVRON_UP = '<svg viewBox="0 0 24 24"><path d="m6 15 6-6 6 6"/></svg>';
const CHEVRON_DOWN = '<svg viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>';

// ---------------------------------------------------------------- helpers
function t(key, vars = {}, fallback) {
  let text = state.strings[key] ?? fallback ?? key;
  for (const [name, value] of Object.entries(vars)) text = text.replaceAll('{' + name + '}', value);
  return text;
}
const dotted = (path) => path.join('.');
const humanize = (key) => key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const clone = (value) => (Array.isArray(value) ? [...value] : value);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value; // Only used for built-in icons.
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child);
  return node;
}
function fieldLabel(field) {
  return t('field.' + dotted(field.path), {}, state.strings['field.' + field.key] ?? humanize(field.key));
}
function groupTitle(group) {
  const id = dotted(group.path);
  if (group.path[0] === 'sources') return t('source.' + group.path[1], {}, humanize(group.path[1]));
  return t('group.' + id, {}, humanize(group.path[group.path.length - 1] || 'Settings'));
}

async function api(method, url, body) {
  let response;
  try {
    response = await fetch(url, {
      method, headers: { 'X-GUI-Token': state.token, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw { status: 0, error: t('error.network') };
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw { status: response.status, error: data.error || response.statusText };
  return data;
}

function banner(kind, text) {
  const node = $('#banner');
  node.hidden = !text;
  node.className = 'banner ' + kind;
  node.textContent = text || '';
}

function confirmBox(text) {
  const dialog = $('#confirm');
  $('#confirm-text').textContent = text;
  dialog.showModal();
  return new Promise((resolve) => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true }));
}

// ---------------------------------------------------------------- state
function changedPaths() {
  return [...state.values.keys()].filter((key) => !same(state.values.get(key), state.baseline.get(key)));
}
function orderChanged() { return !same(state.order, state.baseOrder); }
function decksChanged() { return !same(state.decks, state.baseDecks); }
function dirtyCount() { return changedPaths().length + (orderChanged() ? 1 : 0) + (decksChanged() ? 1 : 0); }
function tabDirty(tab) {
  const changed = new Set(changedPaths());
  return tab.groups.some((g) => g.fields.some((f) => changed.has(dotted(f.path))))
    || (tab.id === 'dictionaries' && orderChanged())
    || (tab.groups.some((g) => dotted(g.path) === 'anki') && decksChanged());
}

function setValue(field, value) {
  state.values.set(dotted(field.path), value);
  refreshChrome();
}

async function load(keepBanner = false) {
  const info = await api('GET', '/api/state?lang=' + encodeURIComponent(state.lang));
  state.info = info;
  state.strings = info.strings;
  const meta = info.strings._meta || { dir: 'ltr' };
  document.documentElement.dir = meta.dir;
  document.documentElement.lang = state.lang;
  document.title = t('app.title') + ' — ' + t('app.subtitle');
  document.querySelectorAll('[data-t]').forEach((node) => { node.textContent = t(node.dataset.t); });
  $('#version').textContent = 'v' + info.app_version;
  $('#config-path').textContent = info.config_path;

  const picker = $('#language');
  picker.replaceChildren(...info.languages.map((l) => el('option', { value: l.code, text: l.name, selected: l.code === state.lang })));
  $('#language-picker').hidden = info.languages.length < 2;

  state.schema = info.schema;
  info.schema.tabs.push({ id: 'database', groups: [] }); // Cache browser; not part of config.toml.
  state.fields.clear(); state.baseline.clear(); state.values.clear(); state.invalid.clear();
  for (const tab of info.schema.tabs) for (const group of tab.groups) for (const field of group.fields) {
    const key = dotted(field.path);
    state.fields.set(key, field);
    state.baseline.set(key, clone(field.value));
    state.values.set(key, clone(field.value));
  }
  state.order = [...info.schema.sources_order];
  state.baseOrder = [...info.schema.sources_order];
  state.baseDecks = info.schema.decks.map((d) => [...d]);
  state.decks = info.schema.decks.map((d) => [...d]);
  const active = [state.values.get('anki.deck_name'), state.values.get('anki.deck_id')];
  // A deck in use but not in the saved list is added, and stored on the next save.
  if (active[0] !== undefined && !state.decks.some((d) => same(d, active))) state.decks.unshift(active);
  if (!info.schema.tabs.some((tab) => tab.id === state.tab)) state.tab = info.schema.tabs[0].id;
  if (!keepBanner) banner('', '');
  render();
  if (info.job && info.job.running && !state.poller) { state.logNext = 0; $('#log').textContent = ''; poll(); }
}

// ---------------------------------------------------------------- rendering
function render() { renderTabs(); renderPage(); refreshChrome(); }

function renderTabs() {
  const nav = $('#tabs');
  nav.replaceChildren(...state.schema.tabs.map((tab) => {
    let extra = null;
    if (tabDirty(tab)) extra = el('span', { class: 'changed', title: t('status.unsaved', { count: '' }) });
    else if (tab.id === 'dictionaries') {
      const on = state.order.filter((k) => state.values.get('sources.' + k + '.enabled')).length;
      extra = el('span', { class: 'count', text: String(on) });
    }
    return el('button', {
      class: 'tab', role: 'tab', 'aria-selected': String(tab.id === state.tab),
      onclick: () => { state.tab = tab.id; localStorage.setItem('gui.tab', tab.id); render(); window.scrollTo(0, 0); },
    }, el('span', { html: `<svg viewBox="0 0 24 24">${ICONS[tab.id] || ICONS.other}</svg>`, style: 'display:contents' }),
    el('span', { text: t('tab.' + tab.id, {}, humanize(tab.id)) }), extra);
  }));
}

function renderPage() {
  const tab = state.schema.tabs.find((item) => item.id === state.tab);
  $('#page-title').textContent = t('tab.' + tab.id, {}, humanize(tab.id));
  $('#page-desc').textContent = t('tab.' + tab.id + '.desc', {}, '');
  const page = $('#page');
  if (tab.id === 'dictionaries') page.replaceChildren(renderSources(tab));
  else if (tab.id === 'database') page.replaceChildren(renderDatabase());
  else page.replaceChildren(...tab.groups.map(renderGroup));
}

function renderGroup(group) {
  if (dotted(group.path) === 'anki') return renderDecks(group);
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', { text: groupTitle(group) }),
      group.help ? el('span', { class: 'hint', text: group.help }) : null),
    el('div', { class: 'card-body' }, group.fields.map(renderField)));
}

function renderField(field) {
  const key = dotted(field.path);
  const id = 'f-' + key.replace(/[^a-z0-9]+/gi, '-');
  const help = t('help.' + key, {}, field.help);
  const row = el('div', { class: 'field', 'data-key': key },
    el('div', { class: 'field-label' }, el('label', { for: id, text: fieldLabel(field) }), el('span', { class: 'key', text: key })),
    el('div', { class: 'field-control' }, control(field, id)),
    help ? el('div', { class: 'field-help', text: help }) : null);
  return row;
}

function control(field, id) {
  const key = dotted(field.path);
  const value = state.values.get(key);
  switch (field.type) {
    case 'bool':
      return el('label', { class: 'switch' },
        el('input', { id, type: 'checkbox', checked: value, onchange: (e) => setValue(field, e.target.checked) }), el('span'));
    case 'int':
    case 'float':
      return el('input', {
        id, type: 'number', value: String(value), step: field.type === 'int' ? '1' : 'any',
        oninput: (e) => {
          const raw = e.target.value.trim();
          const number = Number(raw);
          const ok = raw !== '' && Number.isFinite(number) && (field.type === 'float' || Number.isInteger(number));
          markInvalid(key, !ok);
          if (ok) setValue(field, number);
        },
      });
    case 'name_or_index':
      return el('input', { id, type: 'text', value, spellcheck: 'false', placeholder: t('field.name_or_index'),
        oninput: (e) => { markInvalid(key, !e.target.value.trim()); setValue(field, e.target.value.trim()); } });
    case 'text':
      return el('textarea', { id, oninput: (e) => setValue(field, e.target.value) }, value);
    case 'raw':
      return el('textarea', {
        id, class: 'code', oninput: (e) => {
          let ok = true;
          try { JSON.parse(e.target.value); } catch { ok = false; }
          markInvalid(key, !ok);
          if (ok) setValue(field, e.target.value);
        },
      }, value);
    case 'list':
      return chips(field);
    default:
      return textControl(field, id, value);
  }
}

function textControl(field, id, value) {
  if (field.mode === 'select') {
    const options = field.options.includes(value) ? field.options : [value, ...field.options];
    return el('select', { id, onchange: (e) => setValue(field, e.target.value) },
      options.map((option) => el('option', { value: option, text: option, selected: option === value })));
  }
  if (field.mode === 'file') return fileControl(field, id, value);
  const suggestions = field.mode === 'suggest' ? field.options : null;
  const input = el('input', { id, type: 'text', value, spellcheck: 'false', oninput: (e) => setValue(field, e.target.value) });
  if (!suggestions || !suggestions.length) return input;
  const listId = id + '-list';
  input.setAttribute('list', listId);
  return el('div', {}, input, el('datalist', { id: listId }, suggestions.map((s) => el('option', { value: s }))));
}

function fileControl(field, id, value) {
  const kind = field.extensions.includes('.css') ? 'style' : 'input';
  const listId = id + '-list';
  const datalist = el('datalist', { id: listId });
  const status = el('span', { class: 'file-status' });
  const fill = (files) => {
    state.info.input_files = files.input_files;
    state.info.style_files = files.style_files;
    const list = kind === 'style' ? files.style_files : files.input_files;
    datalist.replaceChildren(...list.map((s) => el('option', { value: s })));
    status.className = 'file-status ' + (files.exists ? 'ok' : 'bad');
    status.textContent = files.exists ? t('file.found') : t('file.missing');
  };
  const check = async () => {
    try { fill(await api('GET', '/api/files?check=' + encodeURIComponent(input.value))); } catch (e) { status.textContent = e.error; }
  };
  let timer = null;
  const input = el('input', {
    id, type: 'text', value, spellcheck: 'false', list: listId,
    oninput: (e) => { setValue(field, e.target.value); clearTimeout(timer); timer = setTimeout(check, 350); },
  });
  const browse = el('button', { type: 'button', class: 'btn small', text: t('file.browse'), onclick: async () => {
    browse.disabled = true;
    try {
      const result = await api('POST', '/api/browse', { kind, current: input.value });
      if (result.path) { input.value = result.path; setValue(field, result.path); }
      await check();
    } catch (e) { banner('error', e.error); } finally { browse.disabled = false; }
  } });
  const refresh = el('button', { type: 'button', class: 'icon-btn', title: t('file.refresh'), 'aria-label': t('file.refresh'),
    html: '<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>', onclick: check });
  check();
  return el('div', { class: 'file-control' }, el('div', { class: 'file-row' }, input, browse, refresh), datalist, status);
}

function chips(field) {
  const key = dotted(field.path);
  const items = state.values.get(key);
  const update = (next) => { setValue(field, next); rerenderField(field); };
  const wrap = el('div', { class: 'chips' });
  items.forEach((item, index) => {
    wrap.append(el('span', { class: 'chip' },
      field.mode === 'ordered' ? el('span', { class: 'n', text: String(index + 1) }) : null,
      item,
      field.mode === 'ordered' && index > 0 ? el('button', {
        type: 'button', title: t('list.move_left'), 'aria-label': t('list.move_left'), text: '‹',
        onclick: () => { const next = [...items]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; update(next); },
      }) : null,
      el('button', {
        type: 'button', title: t('list.remove'), 'aria-label': t('list.remove') + ' ' + item, text: '✕',
        onclick: () => update(items.filter((_, i) => i !== index)),
      })));
  });
  if (!items.length) wrap.append(el('span', { class: 'empty', text: t('list.empty') }));
  if (field.options) {
    const rest = field.options.filter((option) => !items.includes(option));
    if (rest.length) {
      wrap.append(el('select', {
        'aria-label': t('list.add'),
        onchange: (e) => { if (e.target.value) update([...items, e.target.value]); },
      }, el('option', { value: '', text: t('list.add') }), rest.map((option) => el('option', { value: option, text: option }))));
    }
  } else {
    wrap.append(el('input', {
      type: 'text', placeholder: t('list.add_value'),
      onkeydown: (e) => {
        const text = e.target.value.trim();
        if (e.key === 'Enter' && text) { e.preventDefault(); if (!items.includes(text)) update([...items, text]); }
      },
    }));
  }
  return wrap;
}

function rerenderField(field) {
  const row = document.querySelector(`.field[data-key="${CSS.escape(dotted(field.path))}"]`);
  if (row) row.replaceWith(renderField(field));
  refreshChrome();
}

function markInvalid(key, bad) {
  if (bad) state.invalid.add(key); else state.invalid.delete(key);
  document.querySelector(`.field[data-key="${CSS.escape(key)}"]`)?.classList.toggle('invalid', bad);
  refreshChrome();
}

function renderSources(tab) {
  const groups = new Map(tab.groups.map((g) => [g.path[1], g]));
  const enabledOrder = state.order.filter((k) => state.values.get('sources.' + k + '.enabled'));
  const total = state.order.length;
  const list = el('div', { class: 'sources' },
    el('div', { class: 'summary-pill', text: t('source.enabled_count', { count: enabledOrder.length, total }) }));
  state.order.forEach((name, index) => {
    const group = groups.get(name);
    if (!group) return;
    const enabledField = group.fields.find((f) => f.key === 'enabled');
    const others = group.fields.filter((f) => f !== enabledField);
    const on = enabledField ? state.values.get(dotted(enabledField.path)) : true;
    const open = state.open.has(name);
    const move = (delta) => {
      const next = [...state.order];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      state.order = next;
      render();
    };
    const rank = on ? String(enabledOrder.indexOf(name) + 1) : '–';
    const card = el('div', { class: 'source' + (on ? ' on' : '') },
      el('div', { class: 'source-head' },
        el('span', { class: 'source-rank', text: rank }),
        el('div', { class: 'source-text' },
          el('span', { class: 'source-name', text: groupTitle(group) }),
          enabledField && enabledField.help ? el('span', { class: 'source-desc', text: enabledField.help }) : null),
        el('div', { class: 'source-tools' },
          el('button', { class: 'icon-btn', title: t('source.up'), 'aria-label': t('source.up'), disabled: index === 0, html: CHEVRON_UP, onclick: () => move(-1) }),
          el('button', { class: 'icon-btn', title: t('source.down'), 'aria-label': t('source.down'), disabled: index === total - 1, html: CHEVRON_DOWN, onclick: () => move(1) }),
          others.length ? el('button', {
            class: 'btn ghost small', text: t('source.settings') + (open ? ' ▴' : ' ▾'),
            onclick: () => { if (open) state.open.delete(name); else state.open.add(name); renderPage(); },
          }) : null,
          enabledField ? el('label', { class: 'switch', title: on ? t('source.on') : t('source.off') },
            el('input', { type: 'checkbox', checked: on, 'aria-label': groupTitle(group),
              onchange: (e) => { setValue(enabledField, e.target.checked); render(); } }), el('span')) : null)),
      open && others.length ? el('div', { class: 'source-body' }, others.map(renderField)) : null);
    list.append(card);
  });
  return list;
}

function renderDecks(group) {
  const nameField = state.fields.get('anki.deck_name');
  const idField = state.fields.get('anki.deck_id');
  const active = [state.values.get('anki.deck_name'), state.values.get('anki.deck_id')];
  const use = (deck) => { setValue(nameField, deck[0]); setValue(idField, deck[1]); render(); };
  const picker = el('select', { 'aria-label': t('deck.active'), onchange: (e) => use(state.decks[Number(e.target.value)]) },
    state.decks.map((deck, i) => el('option', { value: String(i), text: deck[0] + '  ·  ' + deck[1], selected: same(deck, active) })));
  const rows = el('div', { class: 'deck-list' }, state.decks.map((deck, i) => {
    const inUse = same(deck, active);
    return el('div', { class: 'deck-row' + (inUse ? ' active' : '') },
      el('span', { class: 'deck-name', text: deck[0] }), el('code', { text: String(deck[1]) }),
      inUse ? el('span', { class: 'badge', text: t('deck.in_use') })
        : el('span', { class: 'deck-actions' },
          el('button', { class: 'btn ghost small', text: t('deck.use'), onclick: () => use(deck) }),
          el('button', { class: 'btn ghost small', text: t('deck.remove'), onclick: async () => {
            if (!(await confirmBox(t('deck.remove_confirm', { name: deck[0] })))) return;
            state.decks = state.decks.filter((_, j) => j !== i);
            render();
          } })));
  }));
  const nextId = Math.max(0, ...state.decks.map((d) => d[1])) + 1;
  const newName = el('input', { type: 'text', placeholder: t('deck.name'), 'aria-label': t('deck.name') });
  const newId = el('input', { type: 'number', value: String(nextId), step: '1', min: '1', 'aria-label': t('deck.id') });
  const add = () => {
    const name = newName.value.trim();
    const id = Number(newId.value);
    if (!name || state.decks.some((d) => d[0] === name)) { banner('error', t('deck.error_name')); return; }
    if (!Number.isSafeInteger(id) || id < 1 || state.decks.some((d) => d[1] === id)) { banner('error', t('deck.error_id')); return; }
    banner('', '');
    state.decks = [...state.decks, [name, id]];
    use([name, id]);
  };
  newName.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
  const row = (title, control, help) => el('div', { class: 'field' },
    el('div', { class: 'field-label' }, el('label', { text: title })), el('div', { class: 'field-control' }, control),
    help ? el('div', { class: 'field-help', text: help }) : null);
  const others = group.fields.filter((f) => f.key !== 'deck_name' && f.key !== 'deck_id');
  const changed = !same(active, [state.baseline.get('anki.deck_name'), state.baseline.get('anki.deck_id')]) || decksChanged();
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', { text: groupTitle(group) }), changed ? el('span', { class: 'changed-dot' }) : null),
    el('div', { class: 'card-body' },
      row(t('deck.active'), picker, t('deck.active_help')),
      row(t('deck.saved'), rows, t('deck.saved_help')),
      row(t('deck.add'), el('div', { class: 'deck-add' }, newName, newId,
        el('button', { class: 'btn', text: t('deck.add_button'), onclick: add })), t('deck.add_help')),
      others.map(renderField)));
}

// ---------------------------------------------------------------- database tab
const db = { q: '', source: '', status: '', rows: [], total: 0, open: new Set(), selected: new Set() };

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return (bytes / 1024 ** i).toFixed(i ? 1 : 0) + ' ' + units[i];
}
const sourceName = (s) => t('source.' + s, {}, humanize(s));

async function dbAction(url, body, confirmText) {
  if (confirmText && !(await confirmBox(confirmText))) return null;
  try {
    const result = await api('POST', url, body || {});
    renderPage();
    return result;
  } catch (error) {
    banner('error', error.error === 'busy' ? t('db.busy') : error.error);
    return null;
  }
}

function renderDatabase() {
  const wrap = el('div', { class: 'db' });
  const statsCard = el('div', { class: 'card' }, el('div', { class: 'card-body db-loading', text: t('db.loading') }));
  const searchCard = el('div', { class: 'card' });
  wrap.append(statsCard, searchCard, renderCacheTools());
  loadStats(statsCard);
  renderSearch(searchCard, true);
  return wrap;
}

async function loadStats(card) {
  let stats;
  try { stats = await api('GET', '/api/db/stats'); } catch (e) { card.replaceChildren(el('div', { class: 'card-body', text: e.error })); return; }
  db.sources = stats.sources.map((s) => s.source);
  const tile = (label, value, sub) => el('div', { class: 'tile' }, el('span', { class: 'tile-label', text: label }),
    el('strong', { text: value }), sub ? el('span', { class: 'tile-sub', text: sub }) : null);
  const audio = stats.media.find((m) => m.kind === 'audio') || { files: 0, bytes: 0 };
  const table = el('table', { class: 'db-table' },
    el('thead', {}, el('tr', {}, [t('db.source'), t('db.results'), t('db.indirect'), t('db.not_found'), t('db.text'), t('db.last_saved'), ''].map((h) => el('th', { text: h })))),
    el('tbody', {}, stats.sources.map((s) => el('tr', {},
      el('td', { text: sourceName(s.source) }), el('td', { text: String(s.results) }),
      el('td', { text: String(s.indirect || 0) }), el('td', { text: String(s.not_found) }), el('td', { text: formatBytes(s.text_bytes) }),
      el('td', { text: s.newest || '' }),
      el('td', {}, s.not_found ? el('button', { class: 'btn ghost small', text: t('db.forget_not_found'),
        disabled: state.job.running,
        onclick: () => dbAction('/api/db/forget_not_found', { source: s.source }, t('db.forget_confirm', { source: sourceName(s.source), count: s.not_found })) }) : null)))));
  card.replaceChildren(
    el('div', { class: 'card-head' }, el('h2', { text: t('db.overview') }), el('span', { class: 'hint', text: stats.path }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost small', text: t('db.refresh'), onclick: () => renderPage() }),
      stats.not_found ? el('button', { class: 'btn ghost small', text: t('db.forget_all_not_found', { count: stats.not_found }),
        disabled: state.job.running,
        onclick: () => dbAction('/api/db/forget_not_found', {}, t('db.forget_all_confirm', { count: stats.not_found })) }) : null,
      el('button', { class: 'btn small', text: t('db.compact'), disabled: state.job.running || !stats.exists, onclick: async () => {
        const result = await dbAction('/api/db/compact', {});
        if (result) banner('ok', t('db.compacted', { before: formatBytes(result.before), after: formatBytes(result.after) }));
      } })),
    stats.exists ? el('div', { class: 'card-body' },
      el('div', { class: 'tiles' },
        tile(t('db.file'), formatBytes(stats.file_bytes)),
        tile(t('db.words'), String(stats.words), t('db.results_n', { count: stats.results })),
        tile(t('db.indirect'), String(stats.indirect || 0), t('db.indirect_sub')),
        tile(t('db.not_found'), String(stats.not_found), t('db.not_found_sub')),
        tile(t('db.audio'), String(audio.files), formatBytes(audio.bytes)),
        tile(t('db.media'), formatBytes(stats.media_bytes), stats.media.map((m) => `${m.kind}: ${m.files}`).join(' · ')),
        tile(t('db.text'), formatBytes(stats.text_bytes), stats.oldest ? t('db.since', { date: stats.oldest.slice(0, 10) }) : '')),
      table)
      : el('div', { class: 'card-body', text: t('db.missing') }));
  const filter = document.querySelector('#db-source');
  if (filter && filter.options.length <= 1) {
    filter.append(...db.sources.map((s) => el('option', { value: s, text: sourceName(s), selected: s === db.source })));
  }
}

async function renderSearch(card, reset) {
  if (reset) { db.rows = []; db.total = 0; }
  const input = el('input', { type: 'search', id: 'db-q', value: db.q, placeholder: t('db.search_placeholder'), 'aria-label': t('db.search') });
  const source = el('select', { id: 'db-source', 'aria-label': t('db.source') }, el('option', { value: '', text: t('db.all_sources') }),
    (db.sources || []).map((s) => el('option', { value: s, text: sourceName(s), selected: s === db.source })));
  const status = el('select', { 'aria-label': t('db.status') }, [['', t('db.all')], ['found', t('db.found')], ['indirect', t('db.indirect')], ['not_found', t('db.not_found')]]
    .map(([v, label]) => el('option', { value: v, text: label, selected: v === db.status })));
  const list = el('div', { class: 'db-rows' });
  const count = el('span', { class: 'hint' });
  const selectAll = el('input', { type: 'checkbox', 'aria-label': t('db.select_all'), title: t('db.select_all') });
  const deleteSelected = el('button', { class: 'btn small danger-text', disabled: true });
  const deleteMatching = el('button', { class: 'btn small danger-text' });
  const updateBulk = () => {
    const shown = db.rows.map((r) => r.key);
    db.selected = new Set([...db.selected].filter((k) => shown.includes(k)));
    deleteSelected.textContent = t('db.delete_selected', { count: db.selected.size });
    deleteSelected.disabled = !db.selected.size || state.job.running;
    selectAll.checked = shown.length > 0 && shown.every((k) => db.selected.has(k));
    selectAll.indeterminate = db.selected.size > 0 && !selectAll.checked;
    deleteMatching.textContent = t('db.delete_matching', { count: db.total });
    deleteMatching.disabled = !db.total || state.job.running;
  };
  db.updateBulk = updateBulk;
  selectAll.addEventListener('change', () => {
    db.selected = selectAll.checked ? new Set(db.rows.map((r) => r.key)) : new Set();
    list.querySelectorAll('.db-check').forEach((box) => { box.checked = selectAll.checked; });
    updateBulk();
  });
  deleteSelected.addEventListener('click', () => dbAction('/api/db/delete', { keys: [...db.selected] },
    t('db.delete_selected_confirm', { count: db.selected.size })).then((r) => { if (r) db.selected.clear(); }));
  deleteMatching.addEventListener('click', () => {
    const filters = [db.q && `"${db.q}"`, db.source && sourceName(db.source),
      db.status && t({ not_found: 'db.not_found', indirect: 'db.indirect', found: 'db.found' }[db.status])].filter(Boolean).join(' · ') || t('db.all');
    dbAction('/api/db/delete_matching', { q: db.q, source: db.source, status: db.status },
      t('db.delete_matching_confirm', { count: db.total, filters }));
  });
  const run = async (more) => {
    db.q = input.value.trim(); db.source = source.value; db.status = status.value;
    const offset = more ? db.rows.length : 0;
    try {
      const result = await api('GET', `/api/db/search?q=${encodeURIComponent(db.q)}&source=${encodeURIComponent(db.source)}&status=${db.status}&offset=${offset}`);
      db.rows = more ? db.rows.concat(result.rows) : result.rows;
      db.total = result.total;
      drawRows();
    } catch (e) { list.replaceChildren(el('div', { class: 'empty', text: e.error })); }
  };
  const drawRows = () => {
    count.textContent = t('db.showing', { shown: db.rows.length, total: db.total });
    list.replaceChildren(...(db.rows.length ? db.rows.map(renderDbRow) : [el('div', { class: 'db-empty', text: t('db.no_rows') })]));
    if (db.rows.length < db.total) list.append(el('button', { class: 'btn ghost', text: t('db.more'), onclick: () => run(true) }));
    updateBulk();
  };
  let timer = null;
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => run(false), 300); });
  source.addEventListener('change', () => run(false));
  status.addEventListener('change', () => run(false));
  card.replaceChildren(
    el('div', { class: 'card-head' }, el('h2', { text: t('db.search') }), count),
    el('div', { class: 'card-body' }, el('div', { class: 'db-filters' }, input, source, status),
      el('div', { class: 'db-bulk' }, el('label', { class: 'db-select-all' }, selectAll, el('span', { text: t('db.select_all') })),
        el('span', { class: 'spacer' }), deleteSelected, deleteMatching), list));
  run(false);
}

function renderDbRow(row) {
  const open = db.open.has(row.key);
  const details = el('div', { class: 'db-details' });
  const check = el('input', { type: 'checkbox', class: 'db-check', checked: db.selected.has(row.key), 'aria-label': row.word,
    onchange: (e) => { if (e.target.checked) db.selected.add(row.key); else db.selected.delete(row.key); db.updateBulk?.(); } });
  const line = el('div', { class: 'db-row' + (open ? ' open' : '') }, check,
    el('button', { class: 'db-word', text: row.word, title: t('db.view'), onclick: () => {
      if (db.open.has(row.key)) db.open.delete(row.key); else db.open.add(row.key);
      line.replaceWith(renderDbRow(row));
    } }),
    el('span', { class: 'db-source', text: sourceName(row.source) }),
    el('span', { class: 'badge ' + (row.not_found ? 'warn' : row.indirect.length ? 'info' : 'ok'),
      title: row.indirect.length ? t('db.indirect_help') : '',
      text: row.not_found ? t('db.not_found') : row.indirect.length ? t('db.indirect_of', { base: row.indirect.join(', ') }) : t('db.found') }),
    el('span', { class: 'db-meta', text: [formatBytes(row.text_bytes), row.media_files ? `${row.media_files} ${t('db.files')} · ${formatBytes(row.media_bytes)}` : '', (row.saved_at || '').slice(0, 16)].filter(Boolean).join(' · ') }),
    el('span', { class: 'db-actions' },
      el('button', { class: 'btn ghost small', text: t('db.fetch_again'), disabled: state.job.running, title: t('db.fetch_again_help'),
        onclick: () => start('refresh_word', { word: row.word, source: row.source }) }),
      el('button', { class: 'btn ghost small danger-text', text: t('db.delete'), disabled: state.job.running,
        onclick: () => dbAction('/api/db/delete', { keys: [row.key] }, t('db.delete_confirm', { word: row.word, source: sourceName(row.source) })) })),
    open ? details : null);
  if (open) loadEntry(row, details);
  return line;
}

async function loadEntry(row, box) {
  box.textContent = t('db.loading');
  let entry;
  try { entry = await api('GET', '/api/db/entry?key=' + encodeURIComponent(row.key)); } catch (e) { box.textContent = e.error; return; }
  const settings = Object.entries(entry.settings || {}).map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join(' · ');
  const preview = entry.not_found ? el('p', { class: 'hint', text: t('db.not_found_detail', { source: sourceName(entry.source) }) })
    : el('iframe', { class: 'db-preview', sandbox: '', title: t('db.preview'),
      srcdoc: '<!doctype html><meta charset="utf-8"><style>body{font:14px system-ui,sans-serif;margin:12px;color:#222}img{max-width:120px}</style>' + entry.content });
  box.replaceChildren(...[
    settings ? el('div', { class: 'hint', text: t('db.settings') + ': ' + settings }) : null,
    preview,
    entry.media.length ? el('div', { class: 'db-media' }, entry.media.map((m) => el('code', { text: `${m.kind}: ${m.filename} (${formatBytes(m.bytes)})` }))) : null,
  ].filter(Boolean));
}

function renderCacheTools() {
  const select = el('select', { 'aria-label': t('cache.source') },
    state.info.cache_sources.map((s) => el('option', { value: s, text: t('source.' + s, {}, humanize(s)) })));
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', { text: t('cache.title') })),
    el('div', { class: 'card-body' }, el('div', { class: 'field' },
      el('div', { class: 'field-label' }, el('label', { text: t('cache.source') })),
      el('div', { class: 'cache-row' }, select, el('button', {
        class: 'btn', text: t('cache.clear'), disabled: state.job.running,
        onclick: async () => {
          const name = select.options[select.selectedIndex].text;
          if (await confirmBox(t('cache.confirm', { source: name }))) start('clear_cache', { source: select.value });
        },
      })),
      el('div', { class: 'field-help', text: t('cache.desc') }))));
}

function finishText(job) {
  if (job.returncode === 0) return t('status.done');
  if (job.returncode === 2 && job.kind === 'run') return t('status.stopped');
  return t('status.failed', { code: job.returncode });
}

function refreshChrome() {
  const count = dirtyCount();
  const running = state.job.running;
  const invalid = state.invalid.size > 0;
  $('#save').disabled = !count || running || invalid || state.busy;
  $('#revert').disabled = !count || running || state.busy;
  $('#run').hidden = running;
  $('#stop').hidden = !running;
  $('#run').disabled = invalid || state.busy;
  $('#check').disabled = running || invalid || state.busy;
  $('#reload').disabled = running || state.busy;
  document.querySelectorAll('.field[data-key]').forEach((row) => {
    const key = row.dataset.key;
    row.classList.toggle('changed', !same(state.values.get(key), state.baseline.get(key)));
  });
  const dot = $('#dirty-dot');
  const progress = state.job.progress;
  $('#progress').hidden = !(running && progress);
  if (running) {
    dot.className = 'dot busy';
    let text = state.job.stopping ? t('status.stopping') : state.job.kind === 'check' ? t('status.checking') : t('status.running');
    if (progress && !state.job.stopping) {
      text = t('status.progress', progress);
      $('#progress-bar').style.width = (100 * progress.current / progress.total) + '%';
    }
    $('#status').textContent = text;
  } else if (state.busy) {
    dot.className = 'dot busy';
    $('#status').textContent = t('status.saving');
  } else if (count) {
    dot.className = 'dot dirty';
    $('#status').textContent = t('status.unsaved', { count });
  } else if (state.job.kind && state.job.returncode) {
    dot.className = state.job.returncode === 2 && state.job.kind === 'run' ? 'dot dirty' : 'dot bad';
    $('#status').textContent = finishText(state.job);
  } else {
    dot.className = 'dot';
    $('#status').textContent = state.job.kind ? t('status.done') : t('status.saved');
  }
  const nav = $('#tabs');
  if (nav.children.length) renderTabsLight();
}

function renderTabsLight() {
  // Update the unsaved markers on the tabs without rebuilding the page.
  [...$('#tabs').children].forEach((button, i) => {
    const tab = state.schema.tabs[i];
    const marker = button.querySelector('.changed');
    if (tab && tabDirty(tab) !== Boolean(marker)) { renderTabs(); }
  });
}

// ---------------------------------------------------------------- actions
async function save() {
  if (!dirtyCount()) return true;
  state.busy = true; refreshChrome();
  try {
    const changes = changedPaths().map((key) => ({ path: state.fields.get(key).path, value: state.values.get(key) }));
    if (decksChanged()) changes.push({ path: ['anki', 'saved_decks'], decks: state.decks });
    const result = await api('POST', '/api/save', {
      changes, sources_order: orderChanged() ? state.order : null, version: state.schema.version,
    });
    state.busy = false;
    await load(true);
    if (result.warning) banner('warn', t('warning.title') + ': ' + result.warning);
    else banner('ok', t('status.saved_now'));
    setTimeout(() => { if ($('#banner').classList.contains('ok')) banner('', ''); }, 2500);
    return true;
  } catch (error) {
    state.busy = false;
    banner('error', error.error === 'conflict' ? t('error.conflict') : error.error === 'busy' ? t('error.busy') : error.error);
    refreshChrome();
    return false;
  }
}

async function start(kind, extra = {}) {
  if (dirtyCount() && !(await save())) return;
  try {
    const job = await api('POST', '/api/run', { kind, ...extra });
    state.job = job;
    state.logNext = 0;
    $('#log').textContent = '';
    showLog(true);
    refreshChrome();
    poll();
  } catch (error) {
    banner('error', error.error === 'busy' ? t('error.busy') : error.error);
  }
}

function appendLog(lines) {
  const log = $('#log');
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  for (const line of lines) {
    const trimmed = line.trim();
    let cls = '';
    if (/^\[\d+\/\d+\]/.test(trimmed) || trimmed === 'FINAL REPORT' || trimmed.startsWith('FINAL REPORT')) cls = 'head';
    else if (/^(OK|EMPTY)\b/.test(trimmed) || /^Status: COMPLETED$/.test(trimmed) || trimmed.startsWith('Saved:') || trimmed.startsWith('Configuration OK') || trimmed.startsWith('Removed ')) cls = 'ok';
    else if (/^(FAIL|FAILED|SKIP|Cannot|Run failed|Run stopped|Traceback)\b/.test(trimmed) || /^\w+(Error|Exception):/.test(trimmed)) cls = 'bad';
    else if (/^=+$/.test(trimmed)) cls = 'dim';
    log.append(cls ? el('span', { class: cls, text: line }) : line, '\n');
  }
  if (atBottom) log.scrollTop = log.scrollHeight;
}

async function poll() {
  clearTimeout(state.poller);
  try {
    const job = await api('GET', '/api/job?since=' + state.logNext);
    appendLog(job.lines);
    state.logNext = job.next;
    state.job = job;
    $('#log-status').textContent = job.running ? '' : finishText(job);
    refreshChrome();
    if (job.running) { state.poller = setTimeout(poll, 500); return; }
    state.poller = null;
    if (state.tab === 'database') renderPage();
  } catch (error) {
    state.poller = setTimeout(poll, 2000);
    $('#log-status').textContent = error.error;
  }
}

function showLog(show) {
  $('#log-panel').hidden = !show;
}

function takeToken() {
  const match = location.hash.match(/token=([\w-]+)/);
  if (match) {
    sessionStorage.setItem('gui.token', match[1]);
    history.replaceState(null, '', location.pathname);
  }
  state.token = sessionStorage.getItem('gui.token') || '';
  return Boolean(match);
}

async function boot() {
  takeToken();
  window.addEventListener('hashchange', () => { if (takeToken()) load().catch((e) => banner('error', e.error)); });
  $('#save').addEventListener('click', save);
  $('#revert').addEventListener('click', async () => {
    if (!(await confirmBox(t('confirm.discard')))) return;
    for (const [key, value] of state.baseline) state.values.set(key, clone(value));
    state.order = [...state.baseOrder];
    state.decks = state.baseDecks.map((d) => [...d]);
    state.invalid.clear();
    render();
  });
  $('#reload').addEventListener('click', async () => {
    if (dirtyCount() && !(await confirmBox(t('confirm.reload')))) return;
    await load();
  });
  $('#run').addEventListener('click', () => start('run'));
  $('#check').addEventListener('click', () => start('check'));
  $('#stop').addEventListener('click', async () => { await api('POST', '/api/stop', {}); poll(); });
  $('#toggle-log').addEventListener('click', () => showLog($('#log-panel').hidden));
  $('#close-log').addEventListener('click', () => showLog(false));
  $('#clear-log').addEventListener('click', () => { $('#log').textContent = ''; });
  $('#open-output').addEventListener('click', () => api('POST', '/api/open', { what: 'output' }).catch((e) => banner('error', e.error)));
  $('#language').addEventListener('change', async (e) => {
    if (dirtyCount() && !(await confirmBox(t('confirm.reload')))) { e.target.value = state.lang; return; }
    state.lang = e.target.value;
    localStorage.setItem('gui.lang', state.lang);
    await load();
  });
  window.addEventListener('beforeunload', (e) => { if (dirtyCount()) e.preventDefault(); });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (!$('#save').disabled) save(); }
  });
  try {
    await load();
  } catch (error) {
    banner('error', error.status === 403 ? 'Open the GUI with the link printed by: python main.py --gui' : error.error);
  }
}

boot();
