// Browser regression checks. Requires Playwright and a Chromium-compatible browser.
// Optional: ANIME_BROWSER_EXECUTABLE and ANIME_LAYOUT_OUTPUT select local tools/output.
const { chromium } = require('playwright');
const { createServer } = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const output = process.env.ANIME_LAYOUT_OUTPUT;
const version = fs.readFileSync(path.join(root, 'metadata.yaml'), 'utf8').match(/^version:\s*(\S+)/m)[1];
const now = new Date();
const season = `${now.getFullYear()}-${String(Math.floor(now.getMonth() / 3) * 3 + 1).padStart(2, '0')}`;
const target = 'default:GroupMessage:12345678901234567890';
const items = Array.from({ length: 132 }, (_, index) => ({
  key: `anime:${index}`, title: index ? 'ごーすとみーつ・ぎゃる！' : 'FX戦士くるみちゃん',
  title_cn: index ? `Ghost Meets Gal! ${index}` : 'FX战士久留美',
  season, item_type: 'tv', region: 'jp', season_role: index ? 'continuing' : 'new',
  genres: ['TV', '日本', '漫画改', '萌系'], adaptation_types: ['manga'],
  sources: ['bangumi', 'bgmlist', 'yuc'],
  schedules: [{ weekday: 4, hour: 20, minute: 30 }],
  schedule_note: index ? '' : '来源时间不一致，已统一采用最早时间 20:30 JST（yuc）；其他来源：bgmlist 21:30 JST',
}));
const posts = [];
const requests = [];
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/embedded') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end('<iframe title="AstrBot plugin" src="/" style="position:fixed;inset:0;width:100%;height:100%;border:0"></iframe>');
    return;
  }
  if (url.pathname.startsWith('/api/')) {
    let body = {};
    if (req.method === 'POST') {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      body = JSON.parse(Buffer.concat(chunks).toString());
      posts.push({ endpoint: url.pathname, body });
    }
    let result = {};
    if (url.pathname === '/api/status') result = { sources: { bangumi: { status: 'ok', count: 132 }, yuc: { status: 'ok', count: 98 }, bgmlist: { status: 'ok', count: 102 } }, preferences: { display_timezone: 'Asia/Shanghai' }, template_definitions: [] };
    if (url.pathname === '/api/targets') result = { targets: [{ target_id: target, display_name: '已绑定的测试群聊与很长的群聊名称', enabled: true, subscribed: true }] };
    if (url.pathname === '/api/items') result = { items, count: items.length };
    if (url.pathname === '/api/subscriptions') result = { subscriptions: [{ anime_key: items[0].key, enabled: true, lead_minutes: 15, on_time: true }] };
    if (url.pathname === '/api/preferences') result = { preferences: body };
    if (url.pathname === '/api/refresh') result = { items, sources: {} };
    res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify(result));
    return;
  }
  const name = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
  if (!['index.html', 'style.css', 'controls.js', 'bridge.js', 'app.js'].includes(name)) {
    res.writeHead(404).end(); return;
  }
  requests.push({ name, version: url.searchParams.get('v') });
  res.writeHead(200, { 'Content-Type': name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html; charset=utf-8' });
  res.end(fs.readFileSync(path.join(root, 'views/management', name)));
});

async function main() {
  if (output) fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, ...(process.env.ANIME_BROWSER_EXECUTABLE ? { executablePath: process.env.ANIME_BROWSER_EXECUTABLE } : {}) });
  const failures = [], measurements = [], errors = [];
  try {
    for (const embedded of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 1332, height: 900 } });
      page.on('pageerror', error => errors.push(error.message));
      await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
      await page.goto(`http://127.0.0.1:${server.address().port}/${embedded ? 'embedded' : ''}`);
      const frame = embedded ? page.frames().find(frame => frame.parentFrame()) : page.mainFrame();
      await frame.waitForFunction(() => document.querySelectorAll('.anime-card').length === 132);
      for (const theme of ['dark', 'light']) {
        await frame.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
        for (const width of [1440, 1332, 1250, 1100, 960, 834, 821, 820, 768, 651, 650, 540, 390, 360]) {
          await page.setViewportSize({ width, height: 900 });
          for (const status of ['', '设置已保存。获取番组后应用新的排期来源。', '获取失败：来源响应超时，已保留已有数据。' + '请稍后重试，当前订阅不会丢失。'.repeat(6)]) {
            await frame.evaluate(status => {
              const notice = document.querySelector('#save-status');
              notice.hidden = !status;
              notice.className = `status-inline ${status.startsWith('获取失败') ? 'notice-error' : 'notice-success'}`;
              notice.querySelector('.status-inline-text').textContent = status;
            }, status);
            await frame.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
            const metrics = await frame.evaluate(() => {
              const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height, right:r.right, bottom:r.bottom }; };
              const overflow = document.documentElement.scrollWidth > innerWidth;
              const overflowing = overflow ? [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 8).map(el => ({ tag:el.tagName, class:el.className, right:el.getBoundingClientRect().right })) : [];
              return { viewport: innerWidth, overflow, overflowing, trigger:rect('#target + .select-trigger'), dock:rect('.catalog-command-row'), status:rect('#save-status'), read:rect('#load-subs'), save:rect('#save-subs') };
            });
            const label = `${embedded ? 'embedded' : 'remote'} ${theme} ${width} ${status ? 'status' : 'clear'}`;
            measurements.push({ label, ...metrics });
            if (metrics.trigger.width < 200 || metrics.trigger.height > 55 || metrics.overflow || metrics.dock.height > 330 || Math.abs(metrics.dock.bottom - 900) > 1) failures.push({ label, ...metrics });
            if (status && (metrics.status.width > 441 || metrics.status.width >= metrics.dock.width * 0.9 || Math.abs(metrics.status.right - metrics.save.right) > 1)) failures.push({ label: `${label}: notice must be compact and aligned to the right`, ...metrics });
            if (output && width === 1332 && status.startsWith('设置') && theme === 'dark' && !embedded) await frame.locator('.catalog-command-row').screenshot({ path: path.join(output, 'dock.png') });
          }
        }
      }
      await page.setViewportSize({ width: 1332, height: 900 });
      await frame.evaluate(() => document.querySelector('#save-status').hidden = true);
      await frame.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.equal(await frame.locator('.webui-version').textContent(), `v${version}`);
      await frame.getByRole('button', { name: '提醒发送到', exact: true }).click();
      const popup = frame.locator('#target').locator('..').locator('.select-popover');
      assert.equal(await popup.getAttribute('data-placement'), 'top');
      await frame.getByRole('option', { name: /已绑定的测试群聊/ }).click();
      assert.equal(await frame.locator('#target').inputValue(), target);
      await frame.locator('#load-subs').click();
      await frame.waitForFunction(() => document.querySelectorAll('.anime-card').length === 1);
      await frame.locator('#load-subs').click();
      await frame.waitForFunction(() => document.querySelectorAll('.anime-card').length === 132);
      await frame.locator('#save-subs').click();
      await frame.waitForFunction(() => document.querySelector('#save-status').textContent.includes('已保存'));
      assert.equal(posts.at(-1).body.target_id, target);
      const longLabel = await frame.locator('#target + .select-trigger').getAttribute('title');
      assert.match(longLabel, /已绑定的测试群聊/);
      await frame.locator('#refresh').click();
      await frame.waitForFunction(() => !document.querySelector('#refresh').disabled);
      assert.equal(await frame.locator('#refresh').textContent(), '获取番组');
      assert.equal((await frame.locator('body').innerText()).includes('番表'), false);
      for (const width of [1332, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await frame.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        await frame.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
        const visible = await frame.evaluate(() => document.querySelector('.anime-card:last-child').getBoundingClientRect().bottom <= document.querySelector('.catalog-command-row').getBoundingClientRect().top);
        if (!visible) failures.push({ label: `Last card covered by dock at ${width}px`, embedded });
      }
      await frame.locator('#show-settings').click();
      assert.equal(await frame.locator('.catalog-command-row').isVisible(), false);
      const settingsWidth = await frame.locator('#settings-view').evaluate(el => el.getBoundingClientRect().width);
      await frame.locator('#show-messages').click();
      assert.equal(await frame.locator('#messages-view').evaluate(el => el.getBoundingClientRect().width), settingsWidth);
      await frame.locator('#show-catalog').click();
      for (const type of ['剧场版', 'OVA', 'TV', '所有类型']) {
        await frame.getByRole('button', { name: '类型', exact: true }).click();
        await frame.getByRole('option', { name: type, exact: true }).click();
        assert.equal(await frame.locator('#weekday-filter').isVisible(), !['剧场版', 'OVA'].includes(type));
      }
      await frame.waitForFunction(() => document.querySelectorAll('.anime-card').length === 132);
      for (const view of ['show-settings', 'show-messages', 'show-catalog']) {
        await frame.locator('#' + view).click();
        for (const width of [834, 390, 360]) {
          await page.setViewportSize({ width, height: 900 });
          assert.equal(await frame.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${view} overflows at ${width}`);
        }
      }
      await page.setViewportSize({ width: 1332, height: 900 });
      await frame.evaluate(() => document.documentElement.dataset.theme = 'dark');
      await frame.evaluate(() => window.scrollTo(0, 0));
      if (output && !embedded) {
        await page.screenshot({ path: path.join(output, 'catalog.png') });
        await frame.locator('.catalog-head').screenshot({ path: path.join(output, 'catalog-heading.png') });
        await frame.locator('.anime-card').first().screenshot({ path: path.join(output, 'anime-card.png') });
        await page.setViewportSize({ width:390, height:900 });
        await page.screenshot({ path: path.join(output, 'mobile.png') });
      }
      await page.close();
    }
    assert.deepEqual(errors, []);
    if (output) fs.writeFileSync(path.join(output, 'layout-audit.json'), JSON.stringify({ failures, measurements, errors }, null, 2));
    assert.equal(failures.length, 0, `Layout failures: ${JSON.stringify(failures.slice(0, 3))}`);
    for (const asset of ['style.css', 'bridge.js', 'controls.js', 'app.js']) assert.ok(requests.some(request => request.name === asset && request.version === version), `${asset} must load the current release version`);
    console.log(`Passed ${measurements.length} layouts plus group selection, upward popup, read/save, refresh, scrolling and view-switch checks.`);
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
