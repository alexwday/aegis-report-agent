export const textOptions = {
  benchmarking: 'Benchmarking figures', transcripts: 'Earnings call transcript',
  investor_presentation: 'Investor presentation', rts: 'Report to shareholders',
  event_transcripts: 'Event transcript', supplementary_financials: 'Supplementary financials', pillar3: 'Pillar 3 disclosures',
  one_step: 'One step', staged: 'Gather evidence first', table: 'Table', table_with_note: 'Table with note', themes: 'Cited highlights',
  ready: 'Source available', incomplete: 'Waiting for data', absent: 'Source not available yet', unknown: 'Source unavailable',
  waiting_for_data: 'Waiting for data', ready_to_run: 'Ready', running: 'In progress', published: 'Published',
  provisional: 'Provisional', failed: 'Failed', superseded: 'Superseded', queued: 'Queued', waiting: 'Waiting for data', succeeded: 'Ready',
  higher_is_better: 'Higher is better', lower_is_better: 'Lower is better', highest_to_lowest: 'Highest to lowest',
};
export const label = value => textOptions[value] || 'Unspecified';
export const fiscal = period => period ? 'FY' + period.year + ' Q' + period.quarter : 'Unspecified period';
export const localDate = value => value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
export const initialPeriod = fixture => fixture ? { year: 2090, quarter: 2 } : (() => {
  const date = new Date();
  const month = date.getMonth();
  return { year: date.getFullYear() - Number(month === 0), quarter: month === 0 ? 4 : Math.ceil(month / 3) };
})();

export function el(tag, props = {}, ...children) {
  const item = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (value == null) continue;
    if (name === 'class') item.className = value;
    else if (name.startsWith('on')) item.addEventListener(name.slice(2), value);
    else if (name.startsWith('aria-') || name.startsWith('data-') || !(name in item)) item.setAttribute(name, value);
    else item[name] = value;
  }
  for (const child of children.flat(Infinity)) {
    if (child != null && child !== false) item.append(child instanceof Node ? child : String(child));
  }
  return item;
}

export function button(title, onClick, variant = '', props = {}) {
  return el('button', { class: 'btn ' + variant, type: 'button', onclick: onClick, ...props }, title);
}
export const link = (title, href, variant = '') => el('a', { href, class: 'btn ' + variant }, title);
let controlSequence = 0;
export function field(title, control) {
  const labelId = 'field-label-' + ++controlSequence;
  control.setAttribute('aria-labelledby', labelId);
  return el('label', { class: 'field' }, el('span', { id: labelId }, title), control);
}
export const input = (value = '', props = {}) => el('input', { value, ...props });
export const pill = (title, variant = '') => el('span', { class: 'pill ' + variant }, title);
export const group = (...children) => el('div', { class: 'actions' }, children);
export const card = (...children) => el('div', { class: 'card stack empty' }, children);
export const meta = text => el('p', { class: 'meta' }, text);
export const paragraphs = (...children) => el('div', { class: 'stack' }, children);
export const titleRow = (title, description, aside) => el('div', { class: 'section-head' },
  el('div', {}, el('h2', {}, title), description && el('p', { class: 'muted' }, description)), aside);
export const check = (title, input) => el('label', { class: 'check' }, input, title);

export function select(options, value, props = {}) {
  const control = el('select', props, options.map(([key, name]) => el('option', { value: key }, name)));
  if (value != null) control.value = String(value);
  return control;
}

export function periodFields(period, onChange = () => {}) {
  const year = input(period.year, { type: 'number', min: 1900, max: 2200, required: true });
  const quarter = select([1, 2, 3, 4].map(value => [value, 'Q' + value]), period.quarter);
  const read = () => ({ year: Number(year.value), quarter: Number(quarter.value) });
  for (const control of [year, quarter]) control.addEventListener('change', () => {
    if (year.checkValidity()) onChange(read());
  });
  return { read, node: el('div', { class: 'period-control' }, field('Fiscal year', year), field('Quarter', quarter)) };
}

const dialog = document.querySelector('#dialog');
export function modal(title, content, buttons) {
  document.querySelector('#dialog-content').replaceChildren(el('h2', { id: 'dialog-title' }, title), content, buttons);
  if (!dialog.open) dialog.showModal();
}
export const closeModal = () => dialog.close();
export const cancel = () => button('Cancel', closeModal, 'quiet');

export function confirm(title, message, accept, action) {
  modal(title, el('p', {}, message), group(cancel(), button(accept, () => { closeModal(); action(); }, 'danger')));
}

export function promptForm(title, description, fields, accept, action) {
  const submit = el('button', { class: 'btn primary', type: 'submit' }, accept);
  const form = el('form', { class: 'stack', onsubmit: event => {
    event.preventDefault();
    submit.disabled = true;
    Promise.resolve().then(action).then(result => { if (result !== false) closeModal(); }).catch(error => {
      form.querySelector('[role="alert"]').textContent = error.message;
    }).finally(() => { submit.disabled = false; });
  } }, description && el('p', { class: 'muted' }, description), fields,
  el('p', { class: 'form-error', role: 'alert' }), group(cancel(), submit));
  modal(title, form, el('div', { hidden: true }));
}

export function disclosure(title, ...children) {
  return el('details', {}, el('summary', {}, title), children);
}

export function table(headers, rows, name) {
  return el('div', { class: 'table-wrap', tabindex: 0, role: 'region', 'aria-label': name }, el('table', {},
    el('thead', {}, el('tr', {}, headers.map(title => el('th', { scope: 'col' }, title)))),
    el('tbody', {}, rows.map(row => el('tr', {}, row.map(cell => el('td', {}, cell)))))));
}

export const bankLabel = (banks, symbol) => banks.find(bank => bank.symbol === symbol)?.name || symbol || 'Unspecified bank';
export const currency = row => row.currency_confirmed === false ? 'Currency unconfirmed' : row.currency || 'Currency unspecified';
export const formatValue = value => value == null ? '—' : new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(Number(value));
export const scopeName = (banks, item) => [bankLabel(banks, item.bank), label(item.source), fiscal(item.period)].join(' · ');
export function scopeLabel(time) {
  const count = time.preset?.count || time.offsets?.length || 1;
  const kind = time.preset?.kind;
  const base = count === 1 ? 'Latest quarter' : kind === 'same_quarter_years' || kind === 'year_sequence'
    ? 'Same quarter, last ' + count + ' years' : 'Last ' + count + ' quarters';
  const comparison = time.compare || (time.compare_offset === -4 ? 'prior_year' : time.compare_offset === -1 ? 'prior_quarter' : null);
  return base + (comparison ? (comparison === 'prior_year' ? ' · Compared with last year' : ' · Compared with prior quarter') : '');
}
