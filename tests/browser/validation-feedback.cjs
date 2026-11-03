/* Manual browser regression: run a mock-mode local server, then this script with Playwright available.
   UI_QA_BASE_URL defaults to http://127.0.0.1:8788. Only fictional accounts are created. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const base = process.env.UI_QA_BASE_URL || 'http://127.0.0.1:8788';
if (!['localhost', '127.0.0.1'].includes(new URL(base).hostname)) throw new Error('Use a local test server.');
const evidence = process.env.UI_QA_OUTPUT || path.resolve('docs/qa/UI-final-2026-11-04');
fs.mkdirSync(evidence, { recursive: true });
const checks = [];
function check(name, pass, details) { checks.push({ name, pass, details }); if (!pass) console.log(JSON.stringify(checks.at(-1))); }
async function visibleErrors(form) {
  return form.locator('.field-error').evaluateAll(elements => elements.filter(e => e.textContent && e.getClientRects().length).map(e => e.textContent));
}
async function emptySummary(form) { return form.locator('.form-status').evaluateAll(elements => elements.every(e => !e.textContent.trim() || !e.getClientRects().length)); }
async function fits(page) { return page.evaluate(() => document.documentElement.scrollWidth <= innerWidth); }

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height] of [[360, 800], [1440, 1000]]) {
      const label = width + 'px';
      const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce', serviceWorkers: 'block' });
      const page = await context.newPage(), errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let authPosts = 0;
      page.on('request', request => { if (request.method() === 'POST' && ['/login', '/signup'].includes(new URL(request.url()).pathname)) authPosts++; });
      await page.goto(base + '/login', { waitUntil: 'networkidle' });
      const login = page.locator('form[action="/login"]');
      await login.locator('button[type=submit]').click();
      check(label + ': each blank login field has one inline error', (await visibleErrors(login)).length === 2);
      check(label + ': no duplicate error below login button', await emptySummary(login));
      check(label + ': invalid login is not submitted or disabled', authPosts === 0 && await login.locator('button').isEnabled());
      check(label + ': first invalid control is focused', await login.locator('[name=email]').evaluate(e => document.activeElement === e && e.getAttribute('aria-invalid') === 'true'));
      for (let i = 0; i < 3; i++) await login.locator('button').click();
      check(label + ': repeated attempts do not accumulate alerts', await login.locator('.field-error').count() === 2 && await emptySummary(login));
      check(label + ': login fits viewport', await fits(page));
      await page.screenshot({ path: path.join(evidence, 'login-' + (width === 360 ? 'mobile' : 'desktop') + '.png'), fullPage: true });
      await login.locator('[name=email]').fill('invalid-address');
      await login.locator('button').click();
      check(label + ': invalid email stays inline', (await visibleErrors(login)).some(message => message.includes('이메일 주소 형식')) && await emptySummary(login));
      await login.locator('[name=email]').fill('ui-qa-login@example.test');
      check(label + ': fixing a field clears its text and aria error', await login.locator('[name=email]').evaluate(e => !e.hasAttribute('aria-invalid') && !e.closest('.field').querySelector('.field-error').textContent));
      await login.locator('[name=password]').fill('123');
      await login.locator('button').click();
      check(label + ': short password remains inline', (await visibleErrors(login)).length === 1 && await emptySummary(login));
      await login.locator('[name=password]').fill('ui-qa-not-a-real-password');
      const failedLogin = page.waitForResponse(response => response.url() === base + '/login' && response.request().method() === 'POST');
      await login.locator('button').click();
      check(label + ': authentication failure still comes from server', (await failedLogin).status() === 400);
      await page.waitForLoadState('networkidle');
      check(label + ': server login error remains visible', await page.locator('.note-error').isVisible() && (await page.locator('.note-error').innerText()).includes('이메일 또는 비밀번호'));

      await page.goto(base + '/signup', { waitUntil: 'networkidle' });
      const signup = page.locator('form[action="/signup"]');
      await signup.locator('button').click();
      check(label + ': all three signup errors remain inline', (await visibleErrors(signup)).length === 3 && await emptySummary(signup));
      check(label + ': password helper is preserved alongside its error', (await signup.locator('[name=password]').getAttribute('aria-describedby')).split(' ').includes('pw-help'));
      await page.screenshot({ path: path.join(evidence, 'signup-' + (width === 360 ? 'mobile' : 'desktop') + '.png'), fullPage: true });
      await signup.locator('[name=email]').fill('ui-qa-' + width + '-' + Date.now() + '@example.test');
      await signup.locator('[name=nickname]').fill('T-UI');
      await signup.locator('[name=password]').fill('ui-qa-fictional-password');
      check(label + ': corrected signup clears all field errors', (await visibleErrors(signup)).length === 0 && await emptySummary(signup));
      check(label + ': original help descriptions remain', await signup.locator('[name=password]').getAttribute('aria-describedby') === 'pw-help' && await signup.locator('[name=nickname]').getAttribute('aria-describedby') === 'nick-help');
      // Cancel one valid native submission after the app's handler, so the
      // processing state is observable without a timing-dependent network pause.
      const processing = await signup.evaluate(form => {
        form.addEventListener('submit', event => event.preventDefault(), { once: true });
        form.requestSubmit();
        return { disabled: form.querySelector('button').disabled, busy: form.getAttribute('aria-busy'), message: form.querySelector('.form-status')?.textContent };
      });
      check(label + ': processing summary and duplicate prevention still work', processing.disabled && processing.busy === 'true' && processing.message.includes('요청을 처리'));
      await page.reload({ waitUntil: 'networkidle' });
      await signup.locator('[name=email]').fill('ui-qa-flow-' + width + '-' + Date.now() + '@example.test');
      await signup.locator('[name=nickname]').fill('T-UI');
      await signup.locator('[name=password]').fill('ui-qa-fictional-password');
      await signup.locator('button').click();
      await page.waitForURL(base + '/consent');
      await page.waitForLoadState('networkidle');
      const consent = page.locator('#consent-form');
      await consent.locator('button').click();
      check(label + ': consent without field wrappers retains form error', await consent.locator('.form-status').isVisible() && (await consent.locator('.form-status').innerText()).includes('필수 동의'));
      await consent.locator('button').click();
      check(label + ': consent summary is reused once', await consent.locator('.form-status').count() === 1 && await consent.locator('.field-error').count() === 0);
      await page.locator('#consent-all').check();
      await consent.locator('button').click();
      await page.waitForURL(base + '/onboarding');
      check(label + ': valid signup and consent still progress', page.url().endsWith('/onboarding'));
      await context.request.post(base + '/demo');
      await page.goto(base + '/settings', { waitUntil: 'networkidle' });
      const profile = page.locator('#profile-form');
      const originalHint = await profile.locator('.form-status').innerText();
      await profile.locator('[name=age]').fill('');
      await profile.locator('button[type=submit]').click();
      check(label + ': settings gets inline error and keeps its original hint', (await visibleErrors(profile)).length === 1 && await profile.locator('.form-status').innerText() === originalHint);
      check(label + ': no JavaScript errors', errors.length === 0, errors);
      await context.close();
    }
  } catch (error) { check('suite completed', false, error.stack); }
  finally {
    await browser.close();
    const result = { passed: checks.filter(c => c.pass).length, failed: checks.filter(c => !c.pass).length, checks };
    if (process.env.UI_QA_RESULT) fs.writeFileSync(process.env.UI_QA_RESULT, JSON.stringify(result, null, 2));
    console.log(JSON.stringify({ passed: result.passed, failed: result.failed }));
    if (result.failed) process.exitCode = 1;
  }
})();
