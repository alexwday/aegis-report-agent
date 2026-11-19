#!/usr/bin/env node
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const origin = new URL(process.env.AEGIS_UI_URL || 'http://127.0.0.1:8000');
assert(['127.0.0.1', 'localhost'].includes(origin.hostname), 'Use the loopback fixture app.');
const outputDir = path.resolve(__dirname, '../docs/ui/screenshots');
const capture = process.argv.includes('--screenshots');
const example = 'Build a report comparing Net Income for SYN1-CA and SYN2-CA over the last four quarters';
const errors = [];

async function screen(page, width, name, callouts = []) {
  if (!capture) return;
  await page.evaluate(callouts => {
    window.scrollTo(0, 0);
    for (const [letter, selector] of callouts) {
      const item = document.querySelector(selector);
      if (!item) continue;
      const tag = document.createElement('span');
      tag.className = 'screenshot-callout';
      tag.textContent = letter;
      tag.setAttribute('aria-hidden', 'true');
      Object.assign(tag.style, { position: 'absolute', display: 'grid', placeItems: 'center', width: '25px', height: '25px',
        border: '2px solid white', borderRadius: '50%', background: '#4235aa', color: 'white', font: 'bold 13px system-ui', zIndex: '30',
        pointerEvents: 'none' });
      const box = item.getBoundingClientRect();
      const dialog = item.closest('dialog[open]');
      if (dialog) tag.style.position = 'fixed';
      tag.style.top = Math.max(0, Math.round(box.top + (dialog ? 0 : window.scrollY) - 10)) + 'px';
      tag.style.left = Math.max(0, Math.round(box.left + (dialog ? 0 : window.scrollX) - 18)) + 'px';
      (dialog || document.body).append(tag);
    }
  }, callouts);
  try { await page.screenshot({ path: path.join(outputDir, width + '-' + name + '.png'), fullPage: true, animations: 'disabled' }); }
  finally { await page.locator('.screenshot-callout').evaluateAll(items => items.forEach(item => item.remove())); }
}

function watch(page) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.url().startsWith('http') && new URL(request.url()).origin !== origin.origin) errors.push('Cross-origin request: ' + request.url());
  });
  page.setDefaultTimeout(12000);
}

const exact = { exact: true };
const click = (page, name) => page.getByRole('button', { name, ...exact }).click();
const nav = (page, name) => page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name, ...exact }).click();
const heading = (page, name) => page.getByRole('heading', { name, ...exact }).waitFor();
const text = (page, content) => page.getByText(content, exact).first().waitFor();
const notice = (page, content) => page.locator('#notice').filter({ hasText: content }).waitFor();
async function chooseTemplate(page, title) {
  await click(page.getByRole('article', { name: 'Quarterly earnings', ...exact }), 'Use template');
  await page.getByRole('dialog').getByLabel('Report name').fill(title);
  await click(page, 'Create draft');
  await heading(page, title);
}

async function save(page, note) {
  await click(page, 'Save report');
  await page.getByLabel('Version note (optional)').fill(note);
  await click(page, 'Save version');
  await notice(page, /Version \d+ saved/);
}

async function workflow(browser, width, viewport, identity) {
  const context = await browser.newContext({ viewport, extraHTTPHeaders: { 'X-Aegis-Local-Identity': identity }, acceptDownloads: true });
  const page = await context.newPage();
  watch(page);
  const shot = (name, markers) => screen(page, width, name, markers);
  const suffix = Date.now().toString(36).toUpperCase();
  const report = 'Quarterly earnings brief';
  const second = 'Chat report draft';
  try {
    const existing = await (await context.request.get(new URL('/v1/reports', origin).href)).json();
    for (const report of existing.filter(item => item.title === 'Quarterly earnings brief')) {
      await context.request.post(new URL('/v1/reports/' + report.id + '/archive', origin).href);
    }
    await page.goto(origin.href);
    await heading(page, 'Reports');
    await shot('reports', [['A', '.hero-form'], ['B', '.gallery'], ['C', '.section-head:last-of-type']]);
    await nav(page, 'Templates');
    await heading(page, 'No personal templates yet');
    await shot('templates', [['A', '.gallery'], ['B', '.empty']]);
    await click(page.getByRole('article', { name: 'Quarterly earnings', ...exact }), 'Use template');
    await page.getByRole('dialog').getByLabel('Report name').fill(report);
    await shot('template-start', [['A', 'dialog form']]);
    await click(page, 'Create draft');
    await heading(page, report);
    await shot('workspace-draft', [['A', '.chat'], ['B', '.report-section'], ['C', '.report-actions']]);
    await click(page, 'Preview report');
    await notice(page, 'Report preview is ready.');
    await shot('workspace-preview', [['A', '.table-wrap'], ['B', '.evidence-link']]);
    await page.getByRole('button', { name: /View evidence for Fixture Bank One/ }).first().click();
    await heading(page, 'Source evidence');
    await text(page, 'Page or sheet');
    assert.match(await page.locator('.drawer dd').nth(1).textContent(), /FY2090 Q2/);
    await shot('evidence', [['A', '.drawer dl'], ['B', '.drawer .claim']]);
    await page.keyboard.press('Escape');
    await save(page, 'Initial earnings review');
    await click(page, 'Version history');
    await text(page, 'Initial earnings review');
    await shot('versions', [['A', '.version-card']]);
    await click(page, 'Close panel');
    await click(page, 'Edit section');
    const drawer = page.getByRole('complementary', { name: 'Section settings' });
    await drawer.getByLabel('Time scope', exact).selectOption('trailing_quarters');
    await drawer.getByLabel('Number of periods').fill('4');
    await drawer.getByLabel('Fixture Bank Two').check();
    await shot('section-settings', [['A', '.drawer fieldset'], ['B', '.drawer form label.field']]);
    await click(page, 'Apply section settings');
    await notice(page, 'Section settings applied.');
    await click(page, 'Preview changes');
    await heading(page, 'Changes from saved version');
    await page.locator('.diff').getByText('+ Added figure', exact).first().waitFor();
    assert.equal(await page.locator('.trend canvas').count(), 1);
    const peers = page.getByText('Peer comparison · Net Income · FY2090 Q2', exact).first();
    await peers.click();
    await shot('comparison', [['A', '.diff'], ['B', '.trend']]);
    await save(page, 'Added two-bank history');
    await click(page, 'Version history');
    await click(page, 'What changed');
    await page.getByRole('complementary', { name: 'Version history', exact: true }).getByText(/Updated banks, time scope/).waitFor();
    await shot('version-changes');
    await click(page, 'Close panel');
    await page.getByLabel('Quarter', exact).selectOption('3');
    await click(page, 'Preview report');
    await notice(page, 'Report preview is ready.');
    await text(page, 'Waiting for required data');
    await page.getByText('Source availability', exact).click();
    await shot('partial');
    await page.getByLabel('Quarter', exact).selectOption('2');
    await click(page, 'Schedule refresh');
    const schedule = page.getByRole('dialog');
    await schedule.getByLabel('Saved version to use').selectOption('2');
    await schedule.getByLabel('When a source is pending').selectOption('provisional');
    await schedule.getByLabel('Hours before provisional output').fill('0.001');
    await shot('schedule-settings', [['A', 'dialog form']]);
    await click(page, 'Save schedule');
    await notice(page, 'Schedule saved.');
    await nav(page, 'Schedules and status');
    const panel = page.getByRole('article', { name: report, exact: true });
    await panel.waitFor();
    for (let retry = 0; retry < 40 && !(await panel.getByText('Published', exact).first().isVisible()
      && await panel.getByText('Pending banks and sources', exact).first().isVisible()); retry++) {
      await page.waitForTimeout(350);
      await click(page, 'Refresh status');
      await notice(page, 'Schedule status refreshed.');
    }
    await panel.getByText('Published', exact).first().waitFor();
    await panel.getByText('Pending banks and sources', exact).first().click();
    await panel.getByText(/Fixture Bank Two · Benchmarking figures · FY2090 Q3/).first().waitFor();
    await shot('schedules', [['A', '.schedule-card .period-card'], ['B', '.schedule-card details']]);
    for (let retry = 0; retry < 35 && !await panel.getByText('Provisional', exact).first().isVisible(); retry++) {
      await page.waitForTimeout(300);
      await click(page, 'Refresh status');
      await notice(page, 'Schedule status refreshed.');
    }
    await panel.getByText('Provisional', exact).first().waitFor();
    await panel.getByText('Download provisional output', exact).first().click();
    await shot('provisional', [['A', '.schedule-card .pill.warn']]);
    const provisionalEvent = page.waitForEvent('download');
    await click(panel.getByText('Download provisional output', exact).first().locator('..'), 'JSON');
    assert.equal((await provisionalEvent).suggestedFilename(), 'provisional-quarterly-report.json');
    await panel.getByText('Download output', exact).first().click();
    const event = page.waitForEvent('download');
    await click(panel.getByText('Download output', exact).first().locator('..'), 'HTML');
    assert.equal((await event).suggestedFilename(), 'quarterly-report.html');
    const pdfEvent = page.waitForEvent('download');
    await click(panel.getByText('Download output', exact).first().locator('..'), 'PDF');
    assert.equal((await pdfEvent).suggestedFilename(), 'quarterly-report.pdf');
    const jsonEvent = page.waitForEvent('download');
    await click(panel.getByText('Download output', exact).first().locator('..'), 'JSON');
    assert.equal((await jsonEvent).suggestedFilename(), 'quarterly-report.json');
    await nav(page, 'Reports');
    await heading(page, 'Recent reports');
    await shot('reports-populated');
    await page.getByLabel('Describe the report you want').fill(example);
    await click(page, 'Start with chat');
    await heading(page, second);
    await heading(page, 'Proposed changes');
    await shot('chat-proposal', [['A', '.proposal'], ['B', '.report-section.highlight']]);
    await click(page, 'Accept');
    await notice(page, 'Proposal applied to the draft.');
    await text(page, 'Fixture Bank Two');
    await click(page, 'Preview report');
    await notice(page, 'Report preview is ready.');
    await page.locator('.trend').waitFor();
    await shot('chat-report', [['A', '.report-section .trend'], ['B', '.chat .proposal']]);
    await page.getByLabel('Message Aegis').fill('Switch Net income to staged mode');
    await click(page, 'Send message');
    await heading(page, 'Proposed changes');
    await click(page, 'Reject');
    await heading(page, 'Proposal rejected');
    await click(page, 'Duplicate');
    await notice(page, 'Draft updated.');
    await page.getByLabel('Message Aegis').fill('Remove the Net income section.');
    await click(page, 'Send message');
    await heading(page, 'Proposed changes');
    await click(page, 'Accept');
    await heading(page, 'Apply a removal?');
    await shot('destructive-confirmation', [['A', 'dialog .danger']]);
    await click(page, 'Cancel');
    await click(page, 'Reject');
    await page.getByRole('heading', { name: 'Proposal rejected', exact: true }).nth(1).waitFor();
    await page.route('**/turns/*/events', request => request.abort(), { times: 1 });
    await page.getByLabel('Message Aegis').fill('Switch Net income to staged mode');
    await click(page, 'Send message');
    await page.getByRole('button', { name: 'Reconnect', exact: true }).waitFor();
    await shot('chat-reconnect', [['A', '#chat-progress']]);
    await click(page, 'Reconnect');
    await heading(page, 'Proposed changes');
    await click(page, 'Edit');
    await heading(page, 'Edit proposed section');
    await click(page, 'Apply section settings');
    await notice(page, 'Section settings applied.');
    await click(page, 'Gather evidence');
    await notice(page, 'Evidence is ready to review.');
    await shot('gathered', [['A', '.canvas .notice'], ['B', '.canvas .table-wrap']]);
    await nav(page, 'Help');
    await heading(page, 'Check a source');
    await click(page, 'Check availability');
    await text(page, 'Source available');
    await shot('help', [['A', '.help-grid'], ['B', '.help-grid + .card']]);
    await nav(page, 'Reports');
    await heading(page, 'Recent reports');
    await chooseTemplate(page, 'Recovery exercise · ' + suffix);
    await stateChecks(page, shot);
    console.log(width + ': 5 reviewer workflows, reject and destructive confirmation, exports, recovery and accessibility smoke passed');
  } finally {
    await context.close();
  }
}

async function stateChecks(page, shot) {
  for (const [code, status, message, name] of [
    ['stale_draft_revision', 409, /draft changed/i, 'conflict'],
    ['expired_session', 401, /session has expired/i, 'expired'],
    ['section_limit', 422, /up to six sections/i, 'limit'],
    ['database_unavailable', 503, /temporarily unavailable/i, 'error'],
  ]) {
    const route = '**/v1/drafts/*/previews';
    await page.route(route, request => request.fulfill({ status, json: { detail: code } }));
    await click(page, 'Preview report');
    await page.locator('#error').filter({ hasText: message }).waitFor();
    if (status === 409) await page.getByRole('button', { name: 'Reload draft' }).waitFor();
    if (status === 401) await page.getByRole('button', { name: 'Reload workspace' }).waitFor();
    await shot(name);
    await page.unroute(route);
  }
  const route = '**/v1/drafts/*/previews';
  let release;
  const until = new Promise(resolve => { release = resolve; });
  await page.route(route, async request => { await until; await request.continue(); });
  await click(page, 'Preview report');
  await page.locator('.canvas .loading').waitFor();
  await shot('loading');
  release();
  await notice(page, 'Report preview is ready.');
  await page.unroute(route);
  await page.getByRole('combobox', { name: 'Quarter', exact: true }).selectOption('3');
  await click(page, 'Edit section');
  await page.getByRole('combobox', { name: 'Source type', exact: true }).selectOption('rts');
  await page.getByLabel('Search terms, comma-separated').fill('unmatched volcanic geology');
  await click(page, 'Apply section settings');
  await notice(page, 'Section settings applied.');
  await click(page, 'Preview report');
  await notice(page, 'Report preview is ready.');
  await text(page, 'No matching evidence');
  await page.getByText('Source availability', exact).click();
  await shot('no-match', [['A', '.report-section .pill.warn']]);
  await nav(page, 'Reports');
  await heading(page, 'Recent reports');
  await page.route('**/v1/reports?*', request => request.fulfill({ json: [] }));
  await page.reload();
  await heading(page, 'No saved reports yet');
  await shot('empty');
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
  if (capture) await fs.mkdir(outputDir, { recursive: true });
  try {
    const contextResponse = await fetch(new URL('/console/context', origin));
    assert.equal((await contextResponse.json()).source_mode, 'fixture', 'Use only a seeded fixture stack.');
    for (const [name, viewport, identity] of [
      ['desktop', { width: 1440, height: 1000 }, 'fixture-analyst'],
      ['tablet', { width: 1024, height: 900 }, 'fixture-reviewer'],
    ]) {
      await workflow(browser, name, viewport, identity);
    }
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
    watch(page);
    await page.goto(origin.href);
    await heading(page, 'Reports');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Skip to workspace');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'main');
    await nav(page, 'Templates');
    await heading(page, 'Templates');
    await chooseTemplate(page, 'Phone layout');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await click(page, 'Edit section');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Edit section');
    assert.deepEqual(errors, []);
    console.log('phone: no horizontal overflow, skip link, reduced motion and keyboard drawer focus passed; no runtime cross-origin requests');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
