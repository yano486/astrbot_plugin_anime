import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../views/management/login.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../views/management/login.html', import.meta.url), 'utf8');

function setup(fetch) {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, {
      hidden: false, disabled: false, textContent: '', value: '', handler: null,
      addEventListener(_type, handler) { this.handler = handler; },
      select() { this.selected = true; },
    });
    return elements.get(selector);
  };
  const navigated = [];
  const sandbox = vm.createContext({
    document: { querySelector: get },
    window: { location: { replace: value => navigated.push(value) } },
    fetch,
  });
  vm.runInContext(source, sandbox);
  return { get, navigated };
}

test('login page asks for a numeric PIN in an embedded form', () => {
  assert.match(html, /id="login-form"/);
  assert.match(html, /inputmode="numeric"/);
  assert.match(html, /maxlength="8"/);
});

test('successful login posts the password and redirects without browser auth', async () => {
  const requests = [];
  const pin = '12'.repeat(4);
  const app = setup(async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ authenticated: true }) };
  });
  app.get('#password').value = pin;
  await app.get('#login-form').handler({ preventDefault() {} });
  assert.equal(requests[0].url, '/api/login');
  assert.equal(requests[0].options.method, 'POST');
  assert.equal(requests[0].options.credentials, 'same-origin');
  assert.equal(JSON.parse(requests[0].options.body).password, pin);
  assert.deepEqual(app.navigated, ['/']);
});

test('failed login displays the server error inline and keeps the form usable', async () => {
  const app = setup(async () => ({ ok: false, status: 401, json: async () => ({ error: '密码不正确' }) }));
  app.get('#password').value = '0000';
  await app.get('#login-form').handler({ preventDefault() {} });
  assert.equal(app.get('#login-error').textContent, '密码不正确');
  assert.equal(app.get('#login-error').hidden, false);
  assert.equal(app.get('#login-button').disabled, false);
  assert.deepEqual(app.navigated, []);
});
