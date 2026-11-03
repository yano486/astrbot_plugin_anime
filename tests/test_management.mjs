import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../views/management/app.js', import.meta.url), 'utf8');

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
    window: { AstrBotPluginView: { ready: () => new Promise(() => {}), apiGet, apiPost } },
    document: { querySelector: getElement, createElement: () => new Element(), querySelectorAll: () => [] },
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
  const text = app.run('firstTime({schedules:[{weekday:1,hour:0,minute:30}]})');
  assert.match(text, /北京 周日 23:30/);
});
