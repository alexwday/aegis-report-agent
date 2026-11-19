import { api, download, loadWording, wordingFor } from './api.js';
import { bankLabel, button, card, check, confirm, disclosure, el, field, fiscal, group, initialPeriod, input, label, link, localDate,
  meta, paragraphs, periodFields, pill, promptForm, scopeName, select, titleRow } from './components.js';
import { Workspace } from './workspace.js';

const names = { reports: 'Reports', templates: 'Templates', schedules: 'Schedules and status', help: 'Help', workspace: 'Report workspace' };
const example = 'Build a report comparing Net Income for SYN1-CA and SYN2-CA over the last four quarters';
const main = document.querySelector('#main');
const status = document.querySelector('#notice');
const alert = document.querySelector('#error');

const app = {
  view: 'reports', banks: [], templates: [], reports: [], schedules: [], fixture: true, archived: false, loading: true,

  async boot() {
    try {
      const [, context, banks, templates] = await Promise.all([loadWording(), api('/console/context'), api('/v1/catalog/banks'), api('/v1/templates')]);
      this.fixture = context.source_mode === 'fixture';
      this.banks = banks;
      this.templates = templates;
      document.querySelector('#data-label').textContent = this.fixture ? 'Local demo data' : 'Read-only source connection';
      if (location.hash === '#workspace') await this.recoverWorkspace();
      await this.navigate();
    } catch (error) {
      this.loading = false;
      this.bootError = error;
      this.fail(error);
      this.render();
    }
  },

  async navigate() {
    const requested = location.hash.slice(1).split('/')[0];
    if (requested === 'main') return;
    const view = Object.hasOwn(names, requested) && (requested !== 'workspace' || this.workspace) ? requested : 'reports';
    const changed = this.view !== view;
    this.view = view;
    this.bootError = null;
    this.loading = view !== 'workspace' && view !== 'help';
    this.render(changed ? 'main' : undefined);
    try {
      if (view === 'reports' || view === 'schedules') await this.readReports();
      if (view === 'templates') this.templates = await api('/v1/templates');
    } catch (error) { this.bootError = error; this.fail(error); }
    finally { this.loading = false; this.render(); }
  },

  async attempt(action) {
    this.clearNotice();
    try { return await action(); }
    catch (error) { this.fail(error); return undefined; }
  },

  clearNotice() { status.hidden = alert.hidden = true; alert.replaceChildren(); },
  notify(message) { this.clearNotice(); status.textContent = message; status.hidden = false; },
  fail(error) {
    status.hidden = true;
    alert.hidden = false;
    alert.replaceChildren(document.createTextNode(error.message));
    if (error.status === 401) alert.append(' ', button('Reload workspace', () => location.reload(), 'small'));
    if (error.status === 409 && this.view === 'workspace' && this.workspace) alert.append(' ', button('Reload draft', () => this.attempt(async () => {
      await this.workspace.reload(); this.workspace.refresh(); this.notify('Draft refreshed.');
    }), 'small'), this.workspace.draft.report_id && button('Open latest saved version', () => this.attempt(async () => {
      const report = await api(this.workspace.reportPath);
      await this.openReport(report);
    }), 'small') || '');
  },

  render(focus) {
    document.title = (this.view === 'workspace' ? this.workspace.draft.spec.title : names[this.view]) + ' · Aegis';
    document.querySelector('#breadcrumbs').textContent = this.view === 'workspace' ? 'Reports / Workspace' : names[this.view];
    document.querySelector('#top-actions').replaceChildren(this.view === 'workspace'
      ? link('All reports', '#reports', 'small') : pill(this.fixture ? 'Demo data' : 'Read-only sources', 'neutral'));
    for (const item of document.querySelectorAll('#navigation a')) {
      if (item.dataset.view === this.view || item.dataset.view === 'reports' && this.view === 'workspace') item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    }
    main.replaceChildren(this.loading ? el('div', { class: 'loading card', role: 'status', 'aria-busy': 'true' }, 'Loading your workspace…')
      : this.bootError ? card(el('h1', {}, 'Workspace unavailable'), el('p', {}, this.bootError.message), button('Try again', () => this.boot(), 'primary'))
        : this.view === 'workspace' ? this.workspace.render() : this[this.view + 'Page']());
    if (focus) (document.getElementById(focus) || [...main.querySelectorAll('[data-focus]')].find(item => item.dataset.focus === focus))?.focus({ preventScroll: true });
  },

  async readReports() {
    const forSchedule = this.view === 'schedules';
    const archived = !forSchedule && this.archived;
    const reports = await api('/v1/reports?archived=' + archived);
    const schedules = archived ? [] : (await Promise.all(reports.map(async report => {
      const path = '/v1/reports/' + report.id + '/schedule';
      try {
        const schedule = await api(path);
        const [periods, runs] = await Promise.all([forSchedule || schedule.enabled ? api(path + '/periods') : [], forSchedule ? api(path + '/runs') : []]);
        return { report, schedule, periods, runs };
      } catch (error) {
        if (error.code === 'schedule_not_found') return { report, schedule: null, periods: [], runs: [] };
        throw error;
      }
    })));
    this.reports = reports;
    this.schedules = schedules;
  },

  banksSelect(extras = [], initial = this.banks[0]?.symbol) {
    return select([...extras, ...this.banks.map(bank => [bank.symbol, bank.name])], initial);
  },

  reportsPage() {
    const bank = this.banksSelect();
    const description = el('textarea', { rows: 3, required: true, maxlength: 2000, placeholder: 'Compare net income for two banks over the last four quarters…' });
    const form = el('form', { class: 'hero-form stack', onsubmit: event => {
      event.preventDefault();
      const submit = event.currentTarget.querySelector('[type="submit"]');
      submit.disabled = true;
      this.attempt(async () => {
        const draft = await api('/v1/drafts', 'POST', { bank: bank.value, title: 'Chat report draft' });
        const workspace = this.startWorkspace(draft);
        workspace.chatInput = description.value;
        await workspace.send();
      }).finally(() => { submit.disabled = false; });
    } }, field('Describe the report you want', description), el('div', { class: 'between' },
      el('div', { class: 'hero-bank' }, field('Starting bank', bank)), el('button', { class: 'btn primary', type: 'submit' }, 'Start with chat')),
    this.fixture && button('Try an example', () => { description.value = example; description.focus(); }, 'quiet small'));
    const exampleDoc = el('div', { class: 'hero-example' }, el('div', { class: 'between' }, pill('Template preview'), meta('Quarterly earnings')),
      el('h3', {}, 'Earnings brief'), el('div', {}, [['Section', 'Net income'], ['Fiscal period', 'Latest quarter'], ['Source', 'Benchmarking figures']].map(([title, value]) =>
        el('div', { class: 'sample-row' }, title, meta(value)))), meta('Select a figure to open its source evidence.'));
    return el('div', {}, el('h1', {}, 'Reports'), el('section', { class: 'hero' }, paragraphs(el('h2', {}, 'Build your next quarterly report'),
      el('p', { class: 'muted' }, 'Bring reported figures, peer comparisons and cited findings into one report.'), form), exampleDoc),
    titleRow('Start with a template', 'Choose a starting point for your analysis.', link('All templates', '#templates', 'small')),
    this.gallery(this.templates.filter(template => template.kind === 'system')), titleRow(this.archived ? 'Archived reports' : 'Recent reports', '',
      button(this.archived ? 'Active reports' : 'Archived reports', () => { this.archived = !this.archived; this.navigate(); }, 'small')),
    this.reports.length ? el('ul', { class: 'list' }, this.reports.map(report => this.reportItem(report))) : card(el('h3', {}, this.archived ? 'No archived reports' : 'No saved reports yet'),
      el('p', {}, this.archived ? 'Archived reports appear here. You can restore them at any time.' : 'Save your first draft to see its version and refresh status here.')));
  },

  templatesPage() {
    const personal = this.templates.filter(item => item.kind === 'personal');
    return paragraphs(el('h1', {}, 'Templates'), el('p', { class: 'muted' }, 'Preview the sections, choose a bank and make the report your own.'),
      titleRow('Standard templates'), this.gallery(this.templates.filter(item => item.kind === 'system')),
      titleRow('Your templates'), personal.length ? this.gallery(personal) : card(el('h3', {}, 'No personal templates yet'),
        el('p', {}, 'Use the menu next to a saved report to create a reusable template.')));
  },

  gallery(templates) {
    const marks = { 'quarterly-earnings': '▤', 'credit-watch': '◉', 'margin-and-capital': '▥' };
    return el('div', { class: 'gallery' }, templates.map(template => el('article', { class: 'template card', 'aria-label': template.title },
      el('span', { class: 'template-mark', 'aria-hidden': 'true' }, marks[template.id] || '▧'),
      el('div', {}, el('h3', {}, template.title), el('p', { class: 'muted' }, template.description || 'Your saved report layout.')),
      el('ul', {}, template.section_titles.map(title => el('li', {}, title))), button('Use template', () => this.useTemplate(template), 'small'))));
  },

  useTemplate(template) {
    const personal = template.kind === 'personal';
    const bank = personal ? this.banksSelect([['', 'Keep original banks']], '') : this.banksSelect();
    const title = input(template.title, { required: true, maxlength: 120 });
    promptForm('Start from ' + template.title, template.description, [field('Report name', title), field('Starting bank', bank)], 'Create draft', async () => {
      const draft = await api('/v1/drafts', 'POST', { template: template.id, bank: bank.value || null, title: title.value });
      this.startWorkspace(draft);
    });
  },

  startWorkspace(draft, period = initialPeriod(this.fixture)) {
    this.workspace = new Workspace(this, draft, period);
    this.rememberWorkspace(draft.id, period);
    this.view = 'workspace';
    this.loading = false;
    this.bootError = null;
    history.replaceState(null, '', '#workspace');
    this.render('main');
    window.scrollTo(0, 0);
    return this.workspace;
  },

  rememberWorkspace(id, period) {
    try { sessionStorage.setItem('aegis-active-draft', JSON.stringify({ id, period })); } catch { /* Optional browser state. */ }
  },

  async recoverWorkspace() {
    let previous;
    try { previous = JSON.parse(sessionStorage.getItem('aegis-active-draft')); } catch { return; }
    if (!previous?.id || !previous.period) return;
    const draft = await api('/v1/drafts/' + encodeURIComponent(previous.id)).catch(error => {
      if (error.status !== 404) throw error;
      return null;
    });
    if (draft) this.workspace = new Workspace(this, draft, previous.period);
  },

  async openReport(report) {
    const draft = await api('/v1/reports/' + report.id + '/versions/' + report.head + '/drafts', 'POST');
    this.startWorkspace(draft);
  },

  reportItem(report) {
    const found = this.schedules.find(item => item.report.id === report.id);
    const next = found?.periods.find(item => item.state === 'waiting_for_data' || item.state === 'provisional') || found?.periods[0];
    const missing = [...new Set((next?.missing || []).filter(item => item.state !== 'ready').map(item => bankLabel(this.banks, item.bank)))];
    const state = found?.schedule?.enabled ? next ? label(next.state) + ' · ' + fiscal(next.period) : 'Refresh enabled · ' + fiscal(found.schedule.next_period) : 'Manual refresh';
    return el('li', { class: 'report-row card' }, el('div', {}, el('h3', {}, report.title), meta('Version ' + report.head)),
      el('div', { class: 'report-state' }, pill(report.archived_at ? 'Archived' : state, missing.length ? 'warn' : 'neutral'), missing.length > 0 && meta('Waiting for ' + missing.join(', '))),
      group(!report.archived_at && button('Open', () => this.attempt(() => this.openReport(report)), 'small'), this.reportMenu(report)));
  },

  reportMenu(report) {
    const path = '/v1/reports/' + report.id;
    const refresh = async (action, message) => { await action(); await this.navigate(); this.notify(message); };
    const nameAction = (verb, labelText, initial, action) => {
      const title = input(initial, { required: true, maxlength: 120 });
      promptForm(verb, null, field(labelText, title), verb, () => action(title.value));
    };
    const actions = report.archived_at ? [button('Restore', () => this.attempt(() => refresh(() => api(path + '/restore', 'POST'), 'Report restored.')), 'small')] : [
      button('Rename', () => nameAction('Rename report', 'Report name', report.title, title => refresh(() => api(path, 'PATCH', { title }), 'Report renamed.')), 'small'),
      button('Duplicate', () => nameAction('Duplicate report', 'New report name', report.title.slice(0, 112) + ' (copy)', title => refresh(() => api(path + '/clone', 'POST', { title }), 'Report duplicated.')), 'small'),
      button('Make a template', () => nameAction('Save template', 'Template name', report.title, async title => {
        await api('/v1/templates', 'POST', { title, report_id: report.id, version: report.head });
        this.templates = await api('/v1/templates'); this.notify('Template saved.'); this.render();
      }), 'small'),
      button('Archive', () => confirm('Archive this report?', 'You can restore it from Archived reports.', 'Archive report',
        () => this.attempt(() => refresh(() => api(path + '/archive', 'POST'), 'Report archived.'))), 'small danger'),
    ];
    return disclosure('More', el('div', { class: 'menu' }, actions));
  },

  schedulesPage() {
    return paragraphs(el('h1', {}, 'Schedules and status'), el('div', { class: 'between' }, el('p', { class: 'muted' },
      'See what is waiting, what has been published and when Aegis will check again.'), button('Refresh status', () => this.attempt(async () => { await this.readReports(); this.render(); this.notify('Schedule status refreshed.'); }), 'small')),
    this.schedules.length ? el('div', { class: 'schedule-grid' }, this.schedules.map(item => this.scheduleCard(item))) : card(el('h2', {}, 'No report schedules yet'),
      el('p', {}, 'Save a report first, then turn on automatic quarterly refresh.'), link('Start a report', '#reports', 'small')));
  },

  scheduleCard({ report, schedule, periods, runs }) {
    return el('article', { class: 'card schedule-card stack', 'aria-label': report.title }, el('div', { class: 'between' }, el('h2', {}, report.title),
      pill(schedule?.enabled ? 'Automatic refresh on' : 'Manual refresh', 'neutral')),
    schedule && meta('Version ' + schedule.version + ' · Next quarter ' + fiscal(schedule.next_period)),
    group(button(schedule ? 'Schedule settings' : 'Schedule refresh', () => this.editSchedule(report), 'small'),
      schedule?.enabled && button('Check this quarter now', () => this.attempt(async () => {
        await api('/v1/reports/' + report.id + '/schedule/enqueue', 'POST');
        await this.readReports(); this.render(); this.notify('Quarterly check requested.');
      }), 'small quiet')),
    periods.length ? el('div', { class: 'stack' }, periods.map(period => this.periodCard(period))) : meta(schedule?.enabled ? 'Waiting for the first status check.' : 'Turn on refresh to start tracking quarters.'),
    runs.length > 0 && disclosure('Generation history', ...runs.map(run => el('div', { class: 'period-card' },
      meta(fiscal(run.period) + ' · Version ' + run.version + ' · ' + localDate(run.created_at)), pill(label(run.publication_state || run.state), run.state === 'failed' ? 'bad' : 'neutral'),
      run.error_code && meta(wordingFor(run.error_code)), run.state === 'succeeded' && this.downloadMenu(run.id, run.publication_state === 'provisional')))));
  },

  periodCard(period) {
    const missing = period.missing || [];
    const since = new Date(period.first_checked_at).getTime();
    const elapsedMinutes = Math.max(0, Math.floor((Date.now() - since) / 60000));
    const elapsed = elapsedMinutes < 1 ? 'Less than a minute' : elapsedMinutes < 60 ? elapsedMinutes + ' min' : Math.floor(elapsedMinutes / 60) + ' hr';
    return el('article', { class: 'period-card' }, el('div', { class: 'between' }, el('h3', {}, fiscal(period.period)),
      pill(label(period.state), period.state === 'failed' ? 'bad' : ['waiting_for_data', 'provisional'].includes(period.state) ? 'warn' : '')),
    el('p', { class: 'meta' }, period.message), period.last_correction.length > 0 && pill('Corrected publication'),
    el('dl', {}, el('dt', {}, 'Last check'), el('dd', {}, localDate(period.checked_at)),
      period.next_check_at && [el('dt', {}, 'Next check'), el('dd', {}, localDate(period.next_check_at))],
      missing.length > 0 && [el('dt', {}, 'Waiting for'), el('dd', {}, elapsed)],
      period.published_at && [el('dt', {}, 'Published'), el('dd', {}, localDate(period.published_at))]),
    missing.length > 0 && disclosure('Pending banks and sources', el('ul', { class: 'notes-list' }, missing.map(item => el('li', {},
      scopeName(this.banks, item) + ' · ' + (item.state === 'ready' ? 'Checking source stability' : label(item.state)))))),
    period.last_correction.length > 0 && disclosure('What was corrected', el('ul', { class: 'notes-list' }, period.last_correction.map(item =>
      el('li', {}, (item.change === 'added' ? 'Added' : item.change === 'removed' ? 'Removed' : 'Updated') + ' · ' + scopeName(this.banks, item))))),
    period.current_run_id && this.downloadMenu(period.current_run_id, period.current_kind === 'provisional'));
  },

  downloadMenu(id, provisional) {
    return disclosure(provisional ? 'Download provisional output' : 'Download output', group(...['HTML', 'PDF', 'JSON'].map(format =>
      button(format, () => this.attempt(() => download(id, format.toLowerCase(), provisional)), 'small'))));
  },

  editSchedule(report) {
    return this.attempt(async () => {
      const path = '/v1/reports/' + report.id;
      const [versions, current] = await Promise.all([api(path + '/versions'), api(path + '/schedule').catch(error => {
        if (error.code !== 'schedule_not_found') throw error;
        return null;
      })]);
      const enabled = input('', { type: 'checkbox', checked: current?.enabled ?? true });
      const version = select(versions.map(item => [item.version, 'Version ' + item.version + (item.version === versions[0].version ? ' · Latest saved' : '')]), current?.version || versions[0].version);
      const period = periodFields(current?.period || this.workspace?.period || initialPeriod(this.fixture));
      const policy = select([['wait', 'Wait for all required sources'], ['provisional', 'Allow a provisional report']], current?.provisional_after_hours != null ? 'provisional' : 'wait');
      const hours = input(current?.provisional_after_hours ?? 24, { type: 'number', min: 0, max: 2160, step: 'any', required: true, disabled: policy.value === 'wait' });
      policy.addEventListener('change', () => { hours.disabled = policy.value === 'wait'; });
      const timezone = input(current?.timezone || 'America/Toronto', { required: true, maxlength: 64 });
      promptForm('Schedule quarterly refresh', 'Pin a saved version of “' + report.title + '”. Each fiscal quarter is checked against its required sources.',
        [check('Refresh automatically each quarter', enabled), field('Saved version to use', version), period.node,
          field('When a source is pending', policy), field('Hours before provisional output', hours), disclosure('Time zone', field('Schedule time zone', timezone))],
        'Save schedule', async () => {
          await api(path + '/schedule', 'PUT', { version: Number(version.value), period: period.read(), enabled: enabled.checked,
            expected_revision: current?.revision || null, timezone: timezone.value, quiet_seconds: current?.quiet_seconds ?? null,
            correction_days: current?.correction_days ?? 14, provisional_after_hours: policy.value === 'wait' ? null : Number(hours.value) });
          if (this.view === 'schedules') { await this.readReports(); this.render(); }
          this.notify('Schedule saved. ' + (enabled.checked ? 'See Schedules and status for its next check.' : 'Automatic refresh is paused.'));
        });
    });
  },

  helpPage() {
    const topics = [
      ['Start a report', 'Write a description on Reports or choose a template. A draft is a working copy. Save it to create a version you can reopen.'],
      ['Review proposed changes', 'Ask Aegis to edit the draft. Accept applies a proposal, Reject dismisses it, and Edit opens section settings. A removal asks you to confirm.'],
      ['Check your figures', 'Preview the report, then choose View evidence next to a figure or claim. The drawer gives the source, location, excerpt and latest stability check.'],
      ['Read publication status', 'A provisional output can be published with required sources pending. The schedule records corrections and later complete outputs.'],
      ['Understand fiscal periods', 'Fiscal labels come from the source. For banks with the verified November-to-October calendar, the schedule opens after the quarter ends. The bank’s earnings release can occur later.'],
      ['Use the keyboard', 'Tab to a control and press Enter or Space. Move up and Move down reorder a section. Escape closes a panel or dialog. The source tables can be scrolled with the keyboard.'],
    ];
    return paragraphs(el('h1', {}, 'Help'), el('p', { class: 'muted' }, 'Find your way around the quarterly reporting workspace.'),
      el('div', { class: 'help-grid' }, topics.map(([title, message]) => el('article', { class: 'card' }, el('h2', {}, title), el('p', {}, message)))),
      this.probeCard(), card(el('h2', {}, 'Developer tools'), el('p', {}, 'Inspect raw requests, evidence identifiers and source diagnostics in the local console.'), link('Open Developer tools', '/console', 'small')));
  },

  probeCard() {
    const bank = this.banksSelect();
    const source = select(['benchmarking', 'transcripts', 'investor_presentation', 'rts', 'event_transcripts', 'supplementary_financials', 'pillar3'].map(key => [key, label(key)]), 'benchmarking');
    const metric = input('Net Income');
    const period = periodFields(initialPeriod(this.fixture));
    const result = el('p', { role: 'status', class: 'meta' });
    return card(el('h2', {}, 'Check a source'), el('form', { class: 'stack', onsubmit: event => {
      event.preventDefault();
      this.attempt(async () => {
        const availability = await api('/v1/sources/' + source.value + '/probe', 'POST', {
          bank: bank.value, period: period.read(), metric: source.value === 'benchmarking' ? metric.value : null,
        });
        result.textContent = label(availability.state) + (availability.reason ? ' · ' + wordingFor(availability.reason) : '');
      });
    } }, el('div', { class: 'grid-2' }, field('Bank', bank), field('Source', source), field('Metric for benchmarking', metric), period.node),
    el('button', { type: 'submit', class: 'btn' }, 'Check availability'), result));
  },
};

window.addEventListener('hashchange', () => { app.clearNotice(); app.navigate(); });
app.boot();
