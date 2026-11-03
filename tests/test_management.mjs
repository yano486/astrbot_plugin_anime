import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../views/management/app.js', import.meta.url), 'utf8');
const markup = readFileSync(new URL('../views/management/index.html', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../views/management/style.css', import.meta.url), 'utf8');

class Element {
  value = '';
  textContent = '';
  children = [];
  disabled = false;
  set innerHTML(value) { this.html = value; this.children = []; this.value = ''; }
  get innerHTML() { return this.html || ''; }
  append(value) { this.children.push(value); }
  replaceChildren(...values) { this.children = values; }
  addEventListener() {}
}

function setup(apiGet, apiPost = async () => ({})) {
  const elements = new Map();
  const getElement = name => {
    if (!elements.has(name)) elements.set(name, new Element());
    return elements.get(name);
  };
  const sandbox = vm.createContext({
    window: { AstrBotPluginView: { ready: () => new Promise(() => {}), apiGet, apiPost }, localStorage: { getItem: () => null, setItem() {} } },
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

test('movie year filter omits invalid dates such as the string None', () => {
  const app = setup(async () => ({}));
  app.run('state.items = [{item_type:"movie", release_date:"None"}, {item_type:"ova", release_date:"2027-04-10"}]');
  app.run('movieYears()');
  const options = app.element('#movie-year').children;
  assert.equal(options.some(option => option.value === 'None'), false);
  assert.equal(options.some(option => option.value === '2027'), true);
});

test('touch filters keep a visible field label outside the native select value', () => {
  assert.match(markup, /class="filter-control"><span>地区<\/span><select id="region"/);
  assert.match(markup, /class="filter-control"><span>星期<\/span><select id="weekday"/);
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
