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
  hidden = false;
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

test('reading subscriptions limits the visible catalog to checked items and can be toggled off', async () => {
  const app = setup(async endpoint => endpoint === 'subscriptions'
    ? { subscriptions: [{ anime_key: 'A', enabled: true }, { anime_key: 'B', enabled: false }] }
    : {});
  app.element('#target').value = 'group:A';
  await app.run('loadSubscriptions()');
  app.run('state.items = [{key:"A"}, {key:"B"}, {key:"C"}]');
  assert.equal(app.run('visibleCatalogItems().map(item => item.key).join(",")'), 'A');
  app.run('state.items = []');
  await app.run('loadSubscriptions()');
  assert.equal(app.run('state.showSubscribedOnly'), false);
  app.run('state.items = [{key:"A"}, {key:"B"}, {key:"C"}]');
  assert.equal(app.run('visibleCatalogItems().map(item => item.key).join(",")'), 'A,B,C');
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
  const values = app.run('periodOptions("movie", [{item_type:"movie",release_date:"2025-10-01"},{item_type:"movie",release_date:"2027-04-10"},{item_type:"ova",release_date:"None"}], new Date(2026,10,4)).map(option => option.value).join(",")');
  assert.equal(values, '2025,2026,2027');
});

test('TV and WEB filters use quarters while all types, OVA, and movies use years', () => {
  const app = setup(async () => ({}));
  assert.equal(app.run('catalogPeriodMode("tv")'), 'season');
  assert.equal(app.run('catalogPeriodMode("web")'), 'season');
  assert.equal(app.run('catalogPeriodMode("")'), 'broadcast');
  assert.equal(app.run('catalogPeriodMode("ova")'), 'year');
  assert.equal(app.run('catalogPeriodMode("movie")'), 'year');
});

test('all-types broadcast choices put the current season first and limit fetching scope', () => {
  const app = setup(async () => ({}));
  const options = app.run('periodOptions("", [], new Date(2026,10,4))');
  assert.equal(options.map(option => option.value).join(","), '2026-10,2026-01,2026-04,2026-07,2026-h1,2026-h2,2026-all');
  assert.equal(app.run('periodLabel("", "2026-10")'), '秋 · 10月');
  assert.equal(app.run('periodLabel("", "2026-all")'), '全年');
  assert.equal(app.run('periodsForSelection("", "2026-h1").join(",")'), '2026-01,2026-04');
});

test('weekday dropdown is removed but compact weekday buttons remain', () => {
  assert.doesNotMatch(markup, /id="weekday"/);
  assert.match(markup, /id="weekday-buttons"/);
  assert.match(markup, /data-weekday="1"[^>]*>一/);
  assert.match(markup, /data-weekday="7"[^>]*>日/);
  assert.match(markup, /id="adaptation-filter"/);
  assert.doesNotMatch(markup, /id="role-filter"|跨季续播/);
  assert.match(source, /syncWeekdayButtons/);
  assert.match(source, /state\.weekday/);
  assert.match(source, /#weekday-buttons \[data-weekday\]/);
});

test('adaptation type filter matches Bangumi-origin categories rather than season roles', () => {
  const app = setup(async () => ({}));
  assert.match(markup, />小说改</);
  assert.match(markup, />漫画改</);
  assert.match(markup, />游戏改</);
  assert.match(markup, />原创</);
  assert.match(source, /item\.adaptation_types\s*\|\|\s*\[\]/);
  assert.doesNotMatch(source, /item\.season_role !== role/);
  assert.match(source, /adaptationBadges/);
  assert.equal(app.run('matchesAdaptationType({genres:["轻小说改"]}, "novel")'), true);
  assert.equal(app.run('matchesAdaptationType({genres:["漫画改"]}, "novel")'), false);
});

test('early access type targets the next quarter and keeps only supported filters', () => {
  const app = setup(async () => ({}));
  assert.equal(app.run('catalogPeriodMode("preview")'), 'preview');
  assert.equal(app.run('nextSeason(new Date(2026, 6, 1))'), '2026-10');
  assert.equal(app.run('nextSeason(new Date(2026, 9, 1))'), '2027-01');
  assert.match(markup, /新番抢先看/);
  assert.match(source, /type === "preview"/);
});

test('early access mode keeps TV and WEB items instead of treating preview as an item type', () => {
  const app = setup(async () => ({}));
  assert.equal(app.run('matchesCatalogType("tv", "preview")'), true);
  assert.equal(app.run('matchesCatalogType("web", "preview")'), true);
  assert.equal(app.run('matchesCatalogType("tv", "tv")'), true);
  assert.equal(app.run('matchesCatalogType("web", "tv")'), false);
});

test('preview mode displays the low-source advisory', () => {
  const app = setup(async () => ({}));
  app.run('updatePreviewHint("preview")');
  assert.equal(app.element('#preview-hint').hidden, false);
  app.run('updatePreviewHint("tv")');
  assert.equal(app.element('#preview-hint').hidden, true);
  assert.match(markup, /id="preview-hint"[^>]*>数据源不足，请耐心等待/);
});

test('season choices show the previous, current, and next quarter without a duplicate masthead control', () => {
  const app = setup(async () => ({}));
  const values = app.run('seasonPeriodOptions(new Date(2026,10,4)).map(option => option.value).join(",")');
  assert.equal(values, '2026-10,2026-01,2026-04,2026-07');
  assert.doesNotMatch(markup, /id="season"/);
  assert.match(markup, /id="period"/);
});

test('all-types broadcast filter matches seasons and movie release months', () => {
  const app = setup(async () => ({}));
  assert.equal(app.run('matchesCatalogPeriod({item_type:"tv",season:"2026-10"}, "", "2026-10")'), true);
  assert.equal(app.run('matchesCatalogPeriod({item_type:"movie",release_date:"2026-10-01"}, "", "2026-10")'), true);
  assert.equal(app.run('matchesCatalogPeriod({item_type:"web",season:"2025-10"}, "", "2026-10")'), false);
});

test('year catalog queries load all cached seasons for client-side year filtering', async () => {
  const calls = [];
  const app = setup(async (endpoint, params) => {
    calls.push({ endpoint, params });
    return { items: [], count: 0, updated_at: "" };
  });
  app.element('#type').value = 'movie';
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

test('preview selection refreshes the next quarter before reading its catalog', async () => {
  const calls = [];
  const app = setup(async (endpoint, params) => {
    calls.push({kind: 'get', endpoint, params});
    return {items: [], count: 0, updated_at: ""};
  }, async (endpoint, payload) => {
    calls.push({kind: 'post', endpoint, payload});
    return {};
  });
  app.element('#type').value = 'preview';
  await app.run('configurePeriodControl(); loadItems(true)');
  assert.equal(calls.find(call => call.kind === 'post').endpoint, 'refresh');
  assert.equal(calls.find(call => call.kind === 'post').payload.seasons.join(','), '2027-01');
  assert.match(source, /loadItems\(type === "preview"\)/);
});

test('filters use explicit persistent labels separate from selected values', () => {
  assert.match(markup, /id="region-label" class="filter-label">地区/);
  assert.match(markup, /id="period-label" class="filter-label">上映年份/);
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
  assert.match(markup, /id="exclude-r18"/);
  assert.match(markup, /排除 R18/);
  assert.match(source, /removeWhitelist/);
  assert.match(source, /class="button button-quiet remove-whitelist"/);
});

test('R18 preference uses a styled yes-or-no select', () => {
  assert.match(markup, /id="exclude-r18"[^>]*>[\s\S]*>否</);
  assert.match(markup, /id="exclude-r18"[^>]*>[\s\S]*>是</);
  assert.doesNotMatch(markup, /id="exclude-r18"[^>]*type="checkbox"/);
});

test('catalog places the push target row beside search and keeps filters in the second boxed row', () => {
  assert.match(markup, /class="catalog-command-row"[\s\S]*class="search"[\s\S]*class="target-row"/);
  assert.match(markup, /class="catalog-command-row"[\s\S]*<\/section>[\s\S]*class="toolbar"/);
  assert.doesNotMatch(markup, /class="toolbar"[\s\S]*class="search"/);
});

test('catalog actions use a fixed bottom dock with compact inline status', () => {
  assert.match(markup, /id="save-status"/);
  assert.match(markup, /class="target-row"[\s\S]*id="save-status"/);
  assert.doesNotMatch(markup, /dismiss-status/);
  assert.match(styles, /\.catalog-command-row\{[^}]*position:fixed/);
  assert.match(styles, /\.status-inline\{/);
  assert.doesNotMatch(styles, /\.status-notice\{/);
});

test('bottom status message can expand within the fixed target row', () => {
  assert.match(styles, /\.status-inline\{[^}]*flex:\s*1 1 360px/s);
  assert.match(styles, /\.status-inline\{[^}]*max-width:none/s);
  assert.doesNotMatch(styles, /\.status-inline\{[^}]*max-width:260px/);
  assert.match(styles, /@media\(max-width:650px\)\{\.catalog-command-row \.target-row \.status-inline\{flex-basis:100%\}/);
});

test('calendar month navigation restores focus after rerendering month buttons', () => {
  assert.match(controls, /function renderCalendar\(control, restoreFocus = ""\)/);
  assert.match(controls, /renderCalendar\(control, "previous"\)/);
  assert.match(controls, /renderCalendar\(control, "next"\)/);
  assert.match(controls, /focus\(\{ preventScroll: true \}\)/);
});

test('fetch button keeps readable foreground colors in both themes', () => {
  assert.match(markup, /id="refresh"[^>]*>获取番表</);
  assert.match(styles, /\.button-dark\{color:#fff\}/);
  assert.match(styles, /html\[data-theme="dark"\] \.button-dark\{[^}]*color:#182526/);
});

test('weekday buttons receive more toolbar width than adaptation and year filters', () => {
  assert.ok(styles.includes('.toolbar{grid-template-columns:minmax(115px,1fr) minmax(80px,.75fr) minmax(250px,1.8fr) minmax(100px,.7fr) minmax(90px,.65fr) minmax(100px,.8fr)'));
  assert.match(styles, /\.weekday-buttons button\{[^}]*min-height:42px/);
  assert.ok(styles.includes('.toolbar .weekday-filter{grid-column:1/-1}'));
});

test('empty future sources produce a compact fetch result instead of an error toast', () => {
  const app = setup(async () => ({}));
  const message = app.run('state.sources = {bangumi:{status:"ok",count:100}, bgmlist:{status:"empty"}, yuc:{status:"empty"}}; sourceFailureNotice()');
  assert.equal(message, '已获取番表；bgmlist暂无数据、yuc暂无数据');
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
  assert.match(controls, /positionPopover\(control\)/);
  assert.match(controls, /dataset\.placement\s*=\s*below < popupHeight \+ 8 && above > below \? "top" : "bottom"/);
  assert.match(styles, /\.select-popover\[data-placement="top"\]/);
  assert.match(styles, /\.date-popover\[data-placement="top"\]/);
  assert.match(styles, /\.date-popover\[data-align="right"\]/);
  assert.match(styles, /\.catalog-command-row \.target-row \.select-control\{width:auto;flex:1/);
});

test('push test panel uses a full-width heading and separate responsive control rows', () => {
  assert.match(markup, /class="test-push-panel"[\s\S]*class="test-push-heading"/);
  assert.match(markup, /class="test-push-targets"[\s\S]*id="test-target"[\s\S]*id="test-item"/);
  assert.match(markup, /class="test-push-actions"[\s\S]*id="test-reminder-card"[\s\S]*id="test-update-card"/);
  assert.match(styles, /\.test-push-panel\s*\{[^}]*display:\s*grid/s);
  assert.match(styles, /\.test-push-actions\s*\{[^}]*grid-template-columns/s);
  assert.match(styles, /\.test-push-panel\{[^}]*padding:12px 14px/);
  assert.match(styles, /\.test-push-actions \.button\{[^}]*min-height:40px/s);
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
