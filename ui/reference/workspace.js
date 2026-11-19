import { api, awaitRun, download, requestKey, streamEvents, wordingFor } from './api.js';
import { bankLabel, button, card, check, confirm, currency, disclosure, el, field, fiscal, formatValue, group, input,
  label, localDate, meta, paragraphs, periodFields, pill, promptForm, scopeLabel, scopeName, select, table, titleRow } from './components.js';

const terminal = ['succeeded', 'failed', 'cancelled'];
const tools = {
  validate_draft: 'Checking report settings…', read_draft: 'Reading the draft…', resolve_scope: 'Checking banks and fiscal periods…',
  read_current_draft: 'Reading the draft…', retrieve_evidence: 'Looking up evidence…', search_evidence: 'Looking up evidence…',
  start_preview: 'Preparing a preview…', compare_saved: 'Comparing with the saved version…', explain_diff: 'Reviewing changes…',
  propose_patch: 'Preparing a proposed edit…', probe_sources: 'Checking source availability…',
};
const opText = {
  add_section: 'Add', replace_section: 'Replace', remove_section: 'Remove', reorder_sections: 'Reorder report sections',
  set_banks: 'Change the banks in', set_time: 'Change the time scope for', set_sources: 'Change the sources for',
  set_mode: 'Change the evidence workflow for', set_output_format: 'Change the format of', set_instruction: 'Change the instructions for',
};
const sourceTypes = ['benchmarking', 'transcripts', 'investor_presentation', 'rts'];

function evidenceLocation({ source, locator }) {
  const page = locator.match(/(?:page|sequence) \d+/i)?.[0];
  if (source === 'benchmarking') return locator.split(' · ').slice(0, 2).join(' · ');
  if (source === 'transcripts') return [locator.split(' · ')[0], page].filter(Boolean).join(' · ');
  return page || label(source);
}

export class Workspace {
  constructor(host, draft, period) {
    this.host = host;
    this.draft = draft;
    this.period = period;
    this.messages = [];
    this.chatInput = '';
  }

  get path() { return '/v1/drafts/' + this.draft.id; }
  get reportPath() { return '/v1/reports/' + this.draft.report_id; }
  get sections() { return this.draft.spec.sections; }
  get banks() { return this.host.banks; }
  name(symbol) { return bankLabel(this.banks, symbol); }
  refresh(focus) { if (this.host.workspace === this && this.host.view === 'workspace') this.host.render(focus); }
  attempt(action) { return this.host.attempt(action); }
  async reload() { this.draft = await api(this.path); }

  render() {
    const title = this.draft.spec.title;
    const periods = periodFields(this.period, period => {
      this.period = period;
      this.host.rememberWorkspace(this.draft.id, period);
      this.conversation = null;
      this.result = null;
      this.refresh();
    });
    const controls = el('header', { class: 'workspace-head' },
      el('div', { class: 'between' }, el('h1', {}, title), pill(this.draft.base_version ? 'Based on version ' + this.draft.base_version : 'Unsaved draft', 'neutral')),
      el('div', { class: 'row report-actions' }, periods.node, group(
        button('Preview report', () => this.attempt(() => this.preview()), '', { disabled: this.runBusy || !this.sections.length }),
        this.draft.report_id && button('Preview changes', () => this.attempt(() => this.preview({ compare: true })), '', { disabled: this.runBusy }),
        this.draft.report_id && button('Version history', () => this.attempt(() => this.history())),
        this.draft.report_id && button('Schedule refresh', () => this.host.editSchedule({ id: this.draft.report_id, title }), 'quiet'),
        button('Save report', () => this.save(), 'primary'))));
    return el('div', {}, controls, el('div', { class: 'workspace' + (this.drawer ? ' with-drawer' : '') },
      this.chat(), this.canvas(), this.drawer && this.renderDrawer()));
  }

  async send() {
    const message = this.chatInput.trim();
    if (!message || this.chatBusy) return;
    this.messages.push({ kind: 'user', message });
    this.chatInput = '';
    this.chatBusy = true;
    this.connectionLost = false;
    this.progress = 'Sending your request…';
    this.refresh('chat-input');
    this.retryText = message;
    this.pending = null;
    try {
      this.conversation ||= await api('/v1/conversations', 'POST', { draft_id: this.draft.id, period: this.period });
      const path = '/v1/conversations/' + this.conversation.id + '/turns';
      const turn = await api(path, 'POST', { message, request_key: requestKey() });
      this.pending = { path: path + '/' + turn.id, cursor: 0, turn, message: '' };
      await this.connect();
    } catch (error) {
      this.chatBusy = false;
      this.connectionLost = Boolean(this.pending);
      this.progress = this.connectionLost ? 'Connection interrupted. Reconnect to pick up where you left off.' : error.message;
      this.refresh();
    }
  }

  async connect() {
    const pending = this.pending;
    this.chatBusy = true;
    this.connectionLost = false;
    this.progress = 'Waiting for the assistant…';
    this.refresh();
    const abort = new AbortController();
    this.chatAbort = abort;
    const receive = (cursor, event, data) => {
      pending.cursor = cursor;
      if (event === 'message') pending.message = data.text;
      if (event === 'started') this.progress = 'Reviewing your request…';
      if (event === 'tool') this.progress = tools[data.name] || 'Checking report details…';
      if (event === 'preview_queued') this.progress = 'Preview requested…';
      const region = document.querySelector('#chat-progress');
      if (region && this.host.workspace === this) region.textContent = pending.message || this.progress;
    };
    try {
      do {
        await streamEvents(pending.path, pending.cursor, abort.signal, receive);
        if (this.pending !== pending) return;
        pending.turn = await api(pending.path);
      } while (!terminal.includes(pending.turn.state));
    } catch (error) {
      if (error.name === 'AbortError' || this.pending !== pending) return;
      this.connectionLost = true;
      this.chatBusy = false;
      this.progress = 'Connection interrupted. Reconnect to pick up where you left off.';
      this.refresh();
      return;
    }
    if (this.pending === pending) this.finishChat(pending);
  }

  finishChat(pending) {
    const { turn } = pending;
    this.pending = null;
    this.chatBusy = false;
    this.connectionLost = false;
    this.progress = turn.state === 'cancelled' ? 'Request cancelled. You can send another message.' : turn.state === 'failed'
      ? wordingFor(turn.error_code, 'The assistant couldn’t finish. Try the request again.') : '';
    if (turn.state === 'succeeded') {
      this.retryText = null;
      this.messages.push({ kind: 'assistant', message: turn.message, turn, path: pending.path });
    }
    this.refresh();
    if (turn.preview_id) this.attempt(() => this.watchRun(turn.preview_id));
  }

  async cancelChat() {
    const pending = this.pending;
    pending.turn = await api(pending.path + '/cancel', 'POST');
    if (this.pending !== pending) return;
    this.chatAbort?.abort();
    this.finishChat(pending);
  }

  chat() {
    const message = el('textarea', { id: 'chat-input', rows: 3, value: this.chatInput, maxlength: 2000,
      placeholder: 'Ask for an edit, comparison or source check…', oninput: event => { this.chatInput = event.target.value; } });
    const log = el('div', { class: 'chat-log', 'aria-label': 'Conversation' }, this.messages.length ? this.messages.map(item =>
      el('div', { class: 'stack' }, item.message && el('div', { class: 'chat-text ' + item.kind },
        el('small', { class: 'meta' }, item.kind === 'user' ? 'You' : 'Aegis'), el('p', {}, item.message)),
      item.turn?.proposal && this.proposal(item))) : el('p', { class: 'muted' }, 'Ask Aegis to adjust sections, explain changes or check sources. You review proposed edits before they reach the report.'));
    requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
    const examples = ['Compare with last year', 'Show me the gathered evidence first', 'What changed since the saved version?'];
    return el('aside', { class: 'chat card', 'aria-labelledby': 'chat-title' }, el('h2', { id: 'chat-title' }, 'Conversation'), log,
      el('div', { id: 'chat-progress', class: 'meta', role: 'status', 'aria-live': 'polite' }, this.progress || ''),
      this.pending && this.chatBusy && button('Cancel request', () => this.attempt(() => this.cancelChat()), 'small'),
      this.connectionLost && group(button('Reconnect', () => this.connect(), 'small'), button('Cancel request', () => this.attempt(() => this.cancelChat()), 'small')),
      !this.chatBusy && !this.connectionLost && this.retryText && button('Retry request', () => { this.chatInput = this.retryText; this.send(); }, 'small'),
      el('form', { class: 'chat-compose stack', onsubmit: event => { event.preventDefault(); this.send(); } }, field('Message Aegis', message),
        el('button', { class: 'btn primary', type: 'submit', disabled: this.chatBusy || this.connectionLost }, 'Send message'),
        el('div', { class: 'suggestions', 'aria-label': 'Suggested messages' }, examples.map(example => button(example, () => {
          message.value = this.chatInput = example;
          message.focus();
        }, 'small quiet')))));
  }

  proposal(item) {
    const { turn, path } = item;
    const operations = turn.proposal.operations;
    const deletion = operations.some(op => op.op === 'remove_section');
    const done = turn.applied_revision || turn.rejected;
    const accept = () => this.attempt(async () => {
      const result = await api(path + '/accept', 'POST', { revision: this.draft.revision });
      turn.applied_revision = result.revision;
      await this.reload();
      this.resultStale = true;
      this.host.notify('Proposal applied to the draft.');
      this.refresh('report-canvas');
    });
    return el('article', { class: 'proposal' + (!done && deletion ? ' destructive' : '') },
      el('h3', {}, turn.rejected ? 'Proposal rejected' : turn.applied_revision ? (item.edited ? 'Edited proposal applied' : 'Proposal applied') : 'Proposed changes'),
      el('ul', {}, operations.map(op => el('li', {}, this.describeOp(op)))),
      !done && group(button('Accept', () => deletion ? confirm('Apply a removal?', 'This proposal removes a section from the draft.', 'Remove and apply', accept) : accept(), deletion ? 'small danger' : 'small primary'),
        button('Reject', () => this.attempt(async () => { item.turn = await api(path + '/reject', 'POST'); this.refresh('chat-input'); }), 'small'),
        button('Edit', () => this.editProposal(item), 'small')));
  }

  describeOp(operation) {
    const section = operation.section || this.sections.find(item => item.id === operation.section_id);
    const value = operation.time ? scopeLabel(operation.time) : operation.mode ? label(operation.mode) : operation.output_format ? label(operation.output_format)
      : operation.banks ? operation.banks.map(bank => this.name(bank)).join(', ') : operation.peer_group ? 'Canada’s Big Six'
        : operation.sources ? operation.sources.map(source => label(source.source)).join(', ') : operation.instruction;
    return [opText[operation.op], section && '“' + section.title + '”'].filter(Boolean).join(' ') + (value ? ' · ' + value : '');
  }

  editProposal(item) {
    const operations = item.turn.proposal.operations;
    const id = operations.find(op => op.section || op.section_id);
    const target = id?.section || this.sections.find(section => section.id === id?.section_id) || this.sections[0];
    if (!target) { this.openEditor(null, item); return; }
    let edited = structuredClone(target);
    for (const op of operations) {
      if ((op.section?.id || op.section_id) !== edited.id) continue;
      if (op.section) edited = structuredClone(op.section);
      if (op.op === 'set_banks') Object.assign(edited, { bank: null, banks: op.banks, peer_group: op.peer_group });
      for (const key of ['time', 'sources', 'mode', 'output_format', 'instruction']) if (op[key] != null) edited[key] = op[key];
    }
    this.openEditor(edited, item);
  }

  openDrawer(title, content) {
    const active = document.activeElement;
    if (!this.drawer) this.drawerFocus = active?.getAttribute('data-focus') || 'report-canvas';
    this.drawer = { title, content };
    this.refresh('drawer-heading');
  }

  closeDrawer() { this.drawer = null; this.refresh(this.drawerFocus); }

  renderDrawer() {
    return el('aside', { class: 'drawer card', 'aria-labelledby': 'drawer-heading', onkeydown: event => {
      if (event.key === 'Escape') { event.stopPropagation(); this.closeDrawer(); }
    } }, el('div', { class: 'drawer-head' }, el('h2', { id: 'drawer-heading', tabindex: -1 }, this.drawer.title),
      button('Close panel', () => this.closeDrawer(), 'small quiet')), this.drawer.content);
  }

  canvas() {
    const highlighted = this.messages.flatMap(item => item.turn?.proposal && !item.turn.applied_revision && !item.turn.rejected
      ? item.turn.proposal.operations.flatMap(op => [op.section_id || op.section?.id, ...(op.section_ids || [])]) : []);
    const result = this.result;
    const sectionCount = this.sections.length;
    return el('section', { id: 'report-canvas', tabindex: -1, class: 'canvas card', 'aria-labelledby': 'canvas-title' },
      el('div', { class: 'between' }, el('div', {}, el('h2', { id: 'canvas-title', class: 'canvas-title' }, 'Report canvas'), meta(fiscal(this.period) + ' · ' + sectionCount + (sectionCount === 1 ? ' section' : ' sections'))),
        button('Add section', () => this.openEditor(), 'small', { 'data-focus': 'add-section' })),
      this.runBusy && el('div', { class: 'loading', role: 'status' }, this.runProgress || 'Preparing report…'),
      this.resultStale && result && el('p', { class: 'notice warning' }, 'The draft changed. Preview again to see current figures and evidence.'),
      result?.output.publication === 'provisional' && el('p', { class: 'notice warning' }, 'Provisional report · Some sources are still pending.'),
      result?.output.completion === 'gathered' && el('p', { class: 'notice' }, 'Evidence gathered. Preview the report when you’re ready to see the finished section.'),
      result?.output.diff_details && this.diff(result.output.diff_details),
      !sectionCount && card(el('h3', {}, 'Your report has no sections yet'), el('p', {}, 'Add a section or ask Aegis to suggest one.')),
      this.sections.map((section, index) => this.section(section, index, highlighted.includes(section.id))),
      this.draft.report_id && disclosure('Export saved report', meta('Downloads use the saved version for the selected fiscal period.'),
        group(...['HTML', 'PDF', 'JSON'].map(format => button('Download ' + format, () => this.attempt(() => this.exportSaved(format)), 'small')))));
  }

  section(section, index, highlighted) {
    const output = this.result?.output.sections.find(item => item.id === section.id);
    const readiness = Object.values(this.result?.output.readiness || {}).filter(item => item.section_id === section.id);
    const scopes = readiness.filter(item => item.state !== 'ready' || item.evidence_state === 'no_match');
    const status = scopes.some(item => item.required && item.state !== 'ready') ? ['Waiting for required data', 'warn']
      : scopes.some(item => item.state !== 'ready') ? ['Partial data', 'warn'] : scopes.length ? ['No matching evidence', 'warn']
        : output ? ['Ready', ''] : ['Preview to check data', 'neutral'];
    return el('article', { class: 'report-section' + (highlighted ? ' highlight' : ''), 'aria-label': section.title },
      el('div', { class: 'between' }, el('h3', {}, section.title), pill(...status)),
      highlighted && meta('Proposed edit'),
      el('div', { class: 'pills', 'aria-label': 'Banks and sources' },
        (section.peer_group ? ['Canada’s Big Six'] : (section.banks || [section.bank]).map(bank => this.name(bank))).map(bank => pill(bank, 'neutral')),
        section.sources.map(source => pill(label(source.source)))),
      el('p', { class: 'section-summary' }, [scopeLabel(section.time), label(section.mode), label(section.output_format)].join(' · ')),
      el('div', { class: 'section-controls' }, button('Edit section', () => this.openEditor(section), 'small', { 'data-focus': 'section-' + section.id }),
        section.mode === 'staged' && button('Gather evidence', () => this.attempt(() => this.preview({ section: section.id, gather: true })), 'small', { disabled: this.runBusy }),
        button('Move up', () => this.attempt(() => this.move(index, -1)), 'small quiet', { disabled: index === 0 }),
        button('Move down', () => this.attempt(() => this.move(index, 1)), 'small quiet', { disabled: index === this.sections.length - 1 }),
        button('Duplicate', () => this.attempt(() => this.operate({ op: 'add_section', section: { ...section, id: this.sectionId(), title: section.title.slice(0, 113) + ' (copy)' } })), 'small quiet'),
        button('Remove', () => confirm('Remove this section?', '“' + section.title + '” will be removed from the draft.', 'Remove section',
          () => this.attempt(() => this.operate({ op: 'remove_section', section_id: section.id }))), 'small quiet',
          { disabled: this.sections.length === 1, title: this.sections.length === 1 ? 'A report needs at least one section' : null })),
      scopes.length > 0 && disclosure('Source availability', ...scopes.map(item => meta(scopeName(this.banks, item) + ' · ' +
        (item.evidence_state === 'no_match' ? 'No matching evidence' : label(item.state)) + (item.message ? ' · ' + item.message : '')))),
      output && this.renderOutput(output, this.result.run.id));
  }

  sectionId() { return 'section-' + requestKey().slice(0, 8); }
  async move(index, offset) {
    const order = this.sections.map(section => section.id);
    const id = order[index];
    order.splice(index, 1);
    order.splice(index + offset, 0, id);
    await this.operate({ op: 'reorder_sections', section_ids: order }, 'section-' + id);
  }

  async operate(operation, focus = 'report-canvas') {
    this.draft = await api(this.path + '/operations', 'PATCH', { revision: this.draft.revision, operations: [operation] });
    this.resultStale = true;
    this.host.notify('Draft updated.');
    this.refresh(focus);
  }

  openEditor(section, proposal) {
    const draft = structuredClone(section || {
      id: this.sectionId(), title: 'New section', bank: this.sections[0]?.bank || this.sections[0]?.banks?.[0] || this.banks[0]?.symbol,
      sources: [{ source: 'benchmarking', metric: 'Net Income', segment: 'Enterprise', required: true }],
      time: {}, mode: 'one_step', output_format: 'table_with_note', instruction: 'Summarize the selected evidence.',
    });
    const title = input(draft.title, { required: true, maxlength: 120 });
    const checked = draft.banks || [draft.bank];
    const peer = input('', { type: 'checkbox', checked: Boolean(draft.peer_group) });
    const bankChecks = this.banks.map(bank => [bank, input('', { type: 'checkbox', checked: checked.includes(bank.symbol), disabled: peer.checked })]);
    peer.addEventListener('change', () => bankChecks.forEach(([, box]) => { box.disabled = peer.checked; }));
    const bankField = el('fieldset', {}, el('legend', {}, 'Banks'), check('Canada’s Big Six', peer),
      bankChecks.map(([bank, box]) => check(bank.name, box)));
    const periodKind = select([['latest', 'Latest quarter'], ['trailing_quarters', 'Last quarters'], ['same_quarter_years', 'Same quarter across years'],
      ['quarter_sequence', 'Quarters, oldest first'], ['year_sequence', 'Years, oldest first'], ...(draft.time.offsets?.length > 1 ? [['custom', 'Keep existing custom scope']] : [])], draft.time.preset?.kind || (draft.time.offsets?.length > 1 ? 'custom' : 'latest'));
    const count = input(draft.time.preset?.count || 4, { type: 'number', min: 2, max: 12, required: true, disabled: !draft.time.preset });
    const updateCount = () => {
      count.disabled = ['latest', 'custom'].includes(periodKind.value);
      count.max = ['same_quarter_years', 'year_sequence'].includes(periodKind.value) ? 6 : 12;
    };
    periodKind.addEventListener('change', updateCount);
    updateCount();
    const compare = select([['', 'No comparison'], ['prior_year', 'Compared with last year'], ['prior_quarter', 'Compared with prior quarter'],
      ...(draft.time.compare_offset != null && ![-1, -4].includes(draft.time.compare_offset) ? [['custom', 'Keep existing comparison']] : [])],
      draft.time.compare || ({ '-1': 'prior_quarter', '-4': 'prior_year' }[draft.time.compare_offset]) || (draft.time.compare_offset == null ? '' : 'custom'));
    const mode = select(['one_step', 'staged'].map(key => [key, label(key)]), draft.mode);
    const format = select(['table_with_note', 'table', 'themes'].map(key => [key, label(key)]), draft.output_format);
    const instruction = el('textarea', { value: draft.instruction, required: true, rows: 3, maxlength: 1200 });
    const entries = draft.sources.map(source => this.sourceEditor(source));
    const sources = el('div', { class: 'stack' });
    function drawSources() {
      sources.replaceChildren(...entries.map((entry, index) => el('fieldset', { class: 'stack' }, el('legend', {}, 'Source ' + (index + 1)), entry.node,
        entries.length > 1 && button('Remove source ' + (index + 1), () => { entries.splice(index, 1); drawSources(); }, 'small quiet'))),
        button('Add source', () => { entries.push(this.sourceEditor({ source: 'benchmarking', metric: 'Net Income', segment: 'Enterprise', required: false })); drawSources(); }, 'small', { disabled: entries.length >= 4 }));
    }
    drawSources = drawSources.bind(this);
    drawSources();
    const error = el('p', { role: 'alert', class: 'form-error' });
    const save = el('button', { type: 'submit', class: 'btn primary' }, 'Apply section settings');
    const form = el('form', { class: 'stack', onsubmit: async event => {
      event.preventDefault();
      error.textContent = '';
      const banks = bankChecks.filter(([, box]) => box.checked).map(([bank]) => bank.symbol);
      if (!banks.length && !peer.checked) { error.textContent = 'Choose at least one bank or the peer group.'; return; }
      const selected = entries.map(entry => entry.read());
      const kind = selected.some(item => item.source === 'transcripts') ? 'themes' : selected.some(item => item.source !== 'benchmarking') ? 'highlights' : 'benchmark';
      const time = { compare: compare.value === 'custom' ? null : compare.value || null };
      if (compare.value === 'custom') time.compare_offset = draft.time.compare_offset;
      if (periodKind.value === 'custom') time.offsets = draft.time.offsets;
      else if (periodKind.value !== 'latest') time.preset = { kind: periodKind.value, count: Number(count.value) };
      const updated = { ...draft, title: title.value, bank: null, banks: peer.checked ? null : banks, peer_group: peer.checked ? 'big-6-canadian-banks' : null,
        sources: selected, kind, time, mode: mode.value, output_format: kind === 'benchmark' ? (format.value === 'themes' ? 'table_with_note' : format.value) : 'themes',
        instruction: instruction.value };
      const exists = this.sections.some(item => item.id === draft.id);
      save.disabled = true;
      try {
        const body = { revision: this.draft.revision, operations: [{ op: exists ? 'replace_section' : 'add_section', section: updated }] };
        if (proposal) {
          const changed = await api(proposal.path + '/accept', 'POST', body);
          proposal.turn.applied_revision = changed.revision;
          proposal.edited = true;
          await this.reload();
        } else this.draft = await api(this.path + '/operations', 'PATCH', body);
        this.resultStale = true;
        this.host.notify('Section settings applied.');
        this.closeDrawer();
      } catch (requestError) {
        error.textContent = requestError.message;
      } finally { save.disabled = false; }
    } }, field('Section title', title), bankField, sources, field('Time scope', periodKind), field('Number of periods', count), field('Comparison', compare),
    field('Evidence workflow', mode), field('Format', format), meta('Transcript and document sections use cited highlights.'),
    field('Section instructions', instruction), error, save);
    this.openDrawer(proposal ? 'Edit proposed section' : section ? 'Section settings' : 'Add section',
      proposal ? paragraphs(meta('Applying these settings replaces the proposal with this section edit.'), form) : form);
  }

  sourceEditor(source) {
    const type = select(sourceTypes.map(key => [key, label(key)]), source.source);
    const metric = input(source.metric || 'Net Income', { required: true, maxlength: 120 });
    const segment = input(source.segment || 'Enterprise', { required: true, maxlength: 120 });
    const topic = input(source.topics?.join(', ') || source.topic || '', { maxlength: 350 });
    const terms = input(source.terms?.join(', ') || '', { maxlength: 650 });
    const required = input('', { type: 'checkbox', checked: source.required });
    const fields = el('div', { class: 'stack' });
    const draw = () => fields.replaceChildren(...(type.value === 'benchmarking'
      ? [field('Metric', metric), field('Business segment', segment)]
      : [field(type.value === 'transcripts' ? 'Topics, comma-separated' : 'Topic', topic), field('Search terms, comma-separated', terms)]));
    type.addEventListener('change', draw);
    draw();
    const split = value => value.split(',').map(term => term.trim()).filter(Boolean);
    return { node: paragraphs(field('Source type', type), fields, check('Required when scheduling', required)), read() {
      const settings = { source: type.value, required: required.checked };
      if (type.value === 'benchmarking') return { ...settings, metric: metric.value, segment: segment.value };
      const search = { ...settings, terms: split(terms.value), vector: source.vector || false };
      return type.value === 'transcripts' ? { ...search, topics: split(topic.value) } : { ...search, topic: topic.value.trim() || null };
    } };
  }

  async preview({ compare, section, gather } = {}) {
    const revision = this.draft.revision;
    this.runBusy = true;
    this.runProgress = compare ? 'Preparing the saved version for comparison…' : 'Preparing report…';
    this.refresh();
    try {
      const baseline = compare && await this.savedRun();
      if (compare) {
        const base = await api(this.reportPath + '/versions/' + this.draft.base_version);
        this.settingsChanges = this.versionDiff(base, this.draft.spec);
      } else this.settingsChanges = null;
      const payload = { revision, period: this.period, baseline_run_id: baseline ? baseline.run.id : null,
        section_id: section || null, stop_after: gather ? 'gather' : null };
      const reference = await api(this.path + '/previews', 'POST', payload);
      await this.watchRun(reference.id, revision);
    } finally { this.runBusy = false; this.refresh(); }
  }

  async watchRun(id, revision = this.draft.revision) {
    this.runBusy = true;
    this.refresh();
    try {
      this.result = await awaitRun(id, run => {
        const messages = { queued: 'Preview queued…', running: 'Preparing report and checking evidence…', waiting: 'Waiting for source data…' };
        this.runProgress = messages[run.state];
        const status = document.querySelector('.canvas .loading');
        if (status && this.runProgress && this.host.workspace === this) status.textContent = this.runProgress;
      });
      this.resultStale = this.draft.revision !== revision;
      this.host.notify(this.result.output.completion === 'gathered' ? 'Evidence is ready to review.' : 'Report preview is ready.');
    } finally { this.runBusy = false; this.refresh('report-canvas'); }
  }

  async savedRun() {
    const { year, quarter } = this.period;
    const required = this.draft.base_version;
    const item = await api(this.reportPath + '/runs', 'POST', { version: required, period: this.period,
      request_key: ['reference', this.draft.report_id, required, year, quarter].join('-') });
    return awaitRun(item.id);
  }

  async exportSaved(format) {
    this.host.notify('Preparing ' + format + ' download…');
    const { run, output } = await this.savedRun();
    await download(run.id, format.toLowerCase(), output.publication === 'provisional');
    this.host.notify(format + ' download started.');
  }

  save() {
    const title = input(this.draft.spec.title, { required: true, maxlength: 120 });
    const note = el('textarea', { rows: 3, maxlength: 500, placeholder: 'For example, added the quarterly peer comparison' });
    promptForm('Save report', 'A save creates a version that you can reopen from version history.', [field('Report name', title), field('Version note (optional)', note)],
      'Save version', async () => {
        if (title.value.trim() !== this.draft.spec.title) this.draft = await api(this.path + '/title', 'PATCH', { revision: this.draft.revision, title: title.value });
        const saved = await api(this.path + '/save', 'POST', { revision: this.draft.revision, note: note.value || null });
        await this.reload();
        this.host.notify('Version ' + saved.version + ' saved.');
        this.refresh('report-canvas');
      });
  }

  async history() {
    const versions = await api(this.reportPath + '/versions');
    const history = el('div', { class: 'stack' }, versions.map((version, index) => {
      const prior = versions[index + 1];
      const summary = el('div', { class: 'stack' });
      return el('article', { class: 'version-card' }, el('h3', {}, 'Version ' + version.version), meta(localDate(version.created_at)),
        version.note && el('p', {}, version.note), summary, group(prior && button('What changed', () => this.attempt(async () => {
          const [before, after] = await Promise.all([prior, version].map(item => api(this.reportPath + '/versions/' + item.version)));
          const changes = this.versionDiff(before, after);
          summary.replaceChildren(el('ul', { class: 'notes-list' }, changes.map(change => el('li', {}, change))));
        }), 'small'), button('Open as new draft', () => this.attempt(async () => {
          const opened = await api(this.reportPath + '/versions/' + version.version + '/drafts', 'POST');
          this.host.startWorkspace(opened, this.period);
          this.host.notify('Opened version ' + version.version + ' in a new draft.');
        }), 'small quiet')));
    }));
    this.openDrawer('Version history', history);
  }

  versionDiff(before, after) {
    const changes = before.title === after.title ? [] : ['Report renamed from “' + before.title + '” to “' + after.title + '”.'];
    const prior = new Map(before.sections.map((section, index) => [section.id, { section, index }]));
    const names = { title: 'title', bank: 'banks', banks: 'banks', peer_group: 'banks', sources: 'sources', time: 'time scope',
      mode: 'workflow', output_format: 'format', instruction: 'instructions' };
    after.sections.forEach((section, index) => {
      const old = prior.get(section.id);
      if (!old) { changes.push('Added “' + section.title + '”.'); return; }
      prior.delete(section.id);
      const fields = Object.keys(names).filter(key => JSON.stringify(old.section[key]) !== JSON.stringify(section[key])).map(key => names[key]);
      if (fields.length) changes.push('Updated ' + [...new Set(fields)].join(', ') + ' in “' + section.title + '”.');
      if (old.index !== index) changes.push('Moved “' + section.title + '” to position ' + (index + 1) + '.');
    });
    for (const { section } of prior.values()) changes.push('Removed “' + section.title + '”.');
    return changes.length ? changes : ['No change to the report settings.'];
  }

  citation(id, run, { period, bank, source } = {}) {
    return button('View evidence', () => this.attempt(async () => {
      const datum = await api('/v1/runs/' + run + '/evidence/' + encodeURIComponent(id) + '/detail');
      this.showEvidence(datum, datum.period || period, datum.bank || bank, source);
    }), 'evidence-link small', { 'data-focus': 'citation-' + id, 'aria-label': 'View evidence' + (bank ? ' for ' + this.name(bank) : '') + (period ? ' · ' + fiscal(period) : '') });
  }

  showEvidence(datum, period, bank, source) {
    const applicable = Object.values(this.result?.output.readiness || {})
      .filter(item => item.source === (source || datum.source) && (!bank || item.bank === bank)
        && (!period || item.period?.year === period.year && item.period?.quarter === period.quarter));
    const scope = applicable[0];
    const evidencePeriod = period || (applicable.length === 1 ? scope.period : null);
    const statuses = { stable: 'Current and stable at last check', recently_changed: 'Recently changed', unknown: 'Stability still to be verified' };
    const fields = [['Source', label(datum.source)], ['Fiscal period', fiscal(evidencePeriod)],
      ['Bank', this.name(bank || (applicable.length === 1 ? scope.bank : null))], ['Page or sheet', evidenceLocation(datum)],
      ['Data status', statuses[applicable.length === 1 ? scope.data_stability : null] || 'Stability still to be verified']];
    this.openDrawer('Source evidence', paragraphs(el('dl', {}, fields.map(([title, value]) => [el('dt', {}, title), el('dd', {}, value)])),
      el('div', { class: 'claim' }, el('h3', {}, 'Source excerpt'), el('p', {}, datum.excerpt || 'An excerpt is unavailable for this source.'))));
  }

  renderOutput(output, runId) {
    const rows = output.rows || [];
    const retrieval = output.stage_outputs.find(stage => stage.kind === 'retrieve');
    const gathered = this.result.output.completion === 'gathered' ? retrieval?.passages || [] : [];
    const figures = this.result.output.completion === 'gathered' ? retrieval?.rows || [] : rows;
    return paragraphs(figures.length > 0 && this.figures(figures, runId),
      ...(output.comparisons || []).map(item => el('p', { class: 'section-summary' },
        this.name(item.bank || rows[0]?.bank) + ' · ' + (item.metric || 'Quarterly change') + ' · ' + formatValue(item.value) +
          (item.basis === 'basis_points' ? ' bps' : item.basis === 'percent_change' ? '%' : '') + ' ',
        item.citation_ids.map(id => this.citation(id, runId, { bank: item.bank, source: 'benchmarking' })))),
      output.note && el('div', { class: 'claim' }, el('p', {}, output.note.text), this.citation(output.note.citation_id, runId)),
      ...(output.claims || []).map(claim => el('div', { class: 'claim' }, el('h4', {}, claim.topic), el('p', {}, claim.text),
        group(...claim.citations.map(cite => this.citation(cite.id, runId, { bank: claim.banks?.[0], source: cite.source }))))),
      ...gathered.map(item => el('div', { class: 'claim' }, meta(fiscal(item.period)), el('p', {}, item.excerpt),
        this.citation(item.citation.id, runId, { bank: item.bank, period: item.period, source: item.citation.source }))),
      ...(output.peers || []).map(peer => this.peers(peer, runId)));
  }

  figures(rows, runId) {
    const first = rows.find(row => row.actual != null);
    const trend = first ? rows.filter(row => row.bank === first.bank && row.metric === first.metric && row.segment === first.segment && row.actual != null) : [];
    return paragraphs(trend.length > 1 && this.chart(trend), table(['Bank / period', 'Reported figure', 'Source'], rows.map(row => [
      el('div', {}, el('strong', {}, this.name(row.bank)), meta(fiscal(row.period))),
      el('div', {}, el('strong', {}, formatValue(row.actual) + (row.unit ? ' ' + row.unit : '')), meta(row.metric + ' · ' + currency(row))),
      this.citation(row.citation.id, runId, { bank: row.bank, period: row.period, source: row.citation.source }),
    ]), 'Reported figures'));
  }

  chart(rows) {
    const points = [...rows].sort((left, right) => left.period.year - right.period.year || left.period.quarter - right.period.quarter);
    const values = points.map(row => Number(row.actual));
    const min = Math.min(...values), max = Math.max(...values);
    const canvas = el('canvas', { class: 'chart', width: 580, height: 170, 'aria-hidden': 'true' });
    const ctx = canvas.getContext('2d');
    const tokens = getComputedStyle(document.documentElement);
    ctx.strokeStyle = tokens.getPropertyValue('--line').trim();
    for (const y of [25, 62, 100, 135]) { ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(550, y); ctx.stroke(); }
    const dots = values.map((value, index) => [36 + index * 508 / (values.length - 1), 132 - 100 * (value - min) / (max - min || 1)]);
    ctx.strokeStyle = ctx.fillStyle = tokens.getPropertyValue('--accent').trim();
    ctx.lineWidth = 3;
    ctx.beginPath();
    dots.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.stroke();
    for (const [x, y] of dots) { ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill(); }
    return el('figure', { class: 'trend' }, el('figcaption', {}, points[0].metric + ' trend · ' + this.name(points[0].bank)), canvas,
      el('div', { class: 'between meta' }, fiscal(points[0].period), fiscal(points.at(-1).period)), meta('The table below contains the values for this chart.'));
  }

  peers(peer, run) {
    const rank = peer.ranks.length > 0;
    const rows = rank ? peer.ranks : peer.ordered_values;
    return disclosure('Peer comparison · ' + peer.metric + ' · ' + fiscal(peer.period), paragraphs(
      group(peer.direction && pill(label(peer.direction)), rank && pill('Rank 1 = best', 'neutral'), pill(currency(peer), peer.currency_confirmed === false ? 'warn' : 'neutral')),
      peer.reason && meta(wordingFor(peer.reason, 'Peer ranking is unavailable for this period.')),
      peer.missing_banks.length && meta('Missing banks · ' + peer.missing_banks.map(bank => this.name(bank)).join(', ')),
      rows.length > 0 && table([rank ? 'Rank / bank' : 'Bank', 'Value', 'Source'], rows.map(item => [
        (rank ? item.rank + ' · ' : '') + this.name(item.bank), formatValue(item.value) + (peer.unit ? ' ' + peer.unit : ''),
        this.citation(item.citation_id, run, { period: peer.period, bank: item.bank, source: 'benchmarking' }),
      ]), 'Peer comparison')));
  }

  diff(details) {
    const grouped = {};
    for (const entry of details.entries) grouped[entry.operation] = (grouped[entry.operation] || 0) + 1;
    const keys = { added: '+ Added', removed: '− Removed', moved: '↕ Moved', changed: '≠ Changed' };
    const summary = Object.entries(grouped).map(([operation, number]) => number + ' ' + operation).join(', ');
    return el('section', { class: 'diff', 'aria-label': 'Changes from saved version' }, el('h3', {}, 'Changes from saved version'),
      meta(summary || 'No changes to figures or claims in this preview.'), this.settingsChanges && disclosure('Report settings changes',
        el('ul', { class: 'notes-list' }, this.settingsChanges.map(change => el('li', {}, change)))), details.entries.map(entry => el('article', { class: 'change-line' },
        pill(keys[entry.operation] + ' ' + (entry.entity === 'row' ? 'figure' : entry.entity), entry.operation === 'removed' ? 'warn' : ''),
        el('div', { class: 'diff-row' }, el('div', {}, meta('Saved'), el('p', {}, this.diffText(entry.before, entry.before_index))),
          el('div', {}, meta('Preview'), el('p', {}, this.diffText(entry.after, entry.after_index)))))));
  }

  diffText(item, position) {
    if (!item) return '—';
    if (item.ranks) return [item.metric, fiscal(item.period), item.direction && label(item.direction), ...item.ranks.map(row => this.name(row.bank) + ' · rank ' + row.rank + ' · ' + formatValue(row.value)),
      ...item.ordered_values.map(row => this.name(row.bank) + ' · ' + formatValue(row.value)), item.missing_banks.length > 0 && 'Missing: ' + item.missing_banks.map(bank => this.name(bank)).join(', ')].filter(Boolean).join(' • ');
    if (item.title) return item.title + ' · Position ' + (position + 1);
    if (item.text) return item.text;
    return [item.bank && this.name(item.bank), item.period && fiscal(item.period), item.metric, formatValue(item.actual ?? item.value), item.unit].filter(Boolean).join(' · ');
  }
}
