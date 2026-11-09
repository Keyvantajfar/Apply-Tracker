/* GradApp front end: vanilla JS, no build step, no CDN. */
(() => {
'use strict';

// ---------- tiny helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clip = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const store = {
  get(k, d) { try { const v = localStorage.getItem('gradapp.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('gradapp.' + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
const ICONS = {
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  board: '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/><rect x="17" y="4" width="4" height="13" rx="1"/>',
  people: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><path d="M16 5.2a3 3 0 0 1 0 5.6M18 14.8c1.8.7 3 2.4 3 5.2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>',
  find: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9Z"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
  up: '<path d="M12 16V4M6 10l6-6 6 6M5 20h14"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  send: '<path d="m4 12 16-8-6 16-3-6.5Z"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
};
const icon = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;

// ---------- state ----------
const S = {
  tracker: { universities: [] }, profile: {}, settings: {}, deadlines: [], docs: [], user: window.__USER__ || {},
  stages: [], outreach: [], labels: {},
  view: store.get('view', 'programs'),
  f: Object.assign({ q: '', country: '', stage: '', tag: '', free: false, mine: false, sort: 'score', group: 'tier' }, store.get('filters', {})),
  pf: { q: '', outreach: '', country: '' },
  closed: new Set(store.get('closed', ['unlikely'])),
  drawer: null, chat: null, chatBusy: false, lastActions: [], imp: { prompt: '', preview: null, text: '', mode: 'fill' },
  batch: null,
};
let IDX = { prog: new Map(), prof: new Map(), uni: new Map() };

function reindex() {
  IDX = { prog: new Map(), prof: new Map(), uni: new Map() };
  for (const u of S.tracker.universities) {
    IDX.uni.set(u.id, u);
    for (const p of u.programs) IDX.prog.set(p.id, { u, p });
    for (const q of u.professors) IDX.prof.set(q.id, { u, q });
  }
}
const allPrograms = () => S.tracker.universities.flatMap(u => u.programs.map(p => ({ u, p })));
const dlOf = id => S.deadlines.find(d => d.program_key === id);

function applyState(st) {
  S.tracker = st.tracker; S.profile = st.profile; S.settings = st.settings; S.deadlines = st.deadlines;
  S.docs = st.docs; S.version = st.version; S.user = st.user; S.stages = st.stages; S.outreach = st.outreach; S.labels = st.profile_labels;
  reindex(); applyTheme();
}
function applyTheme() {
  const t = S.settings.theme;
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
}

// ---------- api ----------
async function api(method, url, body, opts = {}) {
  const init = { method, headers: { 'X-GradApp': '1' } };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  let res, data;
  try { res = await fetch(url, init); } catch { throw new Error('Cannot reach the server. Is GradApp still running?'); }
  try { data = await res.json(); } catch { data = { ok: false, error: 'The server sent an unreadable reply.' }; }
  if (res.status === 401) { location.href = '/login'; throw new Error('Signed out.'); }
  if (!res.ok || data.ok === false) { const e = new Error(data.error || `Request failed (${res.status})`); e.data = data; e.status = res.status; throw e; }
  return data;
}
const guard = fn => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, { err: true }); console.error(e); } };

// ---------- toasts, modal, menu ----------
function toast(msg, o = {}) {
  const el = document.createElement('div');
  el.className = 'toast' + (o.err ? ' err' : '');
  el.innerHTML = `<span>${esc(msg)}</span>` + (o.undo ? '<button type="button">Undo</button>' : '');
  if (o.undo) $('button', el).onclick = () => { el.remove(); o.undo(); };
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), o.ms || (o.err ? 7000 : o.undo ? 9000 : 3200));
  return el;
}
function openModal(html, o = {}) {
  const host = $('#modal');
  host.innerHTML = `<div class="modal ${o.wide ? 'wide' : ''}" role="dialog" aria-modal="true">${html}</div>`;
  host.hidden = false;
  host.onmousedown = e => { if (e.target === host) closeModal(); };
  const first = $('input:not([type=checkbox]),textarea,select', host); if (first && !o.noFocus) first.focus();
  return $('.modal', host);
}
function closeModal() { const h = $('#modal'); h.hidden = true; h.innerHTML = ''; }
let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
function openMenu(anchor, items) {
  closeMenu();
  const m = document.createElement('div'); m.className = 'menu';
  m.innerHTML = items.map((it, i) => it === '-' ? '<hr>' : `<button type="button" data-i="${i}" class="${it.danger ? 'danger' : ''}">${it.icon ? icon(it.icon) : ''}${esc(it.label)}</button>`).join('');
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect();
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.right - w)) + 'px';
  m.style.top = (r.bottom + h + 12 > innerHeight ? Math.max(8, r.top - h - 4) : r.bottom + 4) + 'px';
  m.onclick = e => { const b = e.target.closest('button'); if (!b) return; const it = items[+b.dataset.i]; closeMenu(); it.run(); };
  menuEl = m;
}
document.addEventListener('mousedown', e => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); });

// ---------- score helpers ----------
const tierOf = s => s == null ? 'unscored' : s >= 75 ? 'strong' : s >= 45 ? 'possible' : 'unlikely';
const TIER_TITLE = { strong: 'Strong match', possible: 'Possible', unlikely: 'Unlikely or blocked', unscored: 'Not scored yet' };
const TIER_HINT = { strong: '75 and up', possible: '45 to 74', unlikely: 'under 45', unscored: '' };
function ring(p, big = false) {
  const s = p.fit_score, src = (p.score_meta || {}).source, c = 106.8;
  const t = tierOf(s);
  const arc = s == null ? '' : `<circle class="arc" cx="20" cy="20" r="17" stroke-width="3" stroke-dasharray="${(s / 100 * c).toFixed(1)} ${c}"/>`;
  const tip = s == null ? 'No score yet' : `${Math.round(s)} / 100 - ${src === 'manual' ? 'set by you' : src === 'ai' ? 'AI score' : 'estimate from program data'}`;
  return `<button type="button" class="ring ${t} ${src === 'rule' ? 'est' : ''} ${big ? 'big' : ''}" data-act="score" title="${esc(tip)}" aria-label="${esc(tip)}">
    <svg viewBox="0 0 40 40"><circle class="track" cx="20" cy="20" r="17" stroke-width="3"/>${arc}</svg><b>${s == null ? '–' : Math.round(s)}</b></button>`;
}
const money = n => '€' + Math.round(n).toLocaleString('en');
function fmtDate(iso) { const d = new Date(iso + 'T00:00:00'); return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }); }
function tuitionText(p) {
  if (p.tuition_eur_per_year === 0) return '<span class="free">No tuition</span>';
  if (typeof p.tuition_eur_per_year === 'number') return money(p.tuition_eur_per_year) + '/yr';
  return p.tuition_note ? esc(clip(p.tuition_note, 28)) : '<span class="muted">Tuition unknown</span>';
}

// ---------- shell ----------
const NAV = [['programs', 'list', 'Programs'], ['pipeline', 'board', 'Pipeline'], ['professors', 'people', 'Professors'], ['me', 'user', 'My profile'], ['assistant', 'chat', 'Assistant'], ['find', 'find', 'Find programs']];
function renderRail() {
  const n = allPrograms().length;
  $('#rail').innerHTML = `<div class="brand"><span class="brand-mark">G</span>GradApp</div>` +
    NAV.map(([id, ic, lbl]) => `<button type="button" class="nav-item ${S.view === id ? 'on' : ''}" data-act="nav" data-view="${id}" title="${lbl}">${icon(ic)}<span class="lbl">${lbl}</span>${id === 'programs' ? `<span class="nav-count">${n}</span>` : ''}</button>`).join('') +
    `<div class="rail-sp"></div><button type="button" class="nav-item" data-act="settings" title="Settings">${icon('gear')}<span class="lbl">Settings</span></button>
     <div class="rail-user"><span class="avatar">${esc((S.user.display_name || S.user.username || '?')[0].toUpperCase())}</span><div><b>${esc(S.user.display_name || S.user.username)}</b><small>@${esc(S.user.username)}</small></div></div>`;
}
function go(view) {
  S.view = view; store.set('view', view); closeDrawer(); renderRail(); renderView();
  $('#main').scrollTo?.(0, 0); window.scrollTo(0, 0);
}
function renderView() {
  const v = { programs: viewPrograms, pipeline: viewPipeline, professors: viewProfessors, me: viewMe, assistant: viewAssistant, find: viewFind }[S.view] || viewPrograms;
  v();
}

// ---------- PROGRAMS ----------
function filteredPrograms() {
  const f = S.f, q = f.q.trim().toLowerCase();
  let rows = allPrograms().filter(({ u, p }) => {
    if (q && !(`${p.name} ${u.name} ${u.country} ${u.city} ${p.language} ${p.funding} ${p.degree} ${(p.tags || []).join(' ')} ${p.partners || ''}`.toLowerCase().includes(q))) return false;
    if (f.country && u.country !== f.country) return false;
    if (f.stage && p.stage !== f.stage) return false;
    if (f.tag && !(p.tags || []).includes(f.tag)) return false;
    if (f.free && p.tuition_eur_per_year !== 0) return false;
    if (f.mine && !p.apply) return false;
    return true;
  });
  const sorters = {
    score: (a, b) => (b.p.fit_score ?? -1) - (a.p.fit_score ?? -1),
    deadline: (a, b) => ((dlOf(a.p.id)?.days_left) ?? 9999) - ((dlOf(b.p.id)?.days_left) ?? 9999),
    name: (a, b) => a.u.name.localeCompare(b.u.name) || a.p.name.localeCompare(b.p.name),
    recent: (a, b) => (b.p.updated_at || '').localeCompare(a.p.updated_at || ''),
  };
  return rows.sort(sorters[f.sort] || sorters.score);
}
function groupRows(rows) {
  const g = S.f.group, out = [];
  const push = (key, title, list, hint = '') => list.length && out.push({ key, title, rows: list, hint });
  if (g === 'tier') for (const t of ['strong', 'possible', 'unlikely', 'unscored']) push(t, TIER_TITLE[t], rows.filter(r => tierOf(r.p.fit_score) === t), TIER_HINT[t]);
  else if (g === 'country') [...new Set(rows.map(r => r.u.country || 'No country'))].sort().forEach(c => push('c:' + c, c, rows.filter(r => (r.u.country || 'No country') === c)));
  else if (g === 'university') [...new Set(rows.map(r => r.u.id))].forEach(id => { const l = rows.filter(r => r.u.id === id); push('u:' + id, l[0].u.name, l, l[0].u.country); });
  else if (g === 'stage') S.stages.forEach(s => push('s:' + s, s, rows.filter(r => r.p.stage === s)));
  else push('all', 'All programs', rows);
  return out;
}
function rowHTML({ u, p }) {
  const d = dlOf(p.id), link = /^https?:\/\//.test(p.official_link);
  const lang = (p.language || '').split(/[;(,]/)[0].trim();
  const title = link ? `<a class="title" href="${esc(p.official_link)}" target="_blank" rel="noopener noreferrer" data-stop-row>${esc(p.name)}</a>` : `<span class="title">${esc(p.name)}</span>`;
  return `<article class="row ${p.apply ? 'mine' : ''}" data-id="${esc(p.id)}" data-act="row" tabindex="0">
    ${ring(p)}
    <div style="min-width:0">${title}<div class="sub">${esc(u.name)}${u.country ? ' · ' + esc(u.country) : ''}${(p.tags || []).map(x => `<span class="badge accent">${esc(x)}</span>`).join('')}</div></div>
    <div class="facts">${tuitionText(p)}<br><span class="muted">${esc(clip(lang, 22))}</span></div>
    <div class="dlcell ${d && d.days_left <= 21 ? 'soon' : ''}">${d ? `${fmtDate(d.date)}<br><span class="muted">${d.days_left === 0 ? 'today' : d.days_left + ' days'}</span>` : '<span class="muted">No date</span>'}</div>
    <div class="stagecell"><select class="stage-sel" data-act="stage" data-stage="${esc(p.stage)}" aria-label="Stage">${S.stages.map(s => `<option ${s === p.stage ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
    <button type="button" class="star ${p.apply ? 'on' : ''}" data-act="star" title="${p.apply ? 'Applying here' : 'Mark as applying'}" aria-pressed="${p.apply}">${icon('star')}</button>
    <button type="button" class="icon-btn" data-act="rowmenu" aria-label="More">${icon('more')}</button>
  </article>`;
}
function viewPrograms() {
  const countries = [...new Set(S.tracker.universities.map(u => u.country).filter(Boolean))].sort();
  const f = S.f;
  const tags = [...new Set(allPrograms().flatMap(r => r.p.tags || []))].sort();
  $('#view').innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Programs</h1><p id="psub"></p></div><div class="sp"></div>
      <button class="btn" data-act="ai-batch">${icon('spark')}Score with AI</button>
      <button class="btn primary" data-act="add-program">${icon('plus')}Add program</button></div>
    <div id="dlstrip"></div>
    <div class="toolbar">
      <label class="search"><span class="sr">Search</span>${icon('search')}<input type="search" id="q" placeholder="Search   ( / )" value="${esc(f.q)}"></label>
      <select data-filter="country" aria-label="Country"><option value="">All countries</option>${countries.map(c => `<option ${c === f.country ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
      ${tags.length ? `<select data-filter="tag" aria-label="Label"><option value="">Any label</option>${tags.map(x => `<option ${x === f.tag ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>` : ''}
      <select data-filter="stage" aria-label="Stage"><option value="">Any stage</option>${S.stages.map(s => `<option ${s === f.stage ? 'selected' : ''}>${s}</option>`).join('')}</select>
      <button type="button" class="chip ${f.free ? 'on' : ''}" data-act="toggle-free">No tuition</button>
      <button type="button" class="chip mine-chip ${f.mine ? 'on' : ''}" data-act="toggle-mine">${icon('star')}Applying</button>
      <select data-filter="sort" aria-label="Sort"><option value="score" ${f.sort === 'score' ? 'selected' : ''}>Best fit first</option><option value="deadline" ${f.sort === 'deadline' ? 'selected' : ''}>Nearest deadline</option><option value="name" ${f.sort === 'name' ? 'selected' : ''}>University A to Z</option><option value="recent" ${f.sort === 'recent' ? 'selected' : ''}>Recently edited</option></select>
      <select data-filter="group" aria-label="Group by"><option value="tier" ${f.group === 'tier' ? 'selected' : ''}>Group by fit</option><option value="country" ${f.group === 'country' ? 'selected' : ''}>Group by country</option><option value="university" ${f.group === 'university' ? 'selected' : ''}>Group by university</option><option value="stage" ${f.group === 'stage' ? 'selected' : ''}>Group by stage</option><option value="none" ${f.group === 'none' ? 'selected' : ''}>No grouping</option></select>
    </div>
    <div id="plist"></div></div>`;
  renderList();
}
function renderList() {
  const rows = filteredPrograms(), all = allPrograms();
  const mine = all.filter(r => r.p.apply).length;
  const sub = $('#psub'); if (sub) sub.textContent = `${rows.length} of ${all.length} programs · ${mine} you're applying to`;
  const strip = $('#dlstrip');
  if (strip) {
    const next = S.deadlines.filter(d => d.apply || d.days_left <= 120).slice(0, 8);
    strip.innerHTML = next.length ? `<div class="deadlines" aria-label="Next deadlines">${next.map(d => `<button type="button" class="dl ${d.days_left <= 21 ? 'soon' : ''} ${d.apply ? 'mine' : ''}" data-act="open-id" data-id="${esc(d.program_key)}"><span class="when">${fmtDate(d.date)}<small>${d.days_left === 0 ? 'today' : d.days_left + 'd'}</small></span><span class="what"><b>${esc(d.university)}</b> ${esc(clip(d.program, 60))}</span></button>`).join('')}</div>` : '';
  }
  const host = $('#plist'); if (!host) return;
  if (!all.length) { host.innerHTML = `<div class="empty"><h3>No programs yet</h3><p>Add one by hand, or let any AI research a country for you.</p><button class="btn primary" data-act="nav" data-view="find">${icon('find')}Find programs</button></div>`; return; }
  if (!rows.length) { host.innerHTML = `<div class="empty"><h3>Nothing matches</h3><p>Try clearing the search or filters.</p><button class="btn" data-act="clear-filters">Clear filters</button></div>`; return; }
  host.innerHTML = groupRows(rows).map(g => {
    const closed = S.closed.has(g.key) && !S.f.q;
    return `<section class="group ${closed ? 'closed' : ''}" data-key="${esc(g.key)}"><button type="button" class="group-head" data-act="group" data-key="${esc(g.key)}">${icon('chev')}<h2>${esc(g.title)}</h2><span class="n">${g.rows.length}</span><span class="hint">${esc(g.hint || '')}</span></button><div class="rows">${g.rows.map(rowHTML).join('')}</div></section>`;
  }).join('');
}
function patchLocalProgram(np) {
  const e = IDX.prog.get(np.id); if (!e) return;
  const i = e.u.programs.findIndex(x => x.id === np.id); e.u.programs[i] = np; IDX.prog.set(np.id, { u: e.u, p: np });
}
const updateProgram = guard(async (id, patch) => {
  const r = await api('POST', '/api/program/update', { id, patch });
  patchLocalProgram(r.program); S.deadlines = r.deadlines; refresh();
  return r.program;
});
function refresh() { renderRail(); if (S.view === 'programs') renderList(); else renderView(); }

// ---------- PIPELINE ----------
function viewPipeline() {
  const rows = allPrograms();
  $('#view').innerHTML = `<div class="page" style="max-width:none"><div class="page-head"><div><h1>Pipeline</h1><p>Drag a card to move it to the next stage.</p></div></div>
    <div class="board">${S.stages.map(st => {
      const l = rows.filter(r => r.p.stage === st).sort((a, b) => (b.p.fit_score ?? -1) - (a.p.fit_score ?? -1));
      return `<div class="col" data-stage="${st}"><h3>${st}<span class="n">${l.length}</span></h3>${l.map(({ u, p }) => `<div class="card" draggable="true" data-id="${esc(p.id)}" data-act="card">${ring(p)}<div><div class="t">${esc(clip(p.name, 56))}</div><div class="u">${esc(u.name)}</div></div></div>`).join('')}</div>`;
    }).join('')}</div></div>`;
}

// ---------- PROFESSORS ----------
function viewProfessors() {
  const f = S.pf, q = f.q.toLowerCase();
  const countries = [...new Set(S.tracker.universities.filter(u => u.professors.length).map(u => u.country))].sort();
  const blocks = S.tracker.universities.map(u => ({ u, list: u.professors.filter(x => (!q || `${x.name} ${x.research_interests} ${x.affiliation} ${u.name}`.toLowerCase().includes(q)) && (!f.outreach || x.outreach_status === f.outreach) && (!f.country || u.country === f.country)) })).filter(b => b.list.length);
  const total = blocks.reduce((n, b) => n + b.list.length, 0);
  $('#view').innerHTML = `<div class="page"><div class="page-head"><div><h1>Professors</h1><p>${total} people to contact</p></div><div class="sp"></div><button class="btn primary" data-act="add-prof">${icon('plus')}Add professor</button></div>
    <div class="toolbar"><label class="search"><span class="sr">Search</span>${icon('search')}<input type="search" id="pq" placeholder="Search by name or research topic" value="${esc(f.q)}"></label>
    <select data-pfilter="country" aria-label="Country"><option value="">All countries</option>${countries.map(c => `<option ${c === f.country ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
    <select data-pfilter="outreach" aria-label="Outreach"><option value="">Any outreach status</option>${S.outreach.map(o => `<option ${o === f.outreach ? 'selected' : ''}>${o}</option>`).join('')}</select></div>
    <div id="prlist">${profListHTML(blocks)}</div></div>`;
}
function profListHTML(blocks) {
  if (!blocks.length) return `<div class="empty"><h3>No professors here</h3><p>Add people you want to write to, or import them with a research prompt.</p></div>`;
  return blocks.map(({ u, list }) => `<section class="uni-block"><h2>${esc(u.name)}<small>${esc(u.country)}</small></h2><div class="rows">${list.map(q => {
    const phd = /^yes/i.test(q.open_phd_calls || '');
    return `<article class="prow" data-id="${esc(q.id)}" data-act="prof" tabindex="0">
      <div><div class="nm">${esc(q.name)}</div><div class="muted small">${esc(clip(q.title || q.affiliation, 46))}</div></div>
      <div class="interest">${esc(q.research_interests || q.relevance || '')}${phd ? ' <span class="badge good">Open PhD call</span>' : ''}</div>
      <div class="email">${q.email ? `<button type="button" class="btn sm ghost" data-act="copy-email" data-email="${esc(q.email)}" title="Copy email">${icon('copy')}Email</button>` : '<span class="muted small">No email</span>'}</div>
      <select class="stage-sel" data-act="outreach" aria-label="Outreach status">${S.outreach.concat(S.outreach.includes(q.outreach_status) ? [] : [q.outreach_status]).map(o => `<option ${o === q.outreach_status ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>
      ${/^https?:/.test(q.page) ? `<a class="icon-btn" href="${esc(q.page)}" target="_blank" rel="noopener noreferrer" title="Open page" data-stop-row>${icon('ext')}</a>` : '<span></span>'}
    </article>`;
  }).join('')}</div></section>`).join('');
}

// ---------- ME (profile + documents) ----------
const PROFILE_ORDER = ['applicant', 'degree', 'university', 'gpa_overall', 'gpa_last_two_years', 'gpa_german_bavarian', 'gpa_german_scale', 'credits_passed', 'credits_total', 'current_semester', 'approx_ects_cs', 'math_stats_ects', 'english', 'research', 'skills', 'goals'];
const labelOf = k => S.labels[k] || k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
function viewMe() {
  const keys = Object.keys(S.profile).sort((a, b) => { const ia = PROFILE_ORDER.indexOf(a), ib = PROFILE_ORDER.indexOf(b); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b); });
  $('#view').innerHTML = `<div class="page"><div class="page-head"><div><h1>My profile</h1><p>The assistant and AI scores compare programs against this. Everything is editable.</p></div></div>
  <div class="two"><div>
    <div class="panel"><h2>About me</h2><p class="muted">Changes save as you type.</p>
      <div id="prof-fields">${keys.map(k => `<div class="prof-row"><label for="pf-${esc(k)}">${esc(labelOf(k))}</label><textarea id="pf-${esc(k)}" data-pkey="${esc(k)}" rows="1">${esc(S.profile[k])}</textarea><button type="button" class="icon-btn" data-act="del-pfield" data-key="${esc(k)}" aria-label="Remove ${esc(labelOf(k))}">${icon('x')}</button></div>`).join('')}</div>
      <div class="prof-row"><label for="newpf">New field</label><input id="newpf" placeholder="For example: publications"><button type="button" class="icon-btn" data-act="add-pfield" aria-label="Add field">${icon('plus')}</button></div>
    </div></div>
  <div>
    <div class="panel"><h2>Build it from my documents</h2><p class="muted">Upload a resume, transcript or notes. The AI proposes profile fields and you choose which to keep.</p>
      <div class="dropzone" id="drop" tabindex="0" role="button" data-act="pick-files">${icon('up')}<div>Drop PDF, DOCX, TXT or MD files here, or click to choose</div></div>
      <input type="file" id="filepick" multiple accept=".pdf,.docx,.txt,.md" hidden>
      <div id="doclist" style="margin:10px 0">${docListHTML()}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm" data-act="paste-doc">Paste text</button></div>
      <div class="field" style="margin-top:14px"><span>Anything else to tell the AI (optional)</span><textarea id="extra" placeholder="Target countries, budget, topics you care about, constraints..."></textarea></div>
      <button class="btn primary" data-act="ai-profile" id="aiprof">${icon('spark')}Build profile with AI</button>
    </div></div></div></div>`;
  $$('#prof-fields textarea').forEach(autoGrow);
}
function docListHTML() {
  return S.docs.length ? S.docs.map(d => `<div class="doc"><span title="${esc(d.name)}">${esc(d.name)}</span><span class="muted small" style="flex:none">${(d.chars / 1000).toFixed(1)}k chars</span><button type="button" class="icon-btn" data-act="del-doc" data-name="${esc(d.name)}" aria-label="Delete ${esc(d.name)}">${icon('trash')}</button></div>`).join('') : '<p class="muted small">No documents yet.</p>';
}
function autoGrow(t) { t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight + 2, 260) + 'px'; }
const saveProfile = guard(async () => { const r = await api('PUT', '/api/profile', { profile: S.profile }); S.profile = r.profile; });
let profTimer = null;

// ---------- ASSISTANT ----------
const FOCUS_TAG = { general: '', erasmus: 'Erasmus Mundus', daad: 'DAAD' };
const FOCUS_HINT = {
  general: 'Programmes in the countries you list.',
  erasmus: 'Erasmus Mundus Joint Masters only: one entry per consortium, with partner universities, scholarship terms and both application rounds. Erasmus Mundus limits how many programmes you may apply to per intake, so check the official rules before you apply.',
  daad: 'Programmes from DAAD\'s own databases plus the DAAD scholarship that can fund each one. Leave the country empty to use Germany.',
};
const SUGGEST = ['Which programs should I apply to first?', 'What deadlines are coming up in the next two months?', 'Which blocked programs could I unblock, and how?', 'Compare my two best programs.'];
async function viewAssistant() {
  if (S.chat === null) { S.chat = []; try { S.chat = (await api('GET', '/api/chat')).messages; } catch (e) { toast(e.message, { err: true }); } }
  $('#view').innerHTML = `<div class="page"><div class="page-head"><div><h1>Assistant</h1><p>Ask about your programs and profile. It can propose changes; nothing changes until you approve.</p></div><div class="sp"></div><button class="btn" data-act="chat-clear">Clear chat</button></div>
    <div class="chat"><div class="msgs" id="msgs"></div>
    <div class="compose"><textarea id="cin" rows="1" placeholder="Ask something... (Enter to send, Shift+Enter for a new line)"></textarea><button class="btn primary" data-act="chat-send" id="csend">${icon('send')}Send</button></div></div></div>`;
  renderMsgs();
}
function renderMsgs() {
  const host = $('#msgs'); if (!host) return;
  let h = '';
  if (!S.chat.length) h += `<div class="empty"><h3>Ask me anything about your applications</h3><div class="suggest" style="justify-content:center">${SUGGEST.map(s => `<button type="button" class="chip" data-act="suggest">${esc(s)}</button>`).join('')}</div></div>`;
  S.chat.forEach((m, i) => {
    h += `<div class="msg ${m.role}">${esc(m.content)}`;
    if (m.role === 'assistant' && m.actions && m.actions.length && i === S.chat.length - 1 && !m.done) {
      h += `<div class="act"><b>Proposed changes</b>${m.actions.map((a, j) => `<label style="display:flex;gap:8px;margin-top:6px"><input type="checkbox" data-aj="${j}" checked> <span>${esc(a.label)}</span></label>`).join('')}<div class="row-a"><button class="btn sm primary" data-act="apply-actions">Apply selected</button><button class="btn sm" data-act="dismiss-actions">Dismiss</button></div></div>`;
    }
    h += '</div>';
  });
  if (S.chatBusy) h += `<div class="msg assistant"><span class="spinner"></span> Thinking... local models can take a minute.</div>`;
  host.innerHTML = h; host.scrollTop = host.scrollHeight;
}
const sendChat = guard(async text => {
  text = (text || '').trim(); if (!text || S.chatBusy) return;
  S.chat.push({ role: 'user', content: text }); S.chatBusy = true; renderMsgs();
  const cin = $('#cin'); if (cin) cin.value = '';
  try {
    const r = await api('POST', '/api/chat', { message: text });
    S.chat.push({ role: 'assistant', content: r.reply || '(no reply)', actions: r.actions });
  } catch (e) { S.chat.pop(); if (cin) cin.value = text; throw e; }
  finally { S.chatBusy = false; if (S.view === 'assistant') renderMsgs(); }
});

// ---------- FIND PROGRAMS (research prompt + import) ----------
function viewFind() {
  const i = S.imp;
  $('#view').innerHTML = `<div class="page"><div class="page-head"><div><h1>Find programs</h1><p>Let any AI with web access research a country for you, then import its answer here. No API key needed.</p></div></div>
  <div class="steps">
   <div class="panel"><div class="step-h"><span class="step-n">1</span><h2>Create a research prompt</h2></div>
     <label class="field"><span>What are you looking for?</span><select id="ip-focus"><option value="general" ${(i.focus || 'general') === 'general' ? 'selected' : ''}>Any programmes</option><option value="erasmus" ${i.focus === 'erasmus' ? 'selected' : ''}>Erasmus Mundus joint masters</option><option value="daad" ${i.focus === 'daad' ? 'selected' : ''}>DAAD programmes and scholarships</option></select><small class="muted" id="ip-hint">${esc(FOCUS_HINT[i.focus || 'general'])}</small></label>
     <div class="grid2">
       <label class="field"><span>Countries (comma separated; optional for Erasmus and DAAD)</span><input id="ip-countries" placeholder="Germany, Netherlands" value="${esc(i.countries || '')}"></label>
       <label class="field"><span>Degree level</span><select id="ip-level"><option>Master</option><option>PhD</option><option>Bachelor</option></select></label>
       <label class="field"><span>Field of study</span><input id="ip-fields" placeholder="Statistics, data science, machine learning" value="${esc(i.fields || '')}"></label>
       <label class="field"><span>Intake</span><input id="ip-intake" placeholder="Winter 2027/28" value="${esc(i.intake || '')}"></label>
       <label class="field"><span>Teaching language</span><input id="ip-language" placeholder="English" value="${esc(i.language || '')}"></label>
       <label class="field"><span>Maximum tuition (EUR per year)</span><input id="ip-tuition" placeholder="No limit" value="${esc(i.tuition || '')}"></label>
       <label class="field"><span>Universities per country</span><input id="ip-count" type="number" min="3" max="30" value="${esc(i.count || 10)}"></label>
       <label class="field"><span>Extra wishes</span><input id="ip-extra" placeholder="Near Hamburg, with funding, research-oriented" value="${esc(i.extra || '')}"></label>
     </div>
     <div class="toolbar" style="margin:0 0 10px"><label class="chip"><input type="checkbox" id="ip-profs" checked> Include professors</label><label class="chip"><input type="checkbox" id="ip-prof" checked> Include my profile</label><label class="chip"><input type="checkbox" id="ip-skip" checked> Skip programs I already track</label></div>
     <button class="btn primary" data-act="make-prompt">Create prompt</button> <button class="btn" data-act="make-convert" title="For a list an AI already gave you in a chat">Prompt to convert an existing list</button>
     <div id="promptout" ${i.prompt ? '' : 'hidden'} style="margin-top:14px"><p class="small muted" id="prompt-kind" style="margin:0 0 6px">${esc(i.kind || '')}</p><textarea class="promptbox" id="prompttext" readonly>${esc(i.prompt)}</textarea>
       <div style="display:flex;gap:8px;margin-top:8px;align-items:center"><button class="btn" data-act="copy-prompt">${icon('copy')}Copy prompt</button><span class="muted small">Paste it into ChatGPT, Gemini, Claude or Perplexity with web search or deep research switched on.</span></div></div>
   </div>
   <div class="panel"><div class="step-h"><span class="step-n">2</span><h2>Import the answer</h2></div>
     <p class="muted" style="margin-top:0">Paste the JSON the AI gave you, or load it from a file. You see a preview first; nothing is saved until you import, and a backup is made.</p>
     <textarea id="imp-text" class="promptbox" style="min-height:160px" placeholder='{"universities": [ ... ]}'>${esc(i.text)}</textarea>
     <div class="toolbar" style="margin-top:10px"><input type="file" id="imp-file" accept=".json,.txt" hidden><button class="btn" data-act="imp-file">${icon('up')}Load file</button>
       <select id="imp-mode" style="width:auto"><option value="fill" ${i.mode === 'fill' ? 'selected' : ''}>Add new, fill gaps in existing (recommended)</option><option value="add" ${i.mode === 'add' ? 'selected' : ''}>Add new only</option><option value="overwrite" ${i.mode === 'overwrite' ? 'selected' : ''}>Add new, overwrite program facts</option></select>
       <button class="btn primary" data-act="imp-preview">Check</button></div>
     <div id="imp-out">${i.preview ? previewHTML(i.preview) : ''}</div>
   </div></div></div>`;
  $('#ip-level').value = i.level || 'Master';
}
function previewHTML(p) {
  const c = p.counts, any = c.new_universities + c.new_programs + c.updated_programs + c.new_professors + c.updated_professors;
  return `<div class="sum"><div><b>${c.new_universities}</b>new universities</div><div><b>${c.new_programs}</b>new programs</div><div><b>${c.updated_programs}</b>programs updated</div><div><b>${c.new_professors}</b>new professors</div><div><b>${c.skipped_programs}</b>skipped</div></div>
  ${(p.warnings || []).map(w => `<p class="small" style="color:var(--bad)">${esc(w)}</p>`).join('')}
  <div class="itemlist">${p.items.map(it => `<div><span class="badge ${it.action === 'new' ? 'good' : it.action === 'update' ? 'info' : ''}">${it.action}</span><span>${esc(it.name)} ${it.detail ? `<span class="muted">- ${esc(it.detail)}</span>` : ''}</span></div>`).join('')}</div>
  <div style="margin-top:12px">${any ? `<button class="btn primary" data-act="imp-commit">Import ${c.new_programs + c.updated_programs} programs</button>` : '<span class="muted">Nothing new to import with this mode.</span>'}</div>`;
}

// ---------- DRAWER ----------
function openDrawer(kind, id, tab) {
  S.drawer = { kind, id, tab: tab || 'details' }; renderDrawer();
  $('#drawer').classList.add('open'); $('#drawer').setAttribute('aria-hidden', 'false'); $('#scrim').hidden = false;
}
function closeDrawer() {
  S.drawer = null; const d = $('#drawer'); d.classList.remove('open'); d.setAttribute('aria-hidden', 'true'); $('#scrim').hidden = true;
}
const PF = [
  ['Basics', [['name', 'Program name', 'text', 1], ['degree', 'Degree'], ['language', 'Language'], ['duration', 'Duration'], ['official_link', 'Official link', 'url', 1], ['partners', 'Partner universities (joint programmes)', 'area', 1], ['tags', 'Labels (comma separated)', 'text', 1]]],
  ['Money', [['tuition_eur_per_year', 'Tuition (EUR per year)', 'number'], ['tuition_note', 'Tuition note'], ['funding', 'Funding', 'area', 1], ['funding_note', 'Funding note', 'area', 1]]],
  ['Admission', [['admission_mode', 'Admission mode', 'text', 1], ['gpa_rule', 'Requirements', 'area', 1], ['auto_gpa_filter_risk', 'GPA filter risk', 'area', 1], ['last_two_years_gpa_usable', 'Last two years of GPA count?'], ['direct_phd_possible', 'Direct PhD possible?'], ['risk_alert', 'Risk alert', 'area', 1]]],
  ['Research quality', [['verification', 'How well verified', 'area', 1], ['fit_note', 'Why it fits (or not)', 'area', 1]]],
];
function input(obj, [k, label, type, full], attr = 'data-f') {
  const v = obj[k] ?? '', cls = full ? 'field full' : 'field';
  const id = `f-${attr.replace('data-', '')}-${k}`;
  if (type === 'area') return `<label class="${cls}" for="${id}"><span>${esc(label)}</span><textarea id="${id}" ${attr}="${k}" rows="3">${esc(v)}</textarea></label>`;
  const t = type === 'number' ? 'number" step="any' : type === 'url' ? 'url' : type === 'date' ? 'date' : 'text';
  return `<label class="${cls}" for="${id}"><span>${esc(label)}</span><input id="${id}" type="${t}" ${attr}="${k}" value="${esc(v)}"></label>`;
}
function renderDrawer() {
  const d = S.drawer, el = $('#drawer'); if (!d) return;
  if (d.kind === 'prof') return renderProfDrawer();
  const e = IDX.prog.get(d.id); if (!e) { closeDrawer(); return; }
  const { u, p } = e, link = /^https?:\/\//.test(p.official_link);
  el.innerHTML = `<div class="drawer-head"><div class="top">${ring(p)}<h2>${esc(p.name)}</h2>
      ${link ? `<a class="icon-btn" href="${esc(p.official_link)}" target="_blank" rel="noopener noreferrer" title="Open official page" aria-label="Open official page">${icon('ext')}</a>` : ''}
      <button class="icon-btn" data-act="close" aria-label="Close">${icon('x')}</button></div>
    <div class="sub">${esc(u.name)}${u.country ? ' · ' + esc(u.country) : ''}${u.city ? ', ' + esc(u.city) : ''}</div>
    <div class="tabs" role="tablist">${[['details', 'Details'], ['score', 'Score'], ['notes', 'Notes'], ['people', `Professors (${u.professors.length})`]].map(([k, l]) => `<button type="button" class="tab ${d.tab === k ? 'on' : ''}" role="tab" data-act="dtab" data-tab="${k}">${l}</button>`).join('')}</div></div>
    <div class="drawer-body" id="dbody">${drawerBody(u, p, d.tab)}</div>
    <div class="drawer-foot"><span id="savedmark">Edits save automatically.</span><span style="flex:1"></span><button class="btn sm danger" data-act="del-program">${icon('trash')}Delete</button></div>`;
  $$('#dbody textarea').forEach(autoGrow);
}
function drawerBody(u, p, tab) {
  if (tab === 'score') return scoreTab(p);
  if (tab === 'notes') return `<label class="field"><span>My notes</span><textarea data-f="notes" rows="12" id="notes-box">${esc(p.notes)}</textarea></label><p class="muted small">Last edited ${esc((p.updated_at || '').slice(0, 10))}</p>`;
  if (tab === 'people') return (u.professors.length ? u.professors.map(q => `<div class="doc"><span><b>${esc(q.name)}</b><br><span class="muted small">${esc(clip(q.research_interests || q.title, 80))}</span></span><button class="btn sm" data-act="open-prof" data-id="${esc(q.id)}">Open</button></div>`).join('') : '<p class="muted">No professors saved for this university.</p>') + `<div style="margin-top:14px"><button class="btn" data-act="add-prof" data-uni="${esc(u.id)}">${icon('plus')}Add professor</button></div>`;
  const dl = Object.entries(p.deadlines || {});
  return `<div class="fgrid">
    <label class="field"><span>Stage</span><select data-f="stage">${S.stages.map(s => `<option ${s === p.stage ? 'selected' : ''}>${s}</option>`).join('')}</select></label>
    <label class="field"><span>Applying here</span><select data-f="apply"><option value="false" ${!p.apply ? 'selected' : ''}>No</option><option value="true" ${p.apply ? 'selected' : ''}>Yes</option></select></label></div>` +
    PF.map(([sec, fields]) => `<div class="sec">${sec}</div><div class="fgrid">${fields.map(f => input(p, f)).join('')}</div>`).join('') +
    `<div class="sec">Deadlines</div><div id="dl-edit">${dl.map(([k, v]) => `<div class="kv"><input data-dlk value="${esc(k)}" aria-label="Deadline name"><input data-dlv value="${esc(v)}" aria-label="Deadline date or text"><button type="button" class="icon-btn" data-act="dl-del" aria-label="Remove">${icon('x')}</button></div>`).join('')}</div><button class="btn sm" data-act="dl-add">${icon('plus')}Add deadline</button>
     <div class="sec">Sources</div><label class="field"><span>One link per line</span><textarea data-f="sources" rows="3">${esc((p.sources || []).join('\n'))}</textarea></label>
     <div class="sec">University</div><div class="fgrid">${[['name', 'Name', 'text', 1], ['country', 'Country'], ['city', 'City'], ['website', 'Website', 'url', 1]].map(f => input(u, f, 'data-uf')).join('')}</div>`;
}
function scoreTab(p) {
  const m = p.score_meta || {}, s = p.fit_score;
  const src = { manual: 'You set this score', ai: 'Scored by the AI', rule: 'Estimate from the program data', '': 'Not scored yet' }[m.source || ''];
  const list = (a, t) => a && a.length ? `<div class="sec">${t}</div><ul class="list-b">${a.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
  return `<div class="score-hero">${ring(p, true)}<div><h3>${esc(src)}${m.locked ? ` ${icon('lock').replace('class="i"', 'class="i" style="vertical-align:-3px"')}` : ''}</h3><div class="muted small">${m.updated_at ? 'Updated ' + esc(m.updated_at.slice(0, 10)) : 'Pick how to score this program below.'}</div>
    ${m.locked ? '<div class="small muted">Locked: AI and estimates will not overwrite it.</div>' : ''}</div></div>
    ${m.rationale ? `<p>${esc(m.rationale)}</p>` : ''}${list(m.blockers, 'Blockers')}${list(m.strengths, 'Strengths')}${list(m.risks, 'Risks')}
    ${m.next_step ? `<div class="sec">Next step</div><p>${esc(m.next_step)}</p>` : ''}
    <div class="sec">Set it yourself</div>
    <div style="display:flex;gap:8px;align-items:center"><input type="number" id="manual-score" min="0" max="100" step="1" placeholder="0 to 100" value="${s == null ? '' : Math.round(s)}" style="width:110px"><button class="btn" data-act="score-manual">Save my score</button></div>
    <p class="muted small">Saving locks your score so the AI and estimates never overwrite it. You can unlock it any time.</p>
    <div class="sec">Let the AI do it</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" data-act="score-ai" id="score-ai">${icon('spark')}Re-score with AI</button>
      <button class="btn" data-act="score-rule">Use estimate</button>
      ${m.locked ? '<button class="btn" data-act="score-unlock">Unlock</button>' : ''}
      ${s != null ? '<button class="btn ghost" data-act="score-clear">Clear score</button>' : ''}</div>
    <p class="muted small">AI scoring only writes the score and its explanation. It never touches your other fields.</p>`;
}
function renderProfDrawer() {
  const d = S.drawer, e = IDX.prof.get(d.id); if (!e) { closeDrawer(); return; }
  const { u, q } = e, el = $('#drawer');
  const progs = u.programs.map(p => `<option value="${esc(p.id)}" ${p.id === q.program_id ? 'selected' : ''}>${esc(clip(p.name, 60))}</option>`).join('');
  const F = (a) => input(q, a, 'data-qf');
  el.innerHTML = `<div class="drawer-head"><div class="top"><h2>${esc(q.name)}</h2>${q.email ? `<a class="icon-btn" href="mailto:${esc(q.email)}" title="Write an email" aria-label="Write an email">${icon('mail')}</a>` : ''}${/^https?:/.test(q.page) ? `<a class="icon-btn" href="${esc(q.page)}" target="_blank" rel="noopener noreferrer" aria-label="Open page">${icon('ext')}</a>` : ''}<button class="icon-btn" data-act="close" aria-label="Close">${icon('x')}</button></div><div class="sub">${esc(u.name)} · ${esc(u.country)}</div></div>
   <div class="drawer-body"><div class="fgrid">
     <label class="field"><span>Outreach status</span><select data-qf="outreach_status">${S.outreach.map(o => `<option ${o === q.outreach_status ? 'selected' : ''}>${o}</option>`).join('')}</select></label>
     ${F(['last_contacted', 'Last contacted', 'date'])}
     ${F(['name', 'Name', 'text', 1])}${F(['title', 'Title'])}${F(['affiliation', 'Affiliation'])}
     ${F(['research_interests', 'Research interests', 'area', 1])}${F(['relevance', 'Why relevant to me', 'area', 1])}
     ${F(['email', 'Email', 'text'])}${F(['email_source', 'Email source'])}${F(['page', 'Page', 'url', 1])}
     ${F(['open_phd_calls', 'Open PhD calls', 'area', 1])}${F(['direct_phd_possible', 'Direct PhD possible?', 'area', 1])}
     <label class="field full"><span>Linked program</span><select data-qf="program_id"><option value="">None</option>${progs}</select></label>
     ${F(['verification', 'How well verified', 'text', 1])}${F(['notes', 'Notes', 'area', 1])}
     <label class="field full"><span>Sources (one per line)</span><textarea data-qf="sources" rows="2">${esc((q.sources || []).join('\n'))}</textarea></label></div></div>
   <div class="drawer-foot"><span id="savedmark">Edits save automatically.</span><span style="flex:1"></span><button class="btn sm danger" data-act="del-prof">${icon('trash')}Delete</button></div>`;
  $$('#drawer textarea').forEach(autoGrow);
}
function savedMark(ok = true) { const m = $('#savedmark'); if (m) { m.innerHTML = ok ? `<span class="saved">${icon('check').replace('class="i"', 'class="i" style="vertical-align:-4px"')} Saved</span>` : 'Not saved'; } }

// ---------- actions ----------
const toggleApply = (id, v) => updateProgram(id, { apply: v });

async function aiScore(id, force = false) {
  const e = IDX.prog.get(id); if (!e) return;
  try {
    const r = await api('POST', '/api/program/score', { id, action: 'ai', force });
    patchLocalProgram(r.program); return r.program;
  } catch (err) {
    if (err.status === 409 && !force && confirm('You set this score by hand. Replace it with the AI score?')) return aiScore(id, true);
    throw err;
  }
}
async function batchScore(scope) {
  const all = allPrograms();
  let list = scope === 'visible' ? filteredPrograms() : scope === 'unscored' ? all.filter(r => r.p.fit_score == null) : scope === 'estimates' ? all.filter(r => (r.p.score_meta || {}).source === 'rule') : all.filter(r => r.p.apply);
  list = list.filter(r => !(r.p.score_meta || {}).locked);
  if (!list.length) return toast('Nothing to score in that group (locked scores are skipped).');
  S.batch = { stop: false };
  const t = toast('', { ms: 3600000 }); let done = 0, failed = 0, lastErr = '';
  const draw = () => { t.innerHTML = `<span>Scoring with AI: ${done}/${list.length}${failed ? ` (${failed} failed)` : ''}</span><div class="bar"><i style="width:${Math.round(done / list.length * 100)}%"></i></div><button type="button">Stop</button>`; $('button', t).onclick = () => { S.batch.stop = true; }; };
  draw();
  for (const r of list) {
    if (S.batch.stop) break;
    try { await aiScore(r.p.id); } catch (e) { failed++; lastErr = e.message; if (/reach|rejected|profile is empty|key/i.test(e.message)) { break; } }
    done++; draw();
  }
  t.remove(); S.batch = null; refresh();
  if (S.drawer) renderDrawer();
  toast(failed ? `Scored ${done - failed}, ${failed} failed. ${lastErr}` : `Scored ${done} programs.`, { err: !!failed, ms: 6000 });
}

function addProgramModal(prefUni) {
  const unis = S.tracker.universities;
  const m = openModal(`<h2>Add a program</h2><p class="muted">Pick an existing university or type a new one.</p>
    <form id="addp"><div class="fgrid"><label class="field full"><span>University</span><input name="uni" list="unis" required value="${esc(prefUni ? (IDX.uni.get(prefUni) || {}).name || '' : '')}" placeholder="Start typing..."><datalist id="unis">${unis.map(u => `<option value="${esc(u.name)}">`).join('')}</datalist></label>
    <label class="field"><span>Country (new university)</span><input name="country"></label><label class="field"><span>City (new university)</span><input name="city"></label>
    <label class="field full"><span>Program name</span><input name="name" required placeholder="M.Sc. Data Science"></label>
    <label class="field full"><span>Official link</span><input name="official_link" type="url" placeholder="https://"></label>
    <label class="field"><span>Language</span><input name="language"></label><label class="field"><span>Tuition (EUR per year)</span><input name="tuition" type="number" step="any"></label></div>
    <div class="actions"><button type="button" class="btn" data-act="close-modal">Cancel</button><button class="btn primary" type="submit">Add program</button></div></form>`);
  $('#addp', m).onsubmit = guard(async ev => {
    ev.preventDefault(); const f = new FormData(ev.target);
    const ex = unis.find(u => u.name.toLowerCase() === String(f.get('uni')).trim().toLowerCase());
    const r = await api('POST', '/api/program/create', { university_id: ex && ex.id, university: { name: f.get('uni'), country: f.get('country'), city: f.get('city') },
      program: { name: f.get('name'), official_link: f.get('official_link'), language: f.get('language'), tuition_eur_per_year: f.get('tuition') } });
    await reload(); closeModal(); go('programs'); openDrawer('program', r.program.id); toast('Program added.');
  });
}
function addProfModal(uniId) {
  const unis = S.tracker.universities;
  const m = openModal(`<h2>Add a professor</h2><form id="addq"><div class="fgrid"><label class="field full"><span>University</span><select name="uid" required>${unis.map(u => `<option value="${esc(u.id)}" ${u.id === uniId ? 'selected' : ''}>${esc(u.name)}</option>`).join('')}</select></label>
    <label class="field full"><span>Name</span><input name="name" required></label><label class="field"><span>Email</span><input name="email" type="email"></label><label class="field"><span>Page</span><input name="page" type="url" placeholder="https://"></label>
    <label class="field full"><span>Research interests</span><textarea name="research_interests" rows="2"></textarea></label></div>
    <div class="actions"><button type="button" class="btn" data-act="close-modal">Cancel</button><button class="btn primary" type="submit">Add professor</button></div></form>`);
  $('#addq', m).onsubmit = guard(async ev => {
    ev.preventDefault(); const f = new FormData(ev.target);
    const r = await api('POST', '/api/prof/create', { university_id: f.get('uid'), professor: { name: f.get('name'), email: f.get('email'), page: f.get('page'), research_interests: f.get('research_interests') } });
    await reload(); closeModal(); if (S.view === 'professors') renderView(); openDrawer('prof', r.professor.id); toast('Professor added.');
  });
}
async function reload() { applyState(await api('GET', '/api/state')); renderRail(); }

const deleteProgram = guard(async id => {
  const r = await api('POST', '/api/program/delete', { id });
  closeDrawer(); await reload(); renderView();
  toast(`Deleted "${clip(r.removed.name, 40)}"`, { undo: guard(async () => { await api('POST', '/api/program/create', { university_id: r.university_id, program: r.removed }); await reload(); renderView(); toast('Restored.'); }) });
});
const deleteProf = guard(async id => {
  const r = await api('POST', '/api/prof/delete', { id });
  closeDrawer(); await reload(); renderView();
  toast(`Deleted ${r.removed.name}`, { undo: guard(async () => { await api('POST', '/api/prof/restore', { university_id: r.university_id, professor: r.removed }); await reload(); renderView(); }) });
});

function settingsModal() {
  const s = S.settings;
  const m = openModal(`<h2>Settings</h2>
   <div class="sec">AI server</div><p class="muted small" style="margin-top:-4px">Any OpenAI-compatible server: OpenAI, OpenRouter, or a local Ollama / LM Studio. A key is optional for local servers.</p>
   <label class="field"><span>Server URL</span><input id="s-url" value="${esc(s.ai_base_url)}"></label>
   <div class="fgrid"><label class="field"><span>Model</span><input id="s-model" value="${esc(s.ai_model)}"></label><label class="field"><span>Timeout (seconds)</span><input id="s-timeout" type="number" value="${esc(s.ai_timeout)}"></label></div>
   <label class="field"><span>API key ${s.has_api_key ? '(saved; leave blank to keep)' : '(optional)'}</span><input id="s-key" type="password" autocomplete="off" placeholder="${s.has_api_key ? '••••••••' : ''}"></label>
   <div style="display:flex;gap:8px;align-items:center"><button class="btn" data-act="s-test">Test connection</button><span id="s-test" class="small muted"></span></div>
   <div class="sec">Appearance</div><div class="seg" id="s-theme">${['auto', 'light', 'dark'].map(t => `<button type="button" data-theme="${t}" class="${(s.theme || 'auto') === t ? 'on' : ''}">${t[0].toUpperCase() + t.slice(1)}</button>`).join('')}</div>
   <div class="sec">Account</div><div class="fgrid"><label class="field"><span>Display name</span><input id="a-name" value="${esc(S.user.display_name || '')}"></label><div></div>
   <label class="field"><span>Current password</span><input id="a-old" type="password" autocomplete="current-password"></label><label class="field"><span>New password</span><input id="a-new" type="password" autocomplete="new-password"></label></div>
   <button class="btn sm" data-act="a-save">Save account changes</button>
   <div class="sec">Your data</div><p class="muted small" style="margin-top:-4px">Everything lives in plain files in <code>data/users/${esc(S.user.username)}/</code>. A backup is kept on every save.</p>
   <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn sm" href="/api/export/tracker">universities.json</a><a class="btn sm" href="/api/export/programs">programs.csv</a><a class="btn sm" href="/api/export/professors">professors.csv</a><a class="btn sm" href="/api/export/all">Everything (zip)</a><button class="btn sm" data-act="health">Check data health</button></div>
   <p class="muted small" style="margin:14px 0 0">GradApp v${esc(S.version || '')}</p><div class="actions"><button class="btn danger" data-act="logout">${icon('out')}Sign out</button><button class="btn primary" data-act="s-save">Save settings</button></div>`, { wide: true, noFocus: true });
  return m;
}
const saveSettings = guard(async () => {
  const body = { ai_base_url: $('#s-url').value, ai_model: $('#s-model').value, ai_timeout: +$('#s-timeout').value || 300, theme: $('#s-theme .on')?.dataset.theme || 'auto' };
  const k = $('#s-key').value; if (k) body.ai_api_key = k;
  const r = await api('PUT', '/api/settings', body); S.settings = r.settings; applyTheme(); closeModal(); toast('Settings saved.');
});
const healthModal = guard(async () => {
  const r = await api('GET', '/api/health'); const by = {}; r.issues.forEach(i => by[i.msg] = (by[i.msg] || 0) + 1);
  openModal(`<h2>Data health</h2>${r.issues.length ? `<ul class="list-b">${Object.entries(by).map(([m, n]) => `<li>${n} × ${esc(m)}</li>`).join('')}</ul>` : '<p>No problems found.</p>'}<p class="muted small">"Fix" merges duplicate universities/programs and estimates missing scores. It never changes scores you set.</p><div class="actions"><button class="btn" data-act="close-modal">Close</button><button class="btn primary" data-act="health-fix">Fix what can be fixed</button></div>`, { noFocus: true });
});

// ---------- events ----------
document.addEventListener('click', async e => {
  const t = e.target;
  const stop = t.closest('[data-stop-row]'); if (stop) { e.stopPropagation(); return; }
  const a = t.closest('[data-act]'); if (!a) return;
  const act = a.dataset.act, rowEl = a.closest('[data-id]'), id = rowEl && rowEl.dataset.id;
  switch (act) {
    case 'nav': return go(a.dataset.view);
    case 'settings': return settingsModal();
    case 'close': return closeDrawer();
    case 'close-modal': return closeModal();
    case 'row': {
      if (t.closest('select,button,a,input')) return;
      const e2 = IDX.prog.get(id); if (!e2) return;
      if (/^https?:\/\//.test(e2.p.official_link)) window.open(e2.p.official_link, '_blank', 'noopener,noreferrer'); else openDrawer('program', id);
      return;
    }
    case 'score': e.stopPropagation(); return openDrawer('program', id || (rowEl && rowEl.dataset.id) || (S.drawer && S.drawer.id), 'score');
    case 'rowmenu': {
      const { p } = IDX.prog.get(id), link = /^https?:\/\//.test(p.official_link);
      return openMenu(a, [{ label: 'Details and edit', icon: 'list', run: () => openDrawer('program', id) }, link && { label: 'Open official page', icon: 'ext', run: () => window.open(p.official_link, '_blank', 'noopener,noreferrer') },
        { label: 'Re-score with AI', icon: 'spark', run: guard(async () => { const t0 = toast('Scoring with AI...', { ms: 600000 }); try { await aiScore(id); refresh(); toast('Score updated.'); } finally { t0.remove(); } }) }, '-',
        { label: 'Delete program', icon: 'trash', danger: true, run: () => deleteProgram(id) }].filter(Boolean));
    }
    case 'star': { const { p } = IDX.prog.get(id); return toggleApply(id, !p.apply); }
    case 'group': { const k = a.dataset.key; S.closed.has(k) ? S.closed.delete(k) : S.closed.add(k); store.set('closed', [...S.closed]); return renderList(); }
    case 'open-id': return openDrawer('program', a.dataset.id);
    case 'toggle-free': S.f.free = !S.f.free; store.set('filters', S.f); return viewPrograms();
    case 'toggle-mine': S.f.mine = !S.f.mine; store.set('filters', S.f); return viewPrograms();
    case 'clear-filters': S.f = { q: '', country: '', stage: '', tag: '', free: false, mine: false, sort: S.f.sort, group: S.f.group }; store.set('filters', S.f); return viewPrograms();
    case 'add-program': return addProgramModal();
    case 'add-prof': return addProfModal(a.dataset.uni);
    case 'ai-batch': {
      const m = openModal(`<h2>Score with AI</h2><p class="muted">The AI writes only the score and a short explanation. Scores you set by hand are skipped.</p><div class="field"><span>Which programs?</span><select id="bs"><option value="unscored">Not scored yet</option><option value="estimates">Only estimates</option><option value="mine">The ones I'm applying to</option><option value="visible">Everything currently shown</option></select></div><p class="muted small">Each program is one AI request. A local model may take a while per program; you can stop at any time.</p><div class="actions"><button class="btn" data-act="close-modal">Cancel</button><button class="btn primary" data-act="ai-batch-go">Start</button></div>`); return m;
    }
    case 'ai-batch-go': { const sc = $('#bs').value; closeModal(); return batchScore(sc); }
    case 'card': if (t.closest('.ring')) return; return openDrawer('program', id);
    case 'prof': if (t.closest('select,button,a,input')) return; return openDrawer('prof', id);
    case 'open-prof': return openDrawer('prof', a.dataset.id);
    case 'copy-email': { try { await navigator.clipboard.writeText(a.dataset.email); toast('Email copied.'); } catch { toast(a.dataset.email); } return; }
    case 'dtab': S.drawer.tab = a.dataset.tab; return renderDrawer();
    case 'del-program': return deleteProgram(S.drawer.id);
    case 'del-prof': return deleteProf(S.drawer.id);
    case 'dl-add': { const h = document.createElement('div'); h.className = 'kv'; h.innerHTML = `<input data-dlk placeholder="winter"><input data-dlv placeholder="2027-05-31"><button type="button" class="icon-btn" data-act="dl-del">${icon('x')}</button>`; $('#dl-edit').appendChild(h); $('input', h).focus(); return; }
    case 'dl-del': { a.closest('.kv').remove(); return saveDeadlines(); }
    case 'score-manual': { const v = $('#manual-score').value; if (v === '') return toast('Enter a number from 0 to 100.', { err: true }); return scoreAct({ action: 'manual', value: v, lock: true }, 'Score saved and locked.'); }
    case 'score-rule': return scoreAct({ action: 'rule' }, 'Estimate applied.');
    case 'score-clear': return scoreAct({ action: 'clear' }, 'Score cleared.');
    case 'score-unlock': return scoreAct({ action: 'unlock' }, 'Unlocked.');
    case 'score-ai': {
      const b = a; b.disabled = true; b.innerHTML = '<span class="spinner"></span> Scoring...';
      try { await aiScore(S.drawer.id); refresh(); renderDrawer(); toast('Score updated by AI.'); } catch (er) { toast(er.message, { err: true }); renderDrawer(); } return;
    }
    // profile
    case 'pick-files': return $('#filepick').click();
    case 'paste-doc': { const m = openModal(`<h2>Paste text</h2><label class="field"><span>Title</span><input id="pd-t" value="notes"></label><label class="field"><span>Text</span><textarea id="pd-x" rows="10"></textarea></label><div class="actions"><button class="btn" data-act="close-modal">Cancel</button><button class="btn primary" data-act="paste-save">Save</button></div>`); return m; }
    case 'paste-save': { const fd = new FormData(); fd.append('text', $('#pd-x').value); fd.append('title', $('#pd-t').value); closeModal(); return uploadDocs(fd); }
    case 'del-doc': { const r = await api('POST', '/api/docs/delete', { name: a.dataset.name }).catch(er => toast(er.message, { err: true })); if (r) { S.docs = r.docs; $('#doclist').innerHTML = docListHTML(); } return; }
    case 'add-pfield': { const inp = $('#newpf'), k = inp.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''); if (!k) return; S.profile[k] = S.profile[k] || ''; await saveProfile(); viewMe(); $('#pf-' + k)?.focus(); return; }
    case 'del-pfield': { delete S.profile[a.dataset.key]; await saveProfile(); return viewMe(); }
    case 'ai-profile': return aiProfile(a);
    case 'apply-proposals': {
      $$('#prop-list input:checked').forEach(c => { const p = c.dataset; S.profile[p.key] = p.val; });
      closeModal(); await saveProfile(); viewMe(); return toast('Profile updated.');
    }
    // assistant
    case 'chat-send': return sendChat($('#cin').value);
    case 'suggest': return sendChat(a.textContent);
    case 'chat-clear': { await api('POST', '/api/chat/clear', {}).catch(() => 0); S.chat = []; return renderMsgs(); }
    case 'dismiss-actions': { S.chat[S.chat.length - 1].done = true; return renderMsgs(); }
    case 'apply-actions': {
      const last = S.chat[S.chat.length - 1], sel = $$('.act input:checked').map(c => last.actions[+c.dataset.aj]);
      if (!sel.length) return;
      try { const r = await api('POST', '/api/actions/apply', { actions: sel }); applyState(r); last.done = true; renderRail(); renderMsgs(); toast(`Applied ${r.applied.length} change${r.applied.length === 1 ? '' : 's'}.`); } catch (er) { toast(er.message, { err: true }); }
      return;
    }
    // import
    case 'make-prompt': return makePrompt();
    case 'make-convert': return makeConvert();
    case 'copy-prompt': { const ta = $('#prompttext'); try { await navigator.clipboard.writeText(ta.value); } catch { ta.select(); document.execCommand('copy'); } return toast('Prompt copied. Paste it into your AI.'); }
    case 'imp-file': return $('#imp-file').click();
    case 'imp-preview': return impRun(false);
    case 'imp-commit': return impRun(true);
    // settings
    case 's-test': { const o = $('#s-test'); o.innerHTML = '<span class="spinner"></span> Testing...'; await saveSettingsQuiet(); try { const r = await api('POST', '/api/settings/test', {}); o.style.color = 'var(--good)'; o.textContent = `Connected (${r.seconds}s): ${r.reply}`; } catch (er) { o.style.color = 'var(--bad)'; o.textContent = er.message; } return; }
    case 's-save': return saveSettings();
    case 'a-save': return saveAccount();
    case 'health': return healthModal();
    case 'health-fix': { const r = await api('POST', '/api/health/fix', {}).catch(er => toast(er.message, { err: true })); if (r) { applyState(r); renderRail(); renderView(); closeModal(); toast(r.report.length ? `Fixed: ${r.report.length} change(s).` : 'Nothing needed fixing.'); } return; }
    case 'logout': { await api('POST', '/api/logout', {}).catch(() => 0); location.href = '/login'; return; }
  }
});
$('#scrim').addEventListener('click', closeDrawer);

async function saveSettingsQuiet() { const body = { ai_base_url: $('#s-url').value, ai_model: $('#s-model').value, ai_timeout: +$('#s-timeout').value || 300 }; const k = $('#s-key').value; if (k) body.ai_api_key = k; try { S.settings = (await api('PUT', '/api/settings', body)).settings; } catch { /* shown by test */ } }
const saveAccount = guard(async () => {
  const name = $('#a-name').value.trim(); if (name && name !== S.user.display_name) { S.user = (await api('POST', '/api/account/name', { name })).user; renderRail(); }
  const o = $('#a-old').value, n = $('#a-new').value; if (o || n) { await api('POST', '/api/account/password', { old: o, new: n }); $('#a-old').value = $('#a-new').value = ''; }
  toast('Account updated.');
});
const scoreAct = guard(async (body, msg) => { const r = await api('POST', '/api/program/score', { id: S.drawer.id, ...body }); patchLocalProgram(r.program); refresh(); renderDrawer(); toast(msg); });
const saveDeadlines = guard(async () => {
  const d = {}; $$('#dl-edit .kv').forEach(r => { const k = $('[data-dlk]', r).value.trim(), v = $('[data-dlv]', r).value.trim(); if (k && v) d[k] = v; });
  await updateProgram(S.drawer.id, { deadlines: d }); savedMark();
});
const uploadDocs = guard(async fd => { const r = await api('POST', '/api/docs', fd); S.docs = r.docs; if ($('#doclist')) $('#doclist').innerHTML = docListHTML(); toast(r.errors.length ? r.errors.join(' ') : `Added ${r.added.length} document${r.added.length === 1 ? '' : 's'}.`, { err: !!r.errors.length }); });
const aiProfile = guard(async btn => {
  btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = '<span class="spinner"></span> Reading your documents...';
  try {
    const r = await api('POST', '/api/profile/ai-extract', { extra: $('#extra').value });
    if (!r.proposals.length) return toast('The AI found nothing new to add.');
    openModal(`<h2>Proposed profile updates</h2><p class="muted">${esc(r.summary || '')}</p><div id="prop-list">${r.proposals.map(p => `<label class="proposal"><input type="checkbox" checked data-key="${esc(p.key)}" data-val="${esc(p.new)}"><div><b>${esc(p.label)}</b>${p.old ? `<div class="old">${esc(p.old)}</div>` : ''}<div class="new">${esc(p.new)}</div></div></label>`).join('')}</div><div class="actions"><button class="btn" data-act="close-modal">Cancel</button><button class="btn primary" data-act="apply-proposals">Apply selected</button></div>`, { wide: true, noFocus: true });
  } finally { btn.disabled = false; btn.innerHTML = old; }
});
const makePrompt = guard(async () => {
  const g = id => $('#' + id).value;
  Object.assign(S.imp, { countries: g('ip-countries'), level: g('ip-level'), fields: g('ip-fields'), intake: g('ip-intake'), language: g('ip-language'), tuition: g('ip-tuition'), count: g('ip-count'), extra: g('ip-extra') });
  S.imp.focus = g('ip-focus');
  const r = await api('POST', '/api/import/prompt', { focus: S.imp.focus, countries: S.imp.countries, level: S.imp.level, fields: S.imp.fields, intake: S.imp.intake, language: S.imp.language, max_tuition: S.imp.tuition, count: +S.imp.count || 10, extra: S.imp.extra,
    professors: $('#ip-profs').checked, include_profile: $('#ip-prof').checked, skip_existing: $('#ip-skip').checked });
  S.imp.prompt = r.prompt; S.imp.tag = r.tag; S.imp.kind = 'Research prompt'; $('#prompt-kind').textContent = 'Research prompt: paste it into an AI with web search switched on.'; $('#prompttext').value = r.prompt; $('#promptout').hidden = false; $('#promptout').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});
const makeConvert = guard(async () => {
  S.imp.focus = $('#ip-focus').value;
  const r = await api('POST', '/api/import/prompt', { convert: true, focus: S.imp.focus });
  S.imp.prompt = r.prompt; S.imp.tag = r.tag; S.imp.kind = 'Convert prompt';
  $('#prompt-kind').textContent = 'Convert prompt: send it in the SAME chat where the AI gave you its list.';
  $('#prompttext').value = r.prompt; $('#promptout').hidden = false; $('#promptout').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});
const impRun = guard(async commit => {
  S.imp.text = $('#imp-text').value; S.imp.mode = $('#imp-mode').value;
  const r = await api('POST', commit ? '/api/import/commit' : '/api/import/preview', { text: S.imp.text, mode: S.imp.mode, tag: FOCUS_TAG[($('#ip-focus') || {}).value || 'general'] || '' });
  if (!commit) { S.imp.preview = r; $('#imp-out').innerHTML = previewHTML(r); return; }
  applyState(r); S.imp = { prompt: S.imp.prompt, preview: null, text: '', mode: S.imp.mode, ...S.imp, text: '', preview: null };
  renderRail(); renderView(); toast(`Imported: ${r.counts.new_programs} new and ${r.counts.updated_programs} updated programs.`, { ms: 5000 });
});

document.addEventListener('change', async e => {
  const t = e.target;
  if (t.matches('select[data-filter]')) { S.f[t.dataset.filter] = t.value; store.set('filters', S.f); return viewPrograms(); }
  if (t.matches('select[data-pfilter]')) { S.pf[t.dataset.pfilter] = t.value; return viewProfessors(); }
  if (t.matches('select[data-act=stage]')) { t.dataset.stage = t.value; return updateProgram(t.closest('[data-id]').dataset.id, { stage: t.value }); }
  if (t.matches('select[data-act=outreach]')) { const id = t.closest('[data-id]').dataset.id; const r = await api('POST', '/api/prof/update', { id, patch: { outreach_status: t.value } }).catch(er => toast(er.message, { err: true })); if (r) { const x = IDX.prof.get(id); Object.assign(x.q, r.professor); } return; }
  if (t.matches('#s-theme button')) return;
  if (t.id === 'ip-focus') { S.imp.focus = t.value; $('#ip-hint').textContent = FOCUS_HINT[t.value]; S.imp.tag = ''; return; }
  if (t.matches('#imp-file')) { const f = t.files[0]; if (!f) return; const txt = await f.text(); $('#imp-text').value = txt; S.imp.text = txt; return toast(`Loaded ${f.name}. Click Check.`); }
  if (t.matches('#filepick')) { const fd = new FormData(); [...t.files].forEach(f => fd.append('files', f)); t.value = ''; return uploadDocs(fd); }
  // drawer autosave
  if (S.drawer && t.closest('#drawer')) {
    if (t.matches('[data-dlk],[data-dlv]')) return saveDeadlines();
    const d = S.drawer;
    if (t.matches('[data-f]')) {
      const k = t.dataset.f; let v = t.value;
      if (k === 'apply') v = v === 'true';
      if (k === 'sources') v = v.split('\n').map(x => x.trim()).filter(Boolean);
      if (k === 'tags') v = v.split(/[,;]/).map(x => x.trim()).filter(Boolean);
      const p = await updateProgram(d.id, { [k]: v });
      if (p) { savedMark(); if (k === 'name' || k === 'official_link' || k === 'stage') { const keep = d.tab; renderDrawer(); } }
      return;
    }
    if (t.matches('[data-uf]')) {
      const e2 = IDX.prog.get(d.id); const r = await api('POST', '/api/uni/update', { id: e2.u.id, patch: { [t.dataset.uf]: t.value } }).catch(er => toast(er.message, { err: true }));
      if (r) { Object.assign(e2.u, r.university); savedMark(); refresh(); } return;
    }
    if (t.matches('[data-qf]')) {
      const k = t.dataset.qf; let v = t.value; if (k === 'sources') v = v.split('\n').map(x => x.trim()).filter(Boolean);
      const r = await api('POST', '/api/prof/update', { id: d.id, patch: { [k]: v } }).catch(er => { toast(er.message, { err: true }); savedMark(false); });
      if (r) { const x = IDX.prof.get(d.id); Object.assign(x.q, r.professor); savedMark(); if (S.view === 'professors') viewProfessors(); } return;
    }
  }
});
document.addEventListener('input', e => {
  const t = e.target;
  if (t.id === 'q') { S.f.q = t.value; store.set('filters', S.f); return renderList(); }
  if (t.id === 'pq') { S.pf.q = t.value; const pos = t.selectionStart; viewProfessors(); const n = $('#pq'); n.focus(); n.setSelectionRange(pos, pos); return; }
  if (t.matches('[data-pkey]')) { S.profile[t.dataset.pkey] = t.value; autoGrow(t); clearTimeout(profTimer); profTimer = setTimeout(saveProfile, 700); }
  if (t.tagName === 'TEXTAREA') autoGrow(t);
});
document.addEventListener('click', e => { const b = e.target.closest('#s-theme button'); if (b) { $$('#s-theme button').forEach(x => x.classList.toggle('on', x === b)); document.documentElement.dataset.theme = b.dataset.theme === 'auto' ? '' : b.dataset.theme; if (b.dataset.theme === 'auto') delete document.documentElement.dataset.theme; } });
document.addEventListener('keydown', e => {
  const tag = (e.target.tagName || '').toLowerCase(), typing = ['input', 'textarea', 'select'].includes(tag);
  if (e.key === 'Escape') { if (menuEl) return closeMenu(); if (!$('#modal').hidden) return closeModal(); if (S.drawer) return closeDrawer(); }
  if (e.key === 'Enter' && !e.shiftKey && e.target.id === 'cin') { e.preventDefault(); return sendChat(e.target.value); }
  if (e.key === 'Enter' && e.target.matches?.('.row,.prow,.card') && !typing) { e.target.click(); return; }
  if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === '/' && S.view === 'programs') { e.preventDefault(); $('#q')?.focus(); }
  if (e.key === 'n' && S.view === 'programs') { e.preventDefault(); addProgramModal(); }
});
// drag and drop between pipeline stages, and file drop on profile page
document.addEventListener('dragstart', e => { const c = e.target.closest?.('.card'); if (c) { e.dataTransfer.setData('text/plain', c.dataset.id); c.classList.add('dragging'); } });
document.addEventListener('dragend', e => { e.target.classList?.remove('dragging'); $$('.col.over').forEach(c => c.classList.remove('over')); });
document.addEventListener('dragover', e => { const c = e.target.closest?.('.col'); if (c) { e.preventDefault(); $$('.col.over').forEach(x => x !== c && x.classList.remove('over')); c.classList.add('over'); } const d = e.target.closest?.('#drop'); if (d) { e.preventDefault(); d.classList.add('over'); } });
document.addEventListener('dragleave', e => { e.target.closest?.('#drop')?.classList.remove('over'); });
document.addEventListener('drop', e => {
  const c = e.target.closest?.('.col');
  if (c) { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'), st = c.dataset.stage, x = IDX.prog.get(id); if (x && x.p.stage !== st) updateProgram(id, { stage: st }).then(() => viewPipeline()); return; }
  const d = e.target.closest?.('#drop');
  if (d) { e.preventDefault(); d.classList.remove('over'); const fd = new FormData(); [...e.dataTransfer.files].forEach(f => fd.append('files', f)); uploadDocs(fd); }
});

// ---------- boot ----------
(async function boot() {
  try {
    applyState(await api('GET', '/api/state'));
    if (!NAV.some(n => n[0] === S.view)) S.view = 'programs';
    renderRail(); renderView();
  } catch (e) {
    $('#view').innerHTML = `<div class="empty"><h3>Could not load your data</h3><p>${esc(e.message)}</p><button class="btn" onclick="location.reload()">Try again</button></div>`;
  }
})();
})();
