/* Студія шаблонів: один сторінковий інтерфейс над JSON API (app/api.py).
 *
 * Правила цього файла:
 *  - будь-який рядок, що прийшов із даних чи файлів, потрапляє на сторінку лише через textContent /
 *    setAttribute / createElement (helper el); жодного вставлення HTML-рядків і жодного виконання рядків як коду;
 *  - src картинок — лише шляхи /files/... з відповідей API; href — лише фіксований префікс + перевірений id;
 *  - кожен POST/PUT іде з Content-Type: application/json (без тіла — {});
 *  - опитування: GET /api/jobs (+ /api/health) кожні 3 с ланцюжком setTimeout, GET /api/gen поки є
 *    генерації в очікуванні; форми, які редагує власник, опитування не перемальовує.
 */
(function () {
  'use strict';

  var STEPS = ['style', 'images', 'texts', 'apply', 'verify'];
  var STEP_TITLES = { style: 'Стиль', images: 'Картинки', texts: 'Тексти', apply: 'Запис у Canva', verify: 'Перевірка' };
  var STATUS_LABELS = { draft: 'чернетка', waiting_claude: 'чекає Claude', review: 'готово до перегляду', approved: 'затверджено', stale: 'застаріло' };
  var JOB_STATE_LABELS = { pending: 'у черзі', running: 'виконується', done: 'виконано', failed: 'збій', corrupt: 'пошкоджене' };
  var RESULT_LABELS = { done: 'успішно', failed: 'не вдалося', corrupt: 'результат пошкоджено' };
  var JOB_TYPE_LABELS = { map_skeleton: 'Карта скелета', style_directions: 'Напрями стилю', write_texts: 'Написання текстів', apply_canva: 'Запис у Canva', verify: 'Перевірка в Canva' };
  var GEN_STATE_LABELS = { queued: 'у черзі', running: 'генерується', done: 'готово', failed: 'збій', unknown: 'невідомо' };
  var POLL_MS = 3000;
  var FONT_ROLES = ['heading', 'body', 'script'];
  var SEAL_HINT = 'Якщо ви змінили печатку, конверт потрібно перегенерувати: натисніть «Ще раз» на картці «envelope».';
  var STALE_STEP_APPROVABLE = ['style', 'images', 'texts'];

  var S = {
    route: { view: 'home', name: null, step: null },
    templates: [], skeletons: [], jobs: [], tplErrors: {}, health: null,
    tpl: null, tplError: null, skel: null,
    dirty: false, renderedStep: null, renderToken: 0,
    jobSig: null, genSig: null, queue: null,
    promptDraft: {}, styleDraft: null,
    started: false
  };
  var resultCache = {};

  /* ------------------------------------------------------------------ DOM helpers */
  function qs(id) { return document.getElementById(id); }
  function enc(s) { return encodeURIComponent(s); }

  function el(tag, props) {
    var n = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') n.className = v;
        else if (k === 'text') n.textContent = String(v);
        else if (k === 'on') Object.keys(v).forEach(function (ev) { n.addEventListener(ev, v[ev]); });
        else if (k === 'value') n.value = v;
        else if (k === 'checked' || k === 'disabled' || k === 'hidden' || k === 'selected') n[k] = true;
        else n.setAttribute(k, v === true ? '' : String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) addKid(n, arguments[i]);
    return n;
  }
  function addKid(n, kid) {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) { kid.forEach(function (k) { addKid(n, k); }); return; }
    if (typeof kid === 'string' || typeof kid === 'number') { n.appendChild(document.createTextNode(String(kid))); return; }
    n.appendChild(kid);
  }
  function clear(n) { n.replaceChildren(); return n; }
  function idSafe(s) { return String(s).replace(/[^A-Za-z0-9_-]/g, '_'); }
  function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function strOr(v, d) { return typeof v === 'string' ? v : d; }
  function cpLen(s) { return Array.from(s).length; }

  function badge(text, cls) { return el('span', { class: 'badge ' + (cls || ''), text: text }); }
  function statusBadge(status) { return badge(STATUS_LABELS[status] || String(status), 'b-' + idSafe(status)); }

  function fmtAge(sec) {
    if (typeof sec !== 'number') return '';
    if (sec < 60) return sec + ' с тому';
    if (sec < 3600) return Math.floor(sec / 60) + ' хв тому';
    if (sec < 86400) return Math.floor(sec / 3600) + ' год тому';
    return Math.floor(sec / 86400) + ' д тому';
  }

  /* ------------------------------------------------------------------ API */
  function ApiError(status, message, data) { this.status = status; this.message = message; this.data = data; }
  function NetError(message) { this.message = message; }

  function api(method, path, body) {
    var opt = { method: method, headers: {} };
    if (method !== 'GET') {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body === undefined ? {} : body);
    }
    return fetch(path, opt).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) {
          var msg = data && typeof data.error === 'string' ? data.error : 'Помилка ' + res.status;
          throw new ApiError(res.status, msg, data);
        }
        return data;
      });
    }, function (e) {
      throw new NetError('Сервер студії не відповідає: ' + (e && e.message ? e.message : e));
    });
  }

  function errorText(e) {
    if (e instanceof ApiError) {
      var t = e.message;
      var p = e.data && Array.isArray(e.data.problems) ? e.data.problems.filter(function (x) { return typeof x === 'string'; }) : [];
      // the message already joins the problems with "; ": list them separately only when they are not in it
      if (p.length && t.indexOf(p[0]) === -1) t += ' ' + p.join('; ');
      return t;
    }
    if (e instanceof NetError) return e.message;
    return 'Непередбачена помилка інтерфейсу: ' + (e && e.message ? e.message : e);
  }

  /* ------------------------------------------------------------------ messages */
  function setMsg(id, text, kind) {
    var n = qs(id);
    if (!n) return;
    if (!text) { n.hidden = true; clear(n); return; }
    clear(n);
    n.className = 'msg ' + (kind === 'err' ? 'msg-err' : kind === 'ok' ? 'msg-ok' : kind === 'warn' ? 'msg-warn' : '');
    n.setAttribute('role', kind === 'err' ? 'alert' : 'status');
    var lines = Array.isArray(text) ? text : [text];
    n.appendChild(el('span', { text: lines[0] }));
    if (lines.length > 1) n.appendChild(el('ul', null, lines.slice(1).map(function (l) { return el('li', { text: l }); })));
    n.hidden = false;
  }
  function showBanner(text) { qs('error-banner-text').textContent = text; qs('error-banner').hidden = false; }
  function hideBanner() { qs('error-banner').hidden = true; }

  /* run `fn` with the button disabled; the button label may change meanwhile */
  function busy(btn, label, fn) {
    if (btn.disabled) return Promise.resolve();
    var prev = btn.textContent;
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    if (label) btn.textContent = label;
    var done = function () { btn.disabled = false; btn.removeAttribute('aria-busy'); btn.textContent = prev; };
    return Promise.resolve().then(fn).then(function (v) { done(); return v; }, function (e) { done(); throw e; });
  }

  /* ------------------------------------------------------------------ routing */
  function parseRoute() {
    var h = (location.hash || '').replace(/^#/, '');
    var parts = h.split('/').filter(function (x) { return x !== ''; });
    try {
      if (parts[0] === 's' && parts[1]) return { view: 'skeleton', name: decodeURIComponent(parts[1]), step: null };
      if (parts[0] === 't' && parts[1]) {
        var step = parts[2] && STEPS.indexOf(parts[2]) !== -1 ? parts[2] : null;
        return { view: 'template', name: decodeURIComponent(parts[1]), step: step };
      }
    } catch (e) { /* malformed escape: fall through to home */ }
    return { view: 'home', name: null, step: null };
  }

  function showScreen(which) {
    ['home', 'skeleton', 'template', 'missing'].forEach(function (v) { qs('screen-' + v).hidden = (v !== which); });
  }

  function missing(text) {
    showScreen('missing');
    qs('missing-text').textContent = text;
  }

  function onRoute() {
    var next = parseRoute();
    var sameTpl = next.view === 'template' && S.route.view === 'template' && S.route.name === next.name;
    S.route = next;
    S.dirty = false;
    qs('stale-notice').hidden = true;
    if (!sameTpl) { S.tpl = null; S.tplError = null; S.promptDraft = {}; S.styleDraft = null; S.genSig = null; }
    if (next.view === 'home') { showScreen('home'); loadHome(); }
    else if (next.view === 'skeleton') { loadSkeletonScreen(); }
    else if (sameTpl && S.tpl) { renderTemplate(false); }
    else { loadTemplateScreen(); }
  }

  /* ------------------------------------------------------------------ health */
  function renderHealth() {
    var h = S.health, box = qs('health');
    clear(box);
    if (!h) return;
    box.appendChild(el('span', { id: 'health-disk', text: 'Диск моделей: ' + (h.models_mounted ? 'змонтовано' : 'НЕ змонтовано') }));
    box.appendChild(document.createTextNode(' · '));
    box.appendChild(el('span', { id: 'health-comfy', text: 'ComfyUI: ' + strOr(h.comfy_url, '?') }));
  }

  /* ------------------------------------------------------------------ jobs: normalisation and rendering */
  function normJob(j) {
    var r = isObj(j.result) ? j.result : null;
    return {
      id: String(j.id), type: strOr(j.type, null), template: strOr(j.template, null), skeleton: strOr(j.skeleton, null),
      state: strOr(j.state, '?'), age: fmtAge(j.age_s), error: strOr(j.error, null),
      status: r ? r.status : null, summary: r ? r.summary : null
    };
  }
  function normTplJob(j) {
    return { id: String(j.job_id), type: strOr(j.type, null), template: null, skeleton: null, state: strOr(j.folder, '?'), age: '', error: null, status: j.status, summary: j.summary, created: strOr(j.created_utc, '') };
  }

  function jobsTable(rows, showWhere) {
    if (!rows.length) return el('p', { class: 'muted', text: 'Завдань ще немає.' });
    var head = el('tr', null, el('th', { scope: 'col', text: 'Завдання' }), showWhere ? el('th', { scope: 'col', text: 'Де' }) : null,
      el('th', { scope: 'col', text: 'Стан' }), el('th', { scope: 'col', text: 'Результат' }));
    var body = rows.map(function (j) {
      var bad = j.state === 'corrupt' || j.status === 'failed' || j.status === 'corrupt';
      var resultCell = [];
      if (j.state === 'corrupt') resultCell.push(el('div', { class: 'msg-err', text: 'Файл завдання пошкоджено' + (j.error ? ': ' + j.error : '') }));
      else if (j.status) resultCell.push(badge(RESULT_LABELS[j.status] || String(j.status), 'b-' + idSafe(j.status)));
      else resultCell.push(el('span', { class: 'muted', text: 'результату ще немає' }));
      if (j.summary) resultCell.push(el('div', { class: bad ? 'msg-err' : '', text: j.summary }));
      return el('tr', { 'data-test': 'job-row', 'data-job-state': j.state, 'data-job-status': j.status || '' },
        el('td', null, el('div', { text: JOB_TYPE_LABELS[j.type] || j.type || 'невідомий тип' }), el('div', { class: 'mono muted', text: j.id + (j.age ? ' · ' + j.age : '') + (j.created ? ' · ' + j.created : '') })),
        showWhere ? el('td', { text: j.template ? 'шаблон ' + j.template : j.skeleton ? 'скелет ' + j.skeleton : '—' }) : null,
        el('td', null, badge(JOB_STATE_LABELS[j.state] || j.state, 'b-' + idSafe(j.state))),
        el('td', null, resultCell));
    });
    return el('div', { class: 'table-wrap' }, el('table', null, el('thead', null, head), el('tbody', null, body)));
  }

  /* ------------------------------------------------------------------ HOME */
  function loadHome() {
    return Promise.all([api('GET', '/api/templates'), api('GET', '/api/skeletons'), api('GET', '/api/jobs'), api('GET', '/api/health')])
      .then(function (r) {
        S.templates = r[0].templates || [];
        S.skeletons = r[1].skeletons || [];
        S.jobs = r[2].jobs || [];
        S.tplErrors = r[2].template_errors || {};
        S.health = r[3];
        S.jobSig = jobsSig(r[2]);
        hideBanner();
        renderHealth();
        renderHome();
      })
      .catch(function (e) { showBanner(errorText(e)); });
  }

  function stepBadges(steps) {
    return el('div', { class: 'badges' }, STEPS.map(function (s) {
      var st = steps && steps[s];
      return badge(STEP_TITLES[s] + ': ' + (STATUS_LABELS[st] || '?'), 'b-' + idSafe(st || 'draft'));
    }));
  }

  function renderHome() {
    var tl = clear(qs('template-list'));
    if (!S.templates.length) tl.appendChild(el('p', { class: 'muted', text: 'Шаблонів ще немає. Створіть перший нижче.' }));
    var ul = el('ul', { class: 'item-list' });
    S.templates.forEach(function (t) {
      var name = String(t.name);
      if (t.error) {
        ul.appendChild(el('li', { 'data-test': 'template-row', 'data-name': name, 'data-error': 'true' },
          el('div', { class: 'item-title', text: name }),
          el('div', { class: 'badges' }, badge('шаблон пошкоджено', 'b-corrupt')),
          el('div', { class: 'msg-err', text: String(t.error) })));
        return;
      }
      ul.appendChild(el('li', { 'data-test': 'template-row', 'data-name': name },
        el('a', { class: 'item-title', href: '#/t/' + enc(name), text: name }),
        el('div', { class: 'muted', text: 'скелет: ' + strOr(t.skeleton, '—') }),
        stepBadges(t.steps)));
    });
    if (S.templates.length) tl.appendChild(ul);

    var sel = qs('tpl-skeleton');
    var prev = sel.value;
    clear(sel);
    sel.appendChild(el('option', { value: '', text: S.skeletons.length ? '— оберіть скелет —' : 'спершу створіть скелет' }));
    S.skeletons.forEach(function (s) { sel.appendChild(el('option', { value: s.name, text: s.name + (s.has_map ? '' : ' (карти ще немає)') })); });
    if (prev) sel.value = prev;

    var sl = clear(qs('skeleton-list'));
    if (!S.skeletons.length) sl.appendChild(el('p', { class: 'muted', text: 'Скелетів ще немає. Створіть перший нижче.' }));
    var sul = el('ul', { class: 'item-list' });
    S.skeletons.forEach(function (s) {
      var name = String(s.name), job = s.job;
      var bs = [badge(s.has_map ? 'карта є' : 'карти ще немає', s.has_map ? 'b-approved' : 'b-draft')];
      if (job && job.status) bs.push(badge('карта: ' + (RESULT_LABELS[job.status] || job.status), 'b-' + idSafe(job.status)));
      else if (job) bs.push(badge('чекає Claude', 'b-waiting_claude'));
      sul.appendChild(el('li', { 'data-test': 'skeleton-row', 'data-name': name },
        el('a', { class: 'item-title', href: '#/s/' + enc(name), text: name }),
        el('div', { class: 'muted', text: 'дизайн Canva: ' + strOr(s.design_id, '—') }),
        el('div', { class: 'badges' }, bs),
        job && job.summary && (job.status === 'failed' || job.status === 'corrupt') ? el('div', { class: 'msg-err', text: job.summary }) : null));
    });
    if (S.skeletons.length) sl.appendChild(sul);
    renderJobsPanel();
  }

  function renderJobsPanel() {
    var te = clear(qs('template-errors'));
    var names = Object.keys(S.tplErrors || {});
    names.forEach(function (n) {
      te.appendChild(el('div', { class: 'msg msg-err', 'data-test': 'template-error' }, el('span', { text: 'Шаблон «' + n + '»: ' + String(S.tplErrors[n]) })));
    });
    var rows = S.jobs.map(normJob).reverse();
    var attention = rows.filter(function (j) { return j.state === 'corrupt' || j.status === 'failed' || j.status === 'corrupt'; });
    if (attention.length) {
      te.appendChild(el('div', { class: 'msg msg-err', role: 'alert', 'data-test': 'jobs-attention' },
        el('span', { text: 'Потребують уваги: ' + attention.length + ' (збої та пошкоджені завдання нижче позначені червоним).' })));
    }
    clear(qs('jobs-panel')).appendChild(jobsTable(rows.slice(0, 40), true));
  }

  function jobsSig(payload) {
    var rows = (payload.jobs || []).map(function (j) { return [j.id, j.state, j.result ? j.result.status : null, j.result ? j.result.summary : null]; });
    return JSON.stringify([rows, payload.template_errors || {}]);
  }

  function onCreateTemplate(ev) {
    ev.preventDefault();
    var btn = qs('btn-create-template');
    var body = { name: qs('tpl-name').value, skeleton: qs('tpl-skeleton').value, brief: qs('tpl-brief').value };
    busy(btn, 'Створюю…', function () { return api('POST', '/api/templates', body); }).then(function (r) {
      if (!r) return;
      qs('tpl-name').value = ''; qs('tpl-brief').value = '';
      location.hash = '#/t/' + enc(r.name);
    }).catch(function (e) { setMsg('msg-home', errorText(e), 'err'); });
  }

  function onCreateSkeleton(ev) {
    ev.preventDefault();
    var btn = qs('btn-create-skeleton');
    var body = { name: qs('sk-name').value, design_id: qs('sk-design').value };
    busy(btn, 'Створюю…', function () { return api('POST', '/api/skeletons', body); }).then(function (r) {
      if (!r) return;
      qs('sk-name').value = ''; qs('sk-design').value = '';
      location.hash = '#/s/' + enc(r.name);
    }).catch(function (e) { setMsg('msg-home', errorText(e), 'err'); });
  }

  /* ------------------------------------------------------------------ job result block */
  function jobBlock(info, emptyText) {
    if (!info || !info.status) {
      return emptyText ? el('div', { class: 'msg', 'data-test': 'job-block', 'data-job-status': 'none' }, el('span', { text: emptyText })) : null;
    }
    var kind = info.status === 'done' ? 'msg msg-ok' : 'msg msg-err';
    var label = RESULT_LABELS[info.status] || String(info.status);
    var kids = [el('div', null,
      el('strong', { text: (JOB_TYPE_LABELS[info.type] || info.type || 'Завдання') + ': ' + label + '. ' }),
      info.summary ? el('span', { text: info.summary }) : null,
      el('div', { class: 'mono muted', text: strOr(info.job_id, '') }))];
    if (info.copy_missing) kids.push(el('div', { class: 'msg-err', 'data-test': 'copy-missing', text: 'Claude не записав id копії — перевірте /studio. Повторний запис вимкнено, поки id копії не з’явиться.' }));
    return el('div', { class: kind, 'data-test': 'job-block', 'data-job-status': info.status }, kids);
  }

  function getResult(info) {
    if (!info || !info.job_id || info.status === 'corrupt' || !S.route.name) return Promise.resolve(null);
    var key = S.route.name + '/' + info.job_id;
    if (resultCache[key]) return Promise.resolve(resultCache[key]);
    return fetch('/files/templates/' + enc(S.route.name) + '/jobs/' + enc(info.job_id) + '.result.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (isObj(d)) resultCache[key] = d; return isObj(d) ? d : null; })
      .catch(function () { return null; });
  }

  /* ------------------------------------------------------------------ SKELETON screen */
  function loadSkeletonScreen() {
    showScreen('skeleton');
    qs('sk-title').textContent = 'Скелет ' + S.route.name;
    setMsg('msg-skeleton', '');
    api('GET', '/api/skeletons/' + enc(S.route.name)).then(function (d) {
      S.skel = d;
      hideBanner();
      renderSkeleton(false);
    }).catch(function (e) {
      if (e instanceof ApiError && e.status === 404) missing('Скелет «' + S.route.name + '» не знайдено.');
      else showBanner(errorText(e));
    });
    api('GET', '/api/health').then(function (h) { S.health = h; renderHealth(); }).catch(function () {});
  }

  function pageThumb(skeleton, page) {
    var base = '/files/skeletons/' + enc(skeleton) + '/sections/' + enc(String(page.id));
    var img = el('img', { alt: 'Мініатюра секції «' + strOr(page.title, String(page.id)) + '»', loading: 'lazy' });
    var tried = 0;
    img.addEventListener('error', function () {
      tried += 1;
      if (tried === 1) img.setAttribute('src', base + '.jpg');
      else { img.hidden = true; note.hidden = false; }
    });
    var note = el('div', { class: 'hint', text: 'мініатюри немає', hidden: true });
    img.setAttribute('src', base + '.png');
    return el('div', { class: 'page-thumb', 'data-test': 'page-thumb', 'data-page': String(page.id) },
      el('div', null, el('strong', { text: String(page.index) + '. ' }), strOr(page.title, '')), img, note);
  }

  function renderSkeleton(respectDirty) {
    var d = S.skel;
    if (!d) return;
    if (respectDirty && S.dirty) return;
    S.dirty = false;
    var body = clear(qs('skeleton-body'));
    body.appendChild(el('p', null, 'Ідентифікатор дизайну в Canva: ', el('span', { class: 'mono', text: strOr(d.design_id, 'невідомий') })));
    var jb = jobBlock(d.job, 'Карту ще не складено. У сесії Claude Code виконайте /studio, щоб завдання «Карта скелета» виконалося.');
    if (jb) body.appendChild(jb);
    if (Array.isArray(d.map_problems) && d.map_problems.length) {
      body.appendChild(el('div', { class: 'msg msg-err', 'data-test': 'map-problems' }, el('div', null, el('strong', { text: 'Проблеми карти:' }), el('ul', null, d.map_problems.map(function (p) { return el('li', { text: String(p) }); })))));
    }
    var m = d.map;
    if (!isObj(m)) return;

    var pages = Array.isArray(m.pages) ? m.pages.filter(isObj) : [];
    body.appendChild(el('h2', { text: 'Секції' }));
    if (pages.length) body.appendChild(el('div', { class: 'page-thumbs', id: 'page-thumbs', 'data-test': 'page-thumbs' }, pages.map(function (p) { return pageThumb(d.name, p); })));
    else body.appendChild(el('p', { class: 'muted', text: 'У карті немає сторінок.' }));

    var slots = Array.isArray(m.slots) ? m.slots.filter(function (s) { return isObj(s) && typeof s.locator === 'string'; }) : [];
    body.appendChild(el('h2', { text: 'Слоти і ролі' }));
    body.appendChild(el('p', { class: 'hint', text: 'Роль слота підказує, що в ньому має бути. Виправте роль там, де Claude помилився, і збережіть.' }));
    var rows = slots.map(function (s, i) {
      var input = el('input', { type: 'text', id: 'role-' + i, value: strOr(s.role, ''), 'data-locator': s.locator, 'data-orig': strOr(s.role, ''), 'aria-label': 'Роль слота ' + s.locator });
      input.addEventListener('input', function () { S.dirty = true; });
      return el('tr', { 'data-test': 'slot-row' },
        el('td', { class: 'mono', text: s.locator }), el('td', { text: String(s.type) }),
        el('td', { text: s.asset ? String(s.asset) : '—' }),
        el('td', { text: s.personal ? 'персональне' : '' }),
        el('td', { text: typeof s.max_len === 'number' ? String(s.max_len) : '' }),
        el('td', null, input));
    });
    body.appendChild(el('div', { class: 'table-wrap' }, el('table', { id: 'slots-table', 'data-test': 'slots-table' },
      el('thead', null, el('tr', null, ['Слот', 'Тип', 'Картинка', 'Особисте', 'Макс. довжина', 'Роль'].map(function (h) { return el('th', { scope: 'col', text: h }); }))),
      el('tbody', null, rows))));
    var save = el('button', { type: 'button', id: 'save-roles', 'data-test': 'save-roles', class: 'btn btn-primary', text: 'Зберегти ролі' });
    save.addEventListener('click', function () { saveRoles(save); });
    body.appendChild(el('div', { class: 'actions' }, save));

    var assetNames = isObj(m.assets) ? Object.keys(m.assets) : [];
    if (assetNames.length) {
      body.appendChild(el('h2', { text: 'Картинки скелета' }));
      body.appendChild(el('div', { class: 'table-wrap' }, el('table', { 'data-test': 'assets-table' },
        el('thead', null, el('tr', null, ['Назва', 'Вид', 'Рамка (px)', 'Роль', 'Прозорий'].map(function (h) { return el('th', { scope: 'col', text: h }); }))),
        el('tbody', null, assetNames.map(function (a) {
          var sp = isObj(m.assets[a]) ? m.assets[a] : {};
          return el('tr', null, el('td', { class: 'mono', text: a }), el('td', { text: strOr(sp.kind, '') }),
            el('td', { text: Array.isArray(sp.frame) ? sp.frame.join(' × ') : '' }), el('td', { text: strOr(sp.role, '') }), el('td', { text: sp.transparent ? 'так' : 'ні' }));
        })))));
    }
  }

  function saveRoles(btn) {
    var changes = {};
    var inputs = qs('slots-table').querySelectorAll('input[data-locator]');
    Array.prototype.forEach.call(inputs, function (i) {
      if (i.value !== i.getAttribute('data-orig')) changes[i.getAttribute('data-locator')] = i.value;
    });
    if (!Object.keys(changes).length) { setMsg('msg-skeleton', 'Змін немає.', 'warn'); return; }
    busy(btn, 'Зберігаю…', function () { return api('PUT', '/api/skeletons/' + enc(S.route.name) + '/roles', changes); })
      .then(function (r) {
        if (!r) return;
        S.dirty = false;
        return api('GET', '/api/skeletons/' + enc(S.route.name)).then(function (d) { S.skel = d; renderSkeleton(false); setMsg('msg-skeleton', 'Ролі збережено.', 'ok'); });
      })
      .catch(function (e) { setMsg('msg-skeleton', errorText(e), 'err'); });
  }

  /* ------------------------------------------------------------------ TEMPLATE screen: loading */
  function loadTemplateScreen() {
    showScreen('template');
    qs('tpl-title').textContent = 'Шаблон ' + S.route.name;
    clear(qs('tpl-meta'));
    clear(qs('tpl-alerts'));
    clear(qs('step-list'));
    STEPS.forEach(function (s) { qs('screen-' + s).hidden = true; });
    refreshTemplate(false);
  }

  function refreshTemplate(respectDirty) {
    var name = S.route.name;
    return api('GET', '/api/templates/' + enc(name)).then(function (d) {
      if (S.route.view !== 'template' || S.route.name !== name) return;
      S.tpl = d; S.tplError = null;
      S.genSig = genSig(d.generation);
      if (!S.route.step) {  // keep the step the owner is on, even after it gets approved
        S.route.step = activeStep();
        try { history.replaceState(null, '', '#/t/' + enc(name) + '/' + S.route.step); } catch (e) { /* ignore */ }
      }
      hideBanner();
      renderTemplate(respectDirty);
    }, function (e) {
      if (S.route.view !== 'template' || S.route.name !== name) return;
      if (e instanceof ApiError && e.status === 404) { missing('Шаблон «' + name + '» не знайдено.'); return; }
      if (e instanceof ApiError && e.status === 409) { S.tpl = null; S.tplError = e.message; renderTemplate(false); return; }
      showBanner(errorText(e));
    });
  }

  function activeStep() {
    if (S.route.step) return S.route.step;
    var steps = S.tpl.state.steps;
    for (var i = 0; i < STEPS.length; i++) if (steps[STEPS[i]].status !== 'approved') return STEPS[i];
    return 'verify';
  }

  function renderTemplate(respectDirty) {
    qs('tpl-title').textContent = 'Шаблон ' + S.route.name;
    var alerts = clear(qs('tpl-alerts'));
    if (!S.tpl) {
      clear(qs('step-list'));
      clear(qs('tpl-jobs'));
      STEPS.forEach(function (s) { qs('screen-' + s).hidden = true; });
      qs('tpl-meta').textContent = '';
      alerts.appendChild(el('div', { class: 'msg msg-err', role: 'alert', 'data-test': 'template-broken' },
        el('span', { text: 'Шаблон не відкривається: ' + String(S.tplError) + '. Файл state.json треба відновити вручну; студія нічого не змінює сама.' })));
      return;
    }
    var t = S.tpl;
    qs('tpl-meta').textContent = 'Скелет: ' + strOr(t.skeleton, '—');
    var skelLink = el('a', { href: '#/s/' + enc(strOr(t.skeleton, '')), text: ' відкрити карту скелета' });
    qs('tpl-meta').appendChild(document.createTextNode(' · '));
    qs('tpl-meta').appendChild(skelLink);
    renderAlerts(alerts);
    renderStepBar();
    var jr = clear(qs('tpl-jobs'));
    jr.appendChild(jobsTable((t.jobs || []).map(normTplJob).reverse(), false));

    var step = activeStep();
    STEPS.forEach(function (s) { qs('screen-' + s).hidden = (s !== step); });
    if (respectDirty && S.dirty && S.renderedStep === step) {
      qs('stale-notice').hidden = false;
      return;
    }
    qs('stale-notice').hidden = true;
    S.dirty = false;
    S.renderedStep = step;
    S.renderToken += 1;
    ({ style: renderStyle, images: renderImages, texts: renderTexts, apply: renderApply, verify: renderVerify })[step]();
  }

  function renderAlerts(box) {
    var t = S.tpl;
    STEPS.forEach(function (s) {
      var info = t.job_results && t.job_results[s];
      if (info && (info.status === 'failed' || info.status === 'corrupt')) {
        box.appendChild(el('div', { class: 'msg msg-err', role: 'alert', 'data-test': 'job-alert', 'data-step': s },
          el('span', null, el('strong', { text: 'Крок «' + STEP_TITLES[s] + '»: ' + (RESULT_LABELS[info.status] || info.status) + '. ' }),
            info.copy_missing ? 'Claude не записав id копії — перевірте /studio. ' : '', strOr(info.summary, ''))));
      }
    });
    if (Array.isArray(t.problems) && t.problems.length) {
      box.appendChild(el('div', { class: 'msg msg-warn', 'data-test': 'tpl-problems' },
        el('div', null, el('strong', { text: 'Проблеми з даними шаблону:' }), el('ul', null, t.problems.map(function (p) { return el('li', { text: String(p) }); })))));
    }
  }

  function renderStepBar() {
    var list = clear(qs('step-list'));
    var cur = activeStep();
    STEPS.forEach(function (s, i) {
      var st = S.tpl.state.steps[s].status;
      var a = el('a', { class: 'step-link', id: 'step-' + s, 'data-test': 'step-' + s, 'data-status': st, href: '#/t/' + enc(S.route.name) + '/' + s, 'aria-current': s === cur ? 'step' : null },
        el('span', { class: 'step-name' }, el('span', { class: 'step-num', text: (i + 1) + '.' }), STEP_TITLES[s]),
        statusBadge(st));
      list.appendChild(el('li', null, a));
    });
  }

  /* ------------------------------------------------------------------ panel header: status, approve, reopen */
  function approveInfo(step) {
    var st = S.tpl.state.steps[step].status;
    if (!S.tpl.can_start[step]) return { ok: false, why: 'Спершу затвердіть попередні кроки.' };
    if (st === 'review' || (st === 'stale' && STALE_STEP_APPROVABLE.indexOf(step) !== -1)) return { ok: true };
    if (st === 'approved') return { ok: false, why: '' };
    if (st === 'waiting_claude') return { ok: false, why: 'Чекаємо на Claude: у його сесії виконайте /studio.' };
    if (st === 'stale') return { ok: false, why: 'Крок застарів: виконайте його знову.' };
    return { ok: false, why: 'Крок ще не готовий до перегляду.' };
  }

  function panelHead(step, title, intro) {
    var st = S.tpl.state.steps[step].status;
    var ap = approveInfo(step);
    var approve = el('button', { type: 'button', class: 'btn btn-primary', id: 'approve-' + step, 'data-test': 'approve-' + step, text: 'Затвердити крок', disabled: !ap.ok });
    approve.addEventListener('click', function () {
      if (S.dirty) { setMsg('msg-' + step, 'Є незбережені зміни: спершу збережіть їх, інакше затвердиться стара версія.', 'warn'); return; }
      busy(approve, 'Затверджую…', function () { return api('POST', '/api/templates/' + enc(S.route.name) + '/approve', { step: step }); })
        .then(function (r) { if (!r) return; return refreshTemplate(false).then(function () { setMsg('msg-' + step, 'Крок «' + STEP_TITLES[step] + '» затверджено.', 'ok'); }); })
        .catch(function (e) { setMsg('msg-' + step, approveErrorLines(step, e), 'err'); });
    });
    var tools = [approve];
    if (st === 'approved') {
      var reopen = el('button', { type: 'button', class: 'btn', id: 'reopen-' + step, 'data-test': 'reopen-' + step, text: 'Відкрити знову' });
      reopen.addEventListener('click', function () {
        busy(reopen, 'Відкриваю…', function () { return api('POST', '/api/templates/' + enc(S.route.name) + '/reopen', { step: step }); })
          .then(function (r) { if (!r) return; return refreshTemplate(false).then(function () { setMsg('msg-' + step, 'Крок відкрито знову; наступні кроки стали застарілими.', 'warn'); }); })
          .catch(function (e) { setMsg('msg-' + step, errorText(e), 'err'); });
      });
      tools.push(reopen);
    }
    var head = el('div', { class: 'panel-head' },
      el('h2', { id: 'h-' + step, text: (STEPS.indexOf(step) + 1) + '. ' + title }),
      el('div', { class: 'panel-tools' }, statusBadge(st), tools));
    var kids = [head];
    var why = st === 'approved' ? 'Крок затверджено. «Відкрити знову» зробить усі наступні кроки застарілими.' : (!ap.ok ? ap.why : '');
    if (why) kids.push(el('p', { class: 'hint', 'data-test': 'step-hint', text: why }));
    if (intro) kids.push(el('p', { class: 'lead', text: intro }));
    kids.push(el('div', { id: 'msg-' + step, class: 'msg', 'data-test': 'msg-' + step, role: 'status', hidden: true }));
    return kids;
  }

  function approveErrorLines(step, e) {
    var t = errorText(e);
    var lines = [t];
    if (step === 'images' && /\(g\) cover \+ seal|печат/i.test(t)) lines.push(SEAL_HINT);
    return lines;
  }

  function requestInfo(step, extra) {
    var st = S.tpl.state.steps[step].status;
    if (!S.tpl.can_start[step]) return { ok: false, why: 'Спершу затвердіть попередні кроки.' };
    if (st === 'waiting_claude') return { ok: false, why: 'Завдання вже в черзі: у сесії Claude Code виконайте /studio.' };
    if (st === 'approved') return { ok: false, why: 'Крок затверджено. Щоб повторити, спершу відкрийте його знову.' };
    if (extra) return extra;
    return { ok: true };
  }

  function requestButton(step, id, label, path, busyLabel, extraInfo, afterText) {
    var info = requestInfo(step, extraInfo);
    var btn = el('button', { type: 'button', class: 'btn btn-primary', id: id, 'data-test': id, text: label, disabled: !info.ok });
    btn.addEventListener('click', function () {
      busy(btn, busyLabel, function () { return api('POST', '/api/templates/' + enc(S.route.name) + path, {}); })
        .then(function (r) { if (!r) return; return refreshTemplate(false).then(function () { setMsg('msg-' + step, afterText, 'ok'); }); })
        .catch(function (e) { setMsg('msg-' + step, errorText(e), 'err'); });
    });
    return { btn: btn, info: info };
  }

  /* ------------------------------------------------------------------ STYLE panel */
  function mapSlots(type) {
    var m = S.tpl && S.tpl.map;
    return isObj(m) && Array.isArray(m.slots) ? m.slots.filter(function (s) { return isObj(s) && (type.indexOf(s.type) !== -1) && typeof s.locator === 'string'; }) : [];
  }
  function mapAssets() { var m = S.tpl && S.tpl.map; return isObj(m) && isObj(m.assets) ? m.assets : {}; }

  function renderStyle() {
    var t = S.tpl, root = clear(qs('screen-style')), token = S.renderToken;
    panelHead('style', 'Стиль', 'Claude пропонує напрями за вашим брифом. Оберіть один і за потреби поправте палітру та підказки для картинок.').forEach(function (n) { root.appendChild(n); });
    root.appendChild(el('h3', { text: 'Бриф' }));
    root.appendChild(el('p', { id: 'brief-text', 'data-test': 'brief-text', style: 'white-space: pre-wrap', text: t.brief ? t.brief : 'Брифу немає.' }));

    var jb = jobBlock(t.job_results && t.job_results.style, S.tpl.state.steps.style.status === 'waiting_claude' ? 'Напрями ще не готові. У сесії Claude Code виконайте /studio: Claude складе 2–3 напрями за брифом.' : null);
    if (jb) root.appendChild(jb);

    root.appendChild(el('h3', { text: 'Напрями від Claude' }));
    var dirBox = el('div', { id: 'directions', 'data-test': 'directions' }, el('p', { class: 'muted', text: 'Завантажую…' }));
    root.appendChild(dirBox);
    var info = t.job_results && t.job_results.style;
    if (info && info.status === 'done') {
      getResult(info).then(function (res) {
        if (token !== S.renderToken) return;
        renderDirections(dirBox, res);
      });
    } else {
      clear(dirBox).appendChild(el('p', { class: 'muted', text: 'Готових напрямів ще немає.' }));
    }

    root.appendChild(el('h3', { text: 'Поточний стиль' }));
    var editorBox = el('div', { id: 'style-editor', 'data-test': 'style-editor' });
    root.appendChild(editorBox);
    renderStyleEditor(editorBox, S.styleDraft || t.style);
  }

  function parseDirection(d) {
    if (!isObj(d)) return null;
    var out = { name: strOr(d.name, 'Без назви'), description: strOr(d.description, ''), style: {} };
    ['palette', 'colour_roles', 'image_prompts', 'fonts', 'font_map'].forEach(function (k) { if (isObj(d[k])) out.style[k] = d[k]; });
    out.style.name = out.name;
    return out;
  }

  function renderDirections(box, res) {
    clear(box);
    var list = res && isObj(res.outputs) && Array.isArray(res.outputs.directions) ? res.outputs.directions.map(parseDirection).filter(Boolean) : [];
    if (!list.length) { box.appendChild(el('p', { class: 'muted', text: 'У результаті завдання немає напрямів (очікується outputs.directions).' })); return; }
    var current = S.tpl.style && S.tpl.style.name;
    var wrap = el('div', { class: 'directions' });
    list.forEach(function (d, i) {
      var pal = isObj(d.style.palette) ? d.style.palette : {};
      var sw = el('div', { class: 'swatches' }, Object.keys(pal).map(function (r) {
        var c = strOr(pal[r], '');
        var chip = el('i');
        if (/^#[0-9a-fA-F]{6}$/.test(c)) chip.style.backgroundColor = c;
        return el('span', { class: 'swatch', title: r }, chip, r + ' ' + c);
      }));
      var fonts = isObj(d.style.fonts) ? FONT_ROLES.map(function (f) { return f + ': ' + strOr(d.style.fonts[f], '—'); }).join(' · ') : '';
      var prompts = isObj(d.style.image_prompts) ? d.style.image_prompts : {};
      var pbox = el('details', null, el('summary', { text: 'Підказки для картинок' }),
        Object.keys(prompts).map(function (a) { return el('p', null, el('strong', { text: a + ': ' }), strOr(prompts[a], '')); }));
      var btn = el('button', { type: 'button', class: 'btn btn-primary', id: 'choose-direction-' + i, 'data-test': 'choose-direction-' + i, text: 'Обрати цей напрям' });
      btn.addEventListener('click', function () { chooseDirection(btn, d); });
      wrap.appendChild(el('article', { class: 'direction' + (current && current === d.name ? ' is-chosen' : ''), 'data-test': 'direction', 'data-index': String(i) },
        el('h4', { text: d.name }), el('p', { text: d.description }), sw, fonts ? el('p', { class: 'hint', text: fonts }) : null, pbox, btn,
        current && current === d.name ? el('p', { class: 'hint', text: 'Зараз обрано' }) : null));
    });
    box.appendChild(wrap);
  }

  function chooseDirection(btn, d) {
    var style = JSON.parse(JSON.stringify(d.style));
    if (S.tpl.brief) style.brief = S.tpl.brief;
    S.styleDraft = style;
    var box = qs('style-editor');
    renderStyleEditor(box, style);
    S.dirty = true;
    busy(btn, 'Зберігаю…', function () { return api('PUT', '/api/templates/' + enc(S.route.name) + '/style', style); })
      .then(function (r) {
        if (!r) return;
        S.styleDraft = null; S.dirty = false;
        return refreshTemplate(false).then(function () { setMsg('msg-style', 'Напрям «' + d.name + '» обрано і збережено. За потреби поправте його нижче й натисніть «Зберегти стиль».', 'ok'); });
      })
      .catch(function (e) { setMsg('msg-style', ['Напрям завантажено в редактор, але не збережено: ' + errorText(e), 'Виправте поля нижче й натисніть «Зберегти стиль».'], 'err'); });
  }

  function renderStyleEditor(box, style) {
    clear(box);
    var t = S.tpl;
    if (!isObj(t.map)) { box.appendChild(el('p', { class: 'msg msg-warn', text: 'Карти скелета ще немає (або вона недійсна), тому стиль редагувати не можна.' })); return; }
    var base = isObj(style) ? style : {};
    if (!isObj(style)) box.appendChild(el('p', { class: 'hint', 'data-test': 'no-style', text: 'Стилю ще не збережено. Оберіть напрям вище або заповніть поля вручну.' }));
    var form = el('form', { id: 'style-form', 'data-test': 'style-form', autocomplete: 'off' });
    form.addEventListener('submit', function (e) { e.preventDefault(); });
    form.addEventListener('input', function () { S.dirty = true; });
    box.appendChild(form);

    form.appendChild(el('label', { for: 'style-name', text: 'Назва стилю' }));
    form.appendChild(el('input', { type: 'text', id: 'style-name', value: strOr(base.name, '') }));

    form.appendChild(el('h3', { text: 'Палітра' }));
    var palBox = el('div', { id: 'palette-rows', 'data-test': 'palette-rows' });
    var pal = isObj(base.palette) ? base.palette : {};
    Object.keys(pal).forEach(function (r) { palBox.appendChild(paletteRow(r, strOr(pal[r], ''))); });
    form.appendChild(palBox);
    var newRole = el('input', { type: 'text', id: 'new-palette-role', 'aria-label': 'Назва нового кольору (роль)', placeholder: 'нова роль, напр. accent2', maxlength: '40' });
    var addBtn = el('button', { type: 'button', class: 'btn btn-small', id: 'add-palette', text: 'Додати колір' });
    addBtn.addEventListener('click', function () {
      var r = newRole.value.trim();
      if (!r) return;
      var exists = Array.prototype.some.call(palBox.querySelectorAll('[data-role]'), function (n) { return n.getAttribute('data-role') === r; });
      if (exists) { setMsg('msg-style', 'Колір «' + r + '» уже є в палітрі.', 'warn'); return; }
      palBox.appendChild(paletteRow(r, '#888888'));
      newRole.value = '';
      refreshRoleSelects();
      S.dirty = true;
    });
    form.appendChild(el('div', { class: 'row' }, el('div', { class: 'grow' }, newRole), addBtn));

    form.appendChild(el('h3', { text: 'Які кольори де використовуються' }));
    var roles = {};
    Object.keys(isObj(base.colour_roles) ? base.colour_roles : {}).forEach(function (r) { roles[r] = true; });
    mapSlots(['colour']).forEach(function (s) { if (typeof s.role === 'string') roles[s.role] = true; });
    var crGrid = el('div', { class: 'pair-grid', id: 'colour-roles', 'data-test': 'colour-roles' });
    Object.keys(roles).forEach(function (r, i) {
      var sel = el('select', { id: 'colour-role-' + i, 'data-kind': 'colour-role', 'data-role': r, 'data-value': strOr((base.colour_roles || {})[r], '') });
      crGrid.appendChild(el('div', null, el('label', { for: 'colour-role-' + i, text: 'Колір для ролі «' + r + '»' }), sel));
    });
    form.appendChild(crGrid);
    if (!Object.keys(roles).length) crGrid.appendChild(el('p', { class: 'muted', text: 'У карті немає слотів-кольорів.' }));

    form.appendChild(el('h3', { text: 'Підказки для картинок' }));
    var prompts = isObj(base.image_prompts) ? base.image_prompts : {};
    var assets = mapAssets();
    Object.keys(assets).forEach(function (a, i) {
      var sp = isObj(assets[a]) ? assets[a] : {};
      form.appendChild(el('label', { for: 'prompt-' + i, text: 'Картинка «' + a + '» (' + strOr(sp.kind, '?') + ', ' + (Array.isArray(sp.frame) ? sp.frame.join('×') : '?') + ')' }));
      form.appendChild(el('textarea', { id: 'prompt-' + i, rows: '3', 'data-asset': a, text: strOr(prompts[a], '') }));
    });
    if (!Object.keys(assets).length) form.appendChild(el('p', { class: 'muted', text: 'У карті немає картинок.' }));

    form.appendChild(el('h3', { text: 'Шрифти' }));
    var fonts = isObj(base.fonts) ? base.fonts : {};
    var fg = el('div', { class: 'pair-grid' });
    FONT_ROLES.forEach(function (f) {
      fg.appendChild(el('div', null, el('label', { for: 'font-' + f, text: 'Шрифт: ' + f }), el('input', { type: 'text', id: 'font-' + f, 'data-font': f, value: strOr(fonts[f], '') })));
    });
    form.appendChild(fg);

    form.appendChild(el('h3', { text: 'Який шрифт для якого тексту' }));
    var fmRoles = {};
    Object.keys(isObj(base.font_map) ? base.font_map : {}).forEach(function (r) { fmRoles[r] = true; });
    mapSlots(['text', 'table_cell']).forEach(function (s) { if (typeof s.role === 'string') fmRoles[s.role] = true; });
    var fm = el('div', { class: 'pair-grid', id: 'font-map', 'data-test': 'font-map' });
    Object.keys(fmRoles).forEach(function (r, i) {
      var cur = strOr((base.font_map || {})[r], '');
      var sel = el('select', { id: 'fontmap-' + i, 'data-fontmap': r }, el('option', { value: '', text: '— не задано —' }),
        FONT_ROLES.map(function (f) { return el('option', { value: f, text: f, selected: f === cur }); }));
      fm.appendChild(el('div', null, el('label', { for: 'fontmap-' + i, text: 'Текст з роллю «' + r + '»' }), sel));
    });
    form.appendChild(fm);

    var save = el('button', { type: 'button', class: 'btn btn-primary', id: 'save-style', 'data-test': 'save-style', text: 'Зберегти стиль' });
    save.addEventListener('click', function () { saveStyle(save, base); });
    form.appendChild(el('div', { class: 'actions' }, save));
    form.appendChild(el('p', { class: 'hint', text: 'Якщо крок вже затверджено, збереження відкриє його знову, а наступні кроки стануть застарілими.' }));
    refreshRoleSelects();
  }

  function paletteRow(role, hex) {
    var valid = /^#[0-9a-fA-F]{6}$/.test(hex);
    var text = el('input', { type: 'text', value: hex, maxlength: '7', 'aria-label': 'Колір ' + role + ' у форматі #rrggbb', 'data-palette-hex': role });
    var color = el('input', { type: 'color', value: valid ? hex.toLowerCase() : '#888888', 'aria-label': 'Вибір кольору ' + role });
    color.addEventListener('input', function () { text.value = color.value; });
    text.addEventListener('input', function () { if (/^#[0-9a-fA-F]{6}$/.test(text.value)) color.value = text.value.toLowerCase(); });
    return el('div', { class: 'pal-row', 'data-role': role }, el('span', { class: 'pal-role', text: role }), color, text);
  }

  function refreshRoleSelects() {
    var form = qs('style-form');
    if (!form) return;
    var palRoles = Array.prototype.map.call(form.querySelectorAll('#palette-rows [data-role]'), function (n) { return n.getAttribute('data-role'); });
    Array.prototype.forEach.call(form.querySelectorAll('select[data-kind="colour-role"]'), function (sel) {
      var want = sel.value || sel.getAttribute('data-value') || '';
      clear(sel);
      sel.appendChild(el('option', { value: '', text: '— оберіть колір —' }));
      palRoles.forEach(function (r) { sel.appendChild(el('option', { value: r, text: r })); });
      sel.value = palRoles.indexOf(want) !== -1 ? want : '';
    });
  }

  function collectStyle(base) {
    var out = JSON.parse(JSON.stringify(base || {}));
    var form = qs('style-form');
    out.name = qs('style-name').value;
    out.palette = {};
    Array.prototype.forEach.call(form.querySelectorAll('input[data-palette-hex]'), function (i) { out.palette[i.getAttribute('data-palette-hex')] = i.value; });
    out.colour_roles = {};
    Array.prototype.forEach.call(form.querySelectorAll('select[data-kind="colour-role"]'), function (s) { if (s.value) out.colour_roles[s.getAttribute('data-role')] = s.value; });
    out.image_prompts = {};
    Array.prototype.forEach.call(form.querySelectorAll('textarea[data-asset]'), function (t) { out.image_prompts[t.getAttribute('data-asset')] = t.value; });
    out.fonts = {};
    Array.prototype.forEach.call(form.querySelectorAll('input[data-font]'), function (i) { out.fonts[i.getAttribute('data-font')] = i.value; });
    out.font_map = {};
    Array.prototype.forEach.call(form.querySelectorAll('select[data-fontmap]'), function (s) { if (s.value) out.font_map[s.getAttribute('data-fontmap')] = s.value; });
    if (out.brief === undefined && S.tpl.brief) out.brief = S.tpl.brief;
    return out;
  }

  function saveStyle(btn, base) {
    var body = collectStyle(base);
    busy(btn, 'Зберігаю…', function () { return api('PUT', '/api/templates/' + enc(S.route.name) + '/style', body); })
      .then(function (r) {
        if (!r) return;
        S.styleDraft = null; S.dirty = false;
        return refreshTemplate(false).then(function () { setMsg('msg-style', 'Стиль збережено.', 'ok'); });
      })
      .catch(function (e) { setMsg('msg-style', errorText(e), 'err'); });
  }

  /* ------------------------------------------------------------------ IMAGES panel */
  function renderImages() {
    var t = S.tpl, root = clear(qs('screen-images'));
    panelHead('images', 'Картинки', 'Студія сама генерує картинки в ComfyUI під рамки скелета. Для кожної оберіть версію, яка вам подобається, або згенеруйте ще раз.').forEach(function (n) { root.appendChild(n); });

    var h = S.health;
    if (h && !h.models_mounted) {
      root.appendChild(el('div', { class: 'msg msg-err', id: 'disk-warning', 'data-test': 'disk-warning', role: 'alert' }, el('span', { text: 'Диск моделей не змонтовано — генерація недоступна. Підключіть диск і оновіть сторінку.' })));
    }
    var pend = (t.generation && t.generation.pending) || [];
    var q = { queued: 0, running: 0 };
    pend.forEach(function (p) { if (p.state === 'queued') q.queued += 1; else if (p.state === 'running') q.running += 1; });
    var qlines = [el('div', null, el('strong', { text: 'Черга генерації: ' }), pend.length ? ('виконується ' + q.running + ', у черзі ' + q.queued + ', усього очікує ' + pend.length) : 'порожня')];
    qlines.push(el('div', { class: 'hint', text: 'ComfyUI: ' + (h ? strOr(h.comfy_url, '?') : '?') + '. Чи він запущений, студія дізнається лише при спробі генерації: якщо ні, нижче з’явиться повідомлення.' }));
    root.appendChild(el('div', { class: 'msg', id: 'queue-status', 'data-test': 'queue-status' }, el('div', null, qlines)));

    var gen = el('button', { type: 'button', class: 'btn btn-primary', id: 'generate-all', 'data-test': 'generate-all', text: 'Згенерувати всі картинки' });
    var gi = requestInfoGen();
    gen.disabled = !gi.ok;
    gen.addEventListener('click', function () { generate(gen, {}, 'Генерацію запущено для всіх картинок.'); });
    var sheetUrl = '/files/templates/' + enc(S.route.name) + '/assets/contact_sheet.jpg?t=' + Date.now();
    var sheetLink = el('a', { id: 'contact-sheet-link', 'data-test': 'contact-sheet-link', href: sheetUrl, target: '_blank', rel: 'noopener noreferrer', text: 'Аркуш-огляд усіх картинок (відкрити)' });
    root.appendChild(el('div', { class: 'actions' }, gen, sheetLink));
    if (!gi.ok && gi.why) root.appendChild(el('p', { class: 'hint', text: gi.why }));
    var sheetBox = el('div', { id: 'contact-sheet-box' });
    var sheetImg = el('img', { class: 'sheet-preview', alt: 'Аркуш-огляд усіх картинок', hidden: true });
    sheetImg.addEventListener('load', function () { sheetImg.hidden = false; sheetNote.hidden = true; });
    var sheetNote = el('p', { class: 'hint', id: 'contact-sheet-note', text: 'Аркуш-огляд з’явиться, коли ви затвердите крок «Картинки».' });
    sheetImg.setAttribute('src', sheetUrl);
    sheetBox.appendChild(sheetImg);
    sheetBox.appendChild(sheetNote);
    root.appendChild(sheetBox);

    var galleryNote = !isObj(t.map) ? el('div', { class: 'msg msg-warn', text: 'Карти скелета ще немає, тому картинок для показу немає.' }) : null;
    if (galleryNote) root.appendChild(galleryNote);
    var gal = el('div', { class: 'gallery', id: 'gallery', 'data-test': 'gallery' });
    (t.assets || []).forEach(function (a) { gal.appendChild(assetCard(a)); });
    root.appendChild(gal);
  }

  function requestInfoGen() {
    var st = S.tpl.state.steps.images.status;
    if (!S.tpl.can_start.images) return { ok: false, why: 'Спершу затвердіть крок «Стиль».' };
    if (!isObj(S.tpl.style)) return { ok: false, why: 'Спершу збережіть стиль.' };
    if (S.health && !S.health.models_mounted) return { ok: false, why: 'Диск моделей не змонтовано.' };
    if (st === 'approved') return { ok: false, why: 'Крок затверджено. Щоб згенерувати ще раз, спершу відкрийте його знову.' };
    return { ok: true };
  }

  function generate(btn, body, okText) {
    busy(btn, 'Перевіряю ComfyUI…', function () { return api('POST', '/api/templates/' + enc(S.route.name) + '/images/generate', body); })
      .then(function (r) {
        if (!r) return;
        return refreshTemplate(false).then(function () { setMsg('msg-images', okText, 'ok'); });
      })
      .catch(function (e) { setMsg('msg-images', errorText(e), 'err'); });
  }

  function assetCard(a) {
    var key = idSafe(a.asset);
    var pend = (a.generation && a.generation.pending) || [];
    var last = a.generation && a.generation.last;
    var versions = Array.isArray(a.versions) ? a.versions : [];
    var card = el('article', { class: 'asset-card', 'data-test': 'asset-card', 'data-asset': a.asset });
    card.appendChild(el('h3', { text: a.asset }));
    card.appendChild(el('div', { class: 'hint', text: [strOr(a.kind, ''), Array.isArray(a.frame) ? a.frame.join(' × ') + ' px' : '', strOr(a.role, ''), a.transparent ? 'прозорий' : ''].filter(Boolean).join(' · ') }));
    if (pend.length) {
      card.appendChild(el('div', { class: 'msg', 'data-test': 'asset-pending' }, el('span', { text: 'Генерується: ' + pend.map(function (p) { return GEN_STATE_LABELS[p.state] || p.state; }).join(', ') })));
    }
    if (last && (last.status === 'failed' || last.status === 'lost')) {
      var probs = Array.isArray(last.problems) ? last.problems : [];
      card.appendChild(el('div', { class: 'msg msg-err', role: 'alert', 'data-test': 'asset-failed' },
        el('div', null, el('strong', { text: last.status === 'lost' ? 'Генерацію втрачено. ' : 'Остання генерація не вдалася. ' }), probs.map(function (p) { return el('div', { text: String(p) }); }))));
    }
    var vbox = el('div', { class: 'versions', 'data-test': 'versions' });
    versions.forEach(function (v) {
      var chosen = a.chosen === v.file;
      var img = el('img', { alt: a.asset + ', версія ' + v.n, loading: 'lazy' });
      img.setAttribute('src', String(v.url));
      var btn = el('button', { type: 'button', class: 'btn btn-small', id: 'choose-' + key + '-' + v.n, 'data-test': 'choose-' + key + '-' + v.n, text: chosen ? 'Обрано' : 'Прийняти', disabled: chosen });
      btn.setAttribute('aria-label', (chosen ? 'Обрано: ' : 'Прийняти: ') + a.asset + ' версія ' + v.n);
      btn.addEventListener('click', function () {
        busy(btn, '…', function () { return api('POST', '/api/templates/' + enc(S.route.name) + '/images/choose', { asset: a.asset, file: v.file }); })
          .then(function (r) { if (!r) return; return refreshTemplate(false).then(function () { setMsg('msg-images', 'Обрано «' + a.asset + '», версія ' + v.n + '.', 'ok'); }); })
          .catch(function (e) { setMsg('msg-images', errorText(e), 'err'); });
      });
      vbox.appendChild(el('figure', { class: 'version' + (chosen ? ' is-chosen' : ''), 'data-version': String(v.n), 'data-chosen': chosen ? 'true' : 'false', style: 'margin:0' },
        el('div', { class: 'thumb-box' }, img), el('figcaption', { text: 'v' + v.n + (chosen ? ' · обрано' : '') }), btn));
    });
    if (!versions.length) vbox.appendChild(el('p', { class: 'muted', text: 'Версій ще немає.' }));
    card.appendChild(vbox);

    card.appendChild(el('p', { class: 'hint', text: 'Підказка зі стилю: ' + (a.prompt ? a.prompt : 'немає') }));
    var pid = 'own-prompt-' + key;
    card.appendChild(el('label', { for: pid, text: 'Своя підказка (необов’язково)' }));
    var ta = el('textarea', { id: pid, rows: '2', 'data-asset': a.asset, 'data-test': pid, placeholder: 'Залиште порожнім, щоб узяти підказку зі стилю' });
    ta.value = S.promptDraft[a.asset] || '';
    ta.addEventListener('input', function () { S.promptDraft[a.asset] = ta.value; });
    card.appendChild(ta);
    var again = el('button', { type: 'button', class: 'btn', id: 'regen-' + key, 'data-test': 'regen-' + key, text: 'Ще раз' });
    var gi = requestInfoGen();
    again.disabled = !gi.ok || pend.length > 0;
    again.addEventListener('click', function () {
      var body = { assets: [a.asset] };
      if (ta.value.trim()) body.prompt_override = ta.value;
      generate(again, body, 'Генерацію «' + a.asset + '» запущено: нова версія з’явиться тут, старі лишаються.');
    });
    card.appendChild(el('div', { class: 'actions' }, again));
    if (a.kind === 'composed') card.appendChild(el('p', { class: 'hint', text: 'Конверт збирається з печаткою. ' + SEAL_HINT }));
    return card;
  }

  /* ------------------------------------------------------------------ TEXTS panel */
  function lengthWarning(slot, v) {
    if (typeof v !== 'string' || v === '') return '';
    var n = cpLen(v);
    var mx = slot.max_len, orig = slot.original;
    if (typeof mx === 'number' && v.indexOf('\n') === -1 && n > mx) return 'Задовгий рядок: ' + n + ' символів, дозволено до ' + mx + '.';
    if (typeof orig === 'string' && orig && n * 100 > 115 * cpLen(orig)) {
      return 'Абзац задовгий: ' + n + ' символів, в оригіналі ' + cpLen(orig) + ' (дозволено до 115 %, тобто ' + Math.floor(115 * cpLen(orig) / 100) + ').';
    }
    return '';
  }

  function renderTexts() {
    var t = S.tpl, root = clear(qs('screen-texts'));
    panelHead('texts', 'Тексти', 'Claude пише тексти під ваш стиль, а ви правите кожен. Персональні дані (імена, дати) бувають лише в полях з позначкою.').forEach(function (n) { root.appendChild(n); });

    var rb = requestButton('texts', 'request-texts', 'Попросити Claude написати тексти', '/texts/request', 'Створюю завдання…', null, 'Завдання створено. У сесії Claude Code виконайте /studio.');
    var tools = [rb.btn];
    root.appendChild(el('div', { class: 'actions' }, tools));
    if (!rb.info.ok && rb.info.why) root.appendChild(el('p', { class: 'hint', text: rb.info.why }));
    var jb = jobBlock(t.job_results && t.job_results.texts, null);
    if (jb) root.appendChild(jb);

    var slots = mapSlots(['text', 'table_cell']);
    if (!isObj(t.map)) { root.appendChild(el('div', { class: 'msg msg-warn', text: 'Карти скелета ще немає, тому редагувати тексти нема в чому.' })); return; }
    var texts = isObj(t.texts) ? t.texts : {};
    if (!isObj(t.texts)) root.appendChild(el('p', { class: 'hint', 'data-test': 'no-texts', text: 'Збережених текстів ще немає. Попросіть Claude або впишіть їх самі.' }));
    var form = el('form', { id: 'texts-form', 'data-test': 'texts-form', autocomplete: 'off' });
    form.addEventListener('submit', function (e) { e.preventDefault(); });
    form.addEventListener('input', function () { S.dirty = true; });
    var summary = el('div', { id: 'texts-warnings', 'data-test': 'texts-warnings', class: 'msg msg-warn', role: 'status', hidden: true });
    form.appendChild(summary);

    function updateSummary() {
      var n = form.querySelectorAll('.warn:not([hidden])').length;
      if (n) { clear(summary).appendChild(el('span', { text: 'Попередження про довжину: ' + n + '. Текст усе одно можна зберегти.' })); summary.hidden = false; }
      else summary.hidden = true;
    }

    slots.forEach(function (s, i) {
      var tid = 'text-' + i;
      var ta = el('textarea', { id: tid, rows: s.type === 'table_cell' ? '1' : '3', 'data-locator': s.locator, 'data-test': tid });
      ta.value = typeof texts[s.locator] === 'string' ? texts[s.locator] : '';
      var counter = el('span', { class: 'counter' });
      var warn = el('p', { class: 'warn', 'data-test': 'text-warning', role: 'status', hidden: true });
      function refresh() {
        var n = cpLen(ta.value);
        counter.textContent = n + (typeof s.max_len === 'number' ? ' / ' + s.max_len : '') + ' символів';
        var w = lengthWarning(s, ta.value);
        warn.textContent = w;
        warn.hidden = !w;
        updateSummary();
      }
      ta.addEventListener('input', refresh);
      var kids = [el('label', { for: tid }, strOr(s.role, 'текст') + ' · ', el('span', { class: 'mono', text: s.locator }), s.personal ? ' ' : null, s.personal ? badge('персональне поле', 'b-review') : null)];
      if (typeof s.original === 'string' && s.original) kids.push(el('div', { class: 'hint', text: 'Оригінал скелета: ' + s.original }));
      kids.push(ta, el('div', null, counter), warn);
      form.appendChild(el('div', { class: 'text-row', 'data-test': 'text-row', 'data-locator': s.locator }, kids));
      refresh();
    });
    if (!slots.length) form.appendChild(el('p', { class: 'muted', text: 'У карті немає текстових слотів.' }));
    root.appendChild(form);

    var save = el('button', { type: 'button', class: 'btn btn-primary', id: 'save-texts', 'data-test': 'save-texts', text: 'Зберегти тексти', disabled: !slots.length });
    save.addEventListener('click', function () {
      var body = {};
      Array.prototype.forEach.call(form.querySelectorAll('textarea[data-locator]'), function (x) { if (x.value !== '') body[x.getAttribute('data-locator')] = x.value; });
      busy(save, 'Зберігаю…', function () { return api('PUT', '/api/templates/' + enc(S.route.name) + '/texts', body); })
        .then(function (r) {
          if (!r) return;
          S.dirty = false;
          var n = r.length_warnings ? Object.keys(r.length_warnings).length : 0;
          return refreshTemplate(false).then(function () { setMsg('msg-texts', n ? 'Тексти збережено. Є попередження про довжину: ' + n + '.' : 'Тексти збережено.', n ? 'warn' : 'ok'); });
        })
        .catch(function (e) { setMsg('msg-texts', errorText(e), 'err'); });
    });
    root.appendChild(el('div', { class: 'actions' }, save));
    root.appendChild(el('p', { class: 'hint', text: 'Тексти зберігаються точно такими, як ви їх ввели, разом з пробілами й переносами рядків. Якщо крок вже затверджено, збереження відкриє його знову, а наступні кроки стануть застарілими.' }));
  }

  /* ------------------------------------------------------------------ APPLY panel */
  function designLink(id) {
    if (typeof id === 'string' && /^[A-Za-z0-9_-]+$/.test(id)) {
      return el('a', { id: 'canva-design-link', 'data-test': 'canva-design-link', href: 'https://www.canva.com/design/' + id + '/edit', target: '_blank', rel: 'noopener noreferrer', text: 'Відкрити копію в Canva (' + id + ')' });
    }
    return el('span', { class: 'mono', text: String(id) });
  }

  function renderApply() {
    var t = S.tpl, root = clear(qs('screen-apply'));
    panelHead('apply', 'Запис у Canva', null).forEach(function (n) { root.appendChild(n); });
    root.appendChild(el('div', { class: 'explain', 'data-test': 'apply-explain' },
      el('p', null, el('strong', { text: 'Запис у Canva виконує не ця сторінка, а Claude Code. ' }),
        'Натисніть «Записати в Canva»: студія створить завдання. Потім виконайте ', el('code', { text: '/studio' }), ' у сесії Claude Code: Claude зробить копію скелета й запише в неї кольори, тексти та картинки. Оригінал і скелет не змінюються.')));
    var hasCopy = !!(t.state && t.state.canva_copy_id);
    var rb = requestButton('apply', 'apply-canva', hasCopy ? 'Записати в Canva ще раз' : 'Записати в Canva', '/apply', 'Створюю завдання…', null, 'Завдання створено. Тепер виконайте /studio у сесії Claude Code.');
    root.appendChild(el('div', { class: 'actions' }, rb.btn));
    if (!rb.info.ok && rb.info.why) root.appendChild(el('p', { class: 'hint', text: rb.info.why }));
    var info = t.job_results && t.job_results.apply;
    var jb = jobBlock(info, S.tpl.state.steps.apply.status === 'waiting_claude' ? 'Чекаємо на Claude: у його сесії виконайте /studio.' : null);
    if (jb) root.appendChild(jb);
    var copy = t.state && t.state.canva_copy_id;
    root.appendChild(el('p', { id: 'copy-id-line', 'data-test': 'copy-id-line' }, 'Копія в Canva: ', copy ? designLink(copy) : el('span', { class: 'muted', text: 'ще не створена' })));
    root.appendChild(el('p', { class: 'hint', text: 'Двічі натискати не варто: друге завдання для Canva студія відхилить, поки перше не виконано.' }));
    if (info && info.status === 'done' && !info.copy_missing) {
      var extra = el('div', { id: 'apply-extra' });
      root.appendChild(extra);
      var token = S.renderToken;
      getResult(info).then(function (res) { if (token === S.renderToken) renderOutputsExtra(extra, res); });
    }
  }

  function renderOutputsExtra(box, res) {
    clear(box);
    var steps = res && isObj(res.outputs) && Array.isArray(res.outputs.manual_steps) ? res.outputs.manual_steps.filter(function (x) { return typeof x === 'string'; }) : [];
    if (steps.length) {
      box.appendChild(el('h3', { text: 'Ручні кроки від Claude' }));
      box.appendChild(el('ol', { 'data-test': 'claude-manual-steps' }, steps.map(function (x) { return el('li', { text: x }); })));
    }
  }

  /* ------------------------------------------------------------------ VERIFY panel */
  function fontDoneKey(locator) { return 'studio-font-done:' + S.route.name + ':' + locator; }
  function loadFlag(k) { try { return window.localStorage.getItem(k) === '1'; } catch (e) { return false; } }
  function saveFlag(k, v) { try { if (v) window.localStorage.setItem(k, '1'); else window.localStorage.removeItem(k); } catch (e) { /* ignore */ } }

  function renderVerify() {
    var t = S.tpl, root = clear(qs('screen-verify'));
    panelHead('verify', 'Перевірка', 'Claude відкриває копію в Canva, експортує сторінки, вимірює й перевіряє в повноекранному перегляді. Тут ви бачите результат.').forEach(function (n) { root.appendChild(n); });
    var copy = t.state && t.state.canva_copy_id;
    var extra = copy ? null : { ok: false, why: 'Копії в Canva ще немає: спершу запишіть шаблон (крок 4).' };
    var rb = requestButton('verify', 'verify-canva', 'Запустити перевірку', '/verify', 'Створюю завдання…', extra, 'Завдання створено. Тепер виконайте /studio у сесії Claude Code.');
    root.appendChild(el('div', { class: 'actions' }, rb.btn, copy ? designLink(copy) : null));
    if (!rb.info.ok && rb.info.why) root.appendChild(el('p', { class: 'hint', text: rb.info.why }));
    root.appendChild(el('p', null, 'Копія в Canva: ', copy ? el('span', { class: 'mono', 'data-test': 'copy-id', text: String(copy) }) : el('span', { class: 'muted', text: 'ще не створена' })));

    var info = t.job_results && t.job_results.verify;
    var jb = jobBlock(info, t.state.steps.verify.status === 'waiting_claude' ? 'Чекаємо на Claude: у його сесії виконайте /studio.' : null);
    if (jb) root.appendChild(jb);

    root.appendChild(el('h3', { text: 'Таблиця перевірок' }));
    var checks = info && Array.isArray(info.checks) ? info.checks.filter(isObj) : [];
    if (!checks.length) root.appendChild(el('p', { class: 'muted', id: 'checks-empty', text: 'Результату перевірки ще немає.' }));
    else {
      var passed = checks.filter(function (c) { return c.passed === true; }).length;
      root.appendChild(el('p', { id: 'checks-summary', 'data-test': 'checks-summary', text: 'Пройшло ' + passed + ' із ' + checks.length + '.' }));
      root.appendChild(el('div', { class: 'table-wrap' }, el('table', { id: 'checks-table', 'data-test': 'checks-table' },
        el('thead', null, el('tr', null, ['Перевірка', 'Результат', 'Подробиці'].map(function (h) { return el('th', { scope: 'col', text: h }); }))),
        el('tbody', null, checks.map(function (c) {
          var ok = c.passed === true;
          return el('tr', { 'data-test': 'check-row', 'data-passed': ok ? 'true' : 'false' },
            el('td', { text: strOr(c.name, '—') }), el('td', null, badge(ok ? 'пройшло' : 'не пройшло', ok ? 'b-pass' : 'b-fail')),
            el('td', { text: c.detail === undefined || c.detail === null ? '' : String(c.detail) }));
        })))));
    }

    var m = t.map;
    var pages = isObj(m) && Array.isArray(m.pages) ? m.pages.filter(isObj) : [];
    if (pages.length) {
      root.appendChild(el('h3', { text: 'Сторінки' }));
      root.appendChild(el('ul', { 'data-test': 'verify-pages' }, pages.map(function (p) { return el('li', { text: p.index + '. ' + strOr(p.title, '') }); })));
    }

    root.appendChild(el('h3', { text: 'Чекліст шрифтів' }));
    root.appendChild(el('p', { class: 'hint', text: 'Конектор Canva шрифти не змінює. Замініть шрифти вручну в Canva за цим списком і відмічайте зроблене.' }));
    var fc = Array.isArray(t.font_checklist) ? t.font_checklist.filter(isObj) : [];
    if (!fc.length) root.appendChild(el('p', { class: 'muted', text: 'Чекліст з’явиться, коли будуть стиль і карта.' }));
    else {
      root.appendChild(el('div', { class: 'table-wrap' }, el('table', { id: 'font-checklist', 'data-test': 'font-checklist' },
        el('thead', null, el('tr', null, ['Зроблено', 'Текст', 'Роль', 'Шрифт'].map(function (h) { return el('th', { scope: 'col', text: h }); }))),
        el('tbody', null, fc.map(function (r) {
          var loc = strOr(r.locator, '');
          var cb = el('input', { type: 'checkbox', 'aria-label': 'Шрифт для ' + loc + ' замінено', checked: loadFlag(fontDoneKey(loc)) });
          cb.addEventListener('change', function () { saveFlag(fontDoneKey(loc), cb.checked); });
          return el('tr', { 'data-test': 'font-row' }, el('td', null, cb), el('td', { class: 'mono', text: loc }), el('td', { text: strOr(r.role, '') }), el('td', { text: strOr(r.font, '') }));
        })))));
    }

    root.appendChild(el('h3', { text: 'Ручні кроки' }));
    var manual = el('ol', { id: 'manual-steps', 'data-test': 'manual-steps' },
      el('li', { text: 'Замініть шрифти в Canva за чекслістом вище.' }),
      el('li', { text: 'Відкрийте копію в Canva і перегляньте її в повноекранному режимі на комп’ютері та в режимі телефона.' }),
      el('li', { text: 'Переконайтеся, що імена й дати стоять лише в полях з позначкою «персональне поле».' }),
      el('li', { text: 'Нічого не публікуйте, доки не переглянете результат цілком.' }));
    root.appendChild(manual);
    if (info && info.status === 'done') {
      var token = S.renderToken;
      getResult(info).then(function (res) {
        if (token !== S.renderToken || !res || !isObj(res.outputs) || !Array.isArray(res.outputs.manual_steps)) return;
        res.outputs.manual_steps.forEach(function (x) { if (typeof x === 'string') manual.appendChild(el('li', { text: x })); });
      });
    }
  }

  /* ------------------------------------------------------------------ polling */
  function genSig(g) {
    if (!g || (!(g.pending || []).length && !(g.recent || []).length && !g.error)) return 'none';
    return JSON.stringify([(g.pending || []).map(function (p) { return [p.job_id, p.state]; }), (g.recent || []).length, g.error || null]);
  }

  function tick() {
    Promise.all([api('GET', '/api/jobs'), api('GET', '/api/health')]).then(function (r) {
      var jobs = r[0];
      hideBanner();
      S.health = r[1];
      renderHealth();
      S.jobs = jobs.jobs || [];
      S.tplErrors = jobs.template_errors || {};
      var sig = jobsSig(jobs);
      var jobsChanged = (S.jobSig !== null && sig !== S.jobSig);
      S.jobSig = sig;

      var needGen = S.route.view === 'template' && S.tpl && S.tpl.generation && S.tpl.generation.pending.length > 0;
      var genPromise = needGen ? api('GET', '/api/gen') : Promise.resolve(null);
      return genPromise.then(function (gen) {
        var genChanged = false;
        if (gen) {
          S.queue = gen.queue;
          var gs = genSig(gen.templates ? gen.templates[S.route.name] : null);
          genChanged = gs !== S.genSig;  // baseline = the template payload loaded last (same shape)
          S.genSig = gs;
        }
        if (S.route.view === 'home') {
          if (jobsChanged) return loadHome();
          renderJobsPanel();
        } else if (S.route.view === 'template') {
          if (jobsChanged || genChanged) return refreshTemplate(true);
        } else if (S.route.view === 'skeleton') {
          if (jobsChanged) {
            return api('GET', '/api/skeletons/' + enc(S.route.name)).then(function (d) { S.skel = d; renderSkeleton(true); });
          }
        }
      });
    }).catch(function (e) {
      showBanner(errorText(e));
    }).then(function () {
      window.setTimeout(tick, POLL_MS);
    });
  }

  /* ------------------------------------------------------------------ boot */
  function boot() {
    qs('error-banner-close').addEventListener('click', hideBanner);
    qs('btn-refresh-panel').addEventListener('click', function () { S.dirty = false; qs('stale-notice').hidden = true; if (S.route.view === 'template') refreshTemplate(false); });
    qs('form-create-template').addEventListener('submit', onCreateTemplate);
    qs('form-create-skeleton').addEventListener('submit', onCreateSkeleton);
    window.addEventListener('hashchange', onRoute);
    onRoute();
    window.setTimeout(tick, POLL_MS);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
