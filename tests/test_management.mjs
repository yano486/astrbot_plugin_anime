import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../views/management/app.js', import.meta.url), 'utf8');
const markup = readFileSync(new URL('../views/management/index.html', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../views/management/style.css', import.meta.url), 'utf8');
const controlsUrl = new URL('../views/management/controls.js', import.meta.url);
const controls = existsSync(controlsUrl) ? readFileSync(controlsUrl, 'utf8') : '';

class Element {
  value = '';
  textContent = '';
  children = [];
  disabled = false;
  set innerHTML(value) { this.html = value; this.children = []; this.value = ''; }
  get innerHTML() { return this.html || ''; }
  append(value) { this.children.push(value); }
  replaceChildren(...values) { this.children = values; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener() {}
}

function setup(apiGet, apiPost = async () => ({}), options = {}) {
  const elements = new Map();
  const getElement = name => {
    if (!elements.has(name)) elements.set(name, new Element());
    return elements.get(name);
  };
  const window = { AstrBotPluginView: { ready: () => new Promise(() => {}), apiGet, apiPost }, localStorage: { getItem: () => null, setItem() {} } };
  if (options.withLocalStorage === false) delete window.localStorage;
  const sandbox = vm.createContext({
    window,
    document: { querySelector: getElement, createElement: () => new Element(), querySelectorAll: () => [], documentElement: { dataset: {} } },
    console, Date, Map, Set,
  });
  vm.runInContext(source, sandbox);
  return { run: code => vm.runInContext(code, sandbox), element: getElement };
}

test('refreshing target list preserves the selected group', async () => {
  const app = setup(async () => ({ targets: [{ target_id: 'group:A', enabled: true }] }));
  app.element('#target').value = 'group:A';
  await app.run('loadTargets()');
  assert.equal(app.element('#target').value, 'group:A');
});

test('a slower group A response cannot overwrite group B subscriptions', async () => {
  const pending = [];
  const app = setup((endpoint, params) => new Promise(resolve => pending.push({ params, resolve })));
  app.element('#target').value = 'group:A';
  const first = app.run('loadSubscriptions()');
  app.element('#target').value = 'group:B';
  const second = app.run('loadSubscriptions()');
  pending[1].resolve({ subscriptions: [{ anime_key: 'B', enabled: true }] });
  await second;
  pending[0].resolve({ subscriptions: [{ anime_key: 'A', enabled: true }] });
  await first;
  assert.equal(app.run('state.subscriptions.has("B")'), true);
  assert.equal(app.run('state.subscriptions.has("A")'), false);
});

test('saving cannot copy the loaded group subscriptions into a different target', async () => {
  let posts = 0;
  const app = setup(async endpoint => endpoint === 'subscriptions'
    ? { subscriptions: [{ anime_key: 'A', enabled: true, on_time: true }] }
    : { targets: [] }, async () => { posts++; return { saved: 1 }; });
  app.element('#target').value = 'group:A';
  await app.run('loadSubscriptions()');
  app.element('#target').value = 'group:B';
  await app.run('saveSubscriptions()');
  assert.equal(posts, 0);
});

test('Monday 00:30 Japan displays Sunday 23:30 Beijing', () => {
  const app = setup(async () => ({}));
  const text = app.run('firstTime({schedules:[{weekday:1,hour:0,minute:30}]}, "Asia/Shanghai")');
  assert.match(text, /北京 周日 23:30/);
});

test('Japan display preference keeps the Japanese weekday and clock', () => {
  const app = setup(async () => ({}));
  const text = app.run('firstTime({schedules:[{weekday:1,hour:23,minute:0}]}, "Asia/Tokyo")');
  assert.match(text, /日本 周一 23:00/);
});

test('embedded management view works when sandbox blocks localStorage', () => {
  const app = setup(async () => ({}), async () => ({}), { withLocalStorage: false });
  assert.doesNotThrow(() => app.run('setTheme("dark")'));
  assert.equal(app.run('document.documentElement.dataset.theme'), 'dark');
});

test('year options omit invalid dates and include every catalog year', () => {
  const app = setup(async () => ({}));
  const values = app.run('periodOptions("", [{item_type:"tv",season:"2025-10"},{item_type:"movie",release_date:"2027-04-10"},{item_type:"ova",release_date:"None"}], new Date(2026,10,4)).map(option => option.value).join(",")');
  assert.equal(values, '2025,2026,2027');
});

test('TV and WEB filters use quarters while all types, OVA, and movies use years', () => {
  const app = setup(async () => ({}));
  assert.equal(app.run('catalogPeriodMode("tv")'), 'season');
  assert.equal(app.run('catalogPeriodMode("web")'), 'season');
  assert.equal(app.run('catalogPeriodMode("")'), 'year');
  assert.equal(app.run('catalogPeriodMode("ova")'), 'year');
  assert.equal(app.run('catalogPeriodMode("movie")'), 'year');
});

test('season choices show the previous, current, and next quarter without a duplicate masthead control', () => {
  const app = setup(async () => ({}));
  const values = app.run('seasonPeriodOptions(new Date(2026,10,4)).map(option => option.value).join(",")');
  assert.equal(values, '2026-07,2026-10,2027-01');
  assert.doesNotMatch(markup, /id="season"/);
  assert.match(markup, /id="period"/);
});

test('all-types year filter matches TV seasons and movie release years', () => {
  const app = setup(async () => ({}));
  assert.equal(app.run('matchesCatalogPeriod({item_type:"tv",season:"2026-10"}, "", "2026")'), true);
  assert.equal(app.run('matchesCatalogPeriod({item_type:"movie",release_date:"2026-12-01"}, "", "2026")'), true);
  assert.equal(app.run('matchesCatalogPeriod({item_type:"web",season:"2025-10"}, "", "2026")'), false);
});

test('year catalog queries load all cached seasons for client-side year filtering', async () => {
  const calls = [];
  const app = setup(async (endpoint, params) => {
    calls.push({ endpoint, params });
    return { items: [], count: 0, updated_at: "" };
  });
  app.element('#type').value = '';
  app.element('#period').value = '2026';
  await app.run('configurePeriodControl(); loadItems(false)');
  assert.equal(calls[0].params.season, 'all');
});

test('TV season catalog query requests only the selected quarter', async () => {
  const calls = [];
  const app = setup(async (endpoint, params) => {
    calls.push({ endpoint, params });
    return { items: [], count: 0, updated_at: "" };
  });
  app.element('#type').value = 'tv';
  app.element('#period').value = '2026-07';
  await app.run('configurePeriodControl(); document.querySelector("#period").value="2026-07"; loadItems(false)');
  assert.equal(calls[0].params.season, '2026-07');
});

test('filters use explicit persistent labels separate from selected values', () => {
  assert.match(markup, /id="region-label" class="filter-label">地区/);
  assert.match(markup, /id="weekday-label" class="filter-label">星期/);
});

test('settings page exposes whitelist, test-push, and remote WebUI status', () => {
  assert.match(markup, /id="show-settings"/);
  assert.match(markup, /id="save-whitelist"/);
  assert.match(markup, /id="test-push"/);
  assert.match(markup, /id="remote-webui-status"/);
  assert.match(markup, /id="umo-target"/);
  assert.match(markup, /id="schedule-source"/);
  assert.match(markup, /id="display-timezone"/);
  assert.match(markup, /id="test-reminder-card"/);
  assert.match(markup, /id="test-update-card"/);
  assert.match(markup, /id="toggle-theme"/);
  assert.match(source, /removeWhitelist/);
  assert.match(source, /class="button button-quiet remove-whitelist"/);
});

test('catalog fetch action is labelled as getting the schedule', () => {
  assert.match(markup, /id="refresh"[^>]*>获取番表</);
  assert.doesNotMatch(markup, /id="refresh"[^>]*>刷新番表</);
});

test('catalog navigation and headings use subscription wording and settings owns push tests', () => {
  assert.match(markup, /id="show-catalog"[^>]*>动画订阅</);
  assert.match(markup, /id="show-settings"[^>]*>设置</);
  assert.match(markup, /<h2>动画订阅列表<\/h2>/);
  assert.doesNotMatch(markup, /季度片单|设置与推送测试/);
  assert.doesNotMatch(markup, /class="section-index"/);
});

test('management UI loads custom controls and does not use native date inputs', () => {
  assert.match(markup, /src="\.\/controls\.js"/);
  assert.match(controls, /role", "listbox"|role="listbox"/);
  assert.match(controls, /ArrowDown/);
  assert.match(controls, /role", "dialog"|role="dialog"/);
  assert.doesNotMatch(source, /type="date"/);
  assert.match(styles, /\.select-popover/);
  assert.match(styles, /\.date-popover/);
});

test('push test panel uses a full-width heading and separate responsive control rows', () => {
  assert.match(markup, /class="test-push-panel"[\s\S]*class="test-push-heading"/);
  assert.match(markup, /class="test-push-targets"[\s\S]*id="test-target"[\s\S]*id="test-item"/);
  assert.match(markup, /class="test-push-actions"[\s\S]*id="test-reminder-card"[\s\S]*id="test-update-card"/);
  assert.match(styles, /\.test-push-panel\s*\{[^}]*display:\s*grid/s);
  assert.match(styles, /\.test-push-actions\s*\{[^}]*grid-template-columns/s);
});

test('YUC remains available in source filter even when the current items lack it', () => {
  const app = setup(async () => ({}));
  app.run('state.items = []; state.sources = {bangumi: {status:"ok"}}; sourceChoices()');
  assert.equal(app.element('#source').children.some(option => option.value === 'yuc'), true);
});

test('catalog cards make Bangumi covers links and let other card areas toggle selection', () => {
  assert.match(source, /class="cover-link"/);
  assert.match(source, /event\.target\.closest\("a, input, button, select, label"\)/);
  assert.match(source, /updateSelected\(\)/);
});
