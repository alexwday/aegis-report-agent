const wording = {};

export function wordingFor(code, fallback = 'Try again in a moment.') {
  return wording[code] || fallback;
}

export class RequestError extends Error {
  constructor(status, detail) {
    const defaults = {
      401: 'Your session has expired. Reload the workspace to reconnect.',
      404: 'This item is no longer available to you.',
      409: 'This report changed while you were editing. Open the latest version to continue.',
      422: 'Check the options you entered. Choose valid banks, sources and fiscal periods.',
      429: 'You’ve reached a limit. Wait for your current work to finish and try again.',
      503: 'The workspace is temporarily unavailable. Try again in a moment.',
    };
    super(typeof detail === 'string' ? wordingFor(detail, defaults[status]) : defaults[status] || 'Something went wrong. Try again.');
    this.status = status;
    this.code = typeof detail === 'string' ? detail : null;
  }
}

async function request(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new RequestError(503);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new RequestError(response.status, payload.detail);
  }
  return response;
}

export async function api(path, method = 'GET', body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(body);
  }
  return (await request(path, options)).json();
}

export async function loadWording() {
  Object.assign(wording, await api('/v1/reasons'));
}

export async function streamEvents(path, cursor, signal, receive) {
  const response = await request(path + '/events', { headers: { 'Last-Event-ID': String(cursor) }, signal });
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let pending = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += value;
      const frames = pending.split('\n\n');
      pending = frames.pop();
      for (const frame of frames) {
        const fields = Object.fromEntries(frame.split('\n').filter(line => /^[a-z]+: /.test(line)).map(line => {
          const offset = line.indexOf(': ');
          return [line.slice(0, offset), line.slice(offset + 2)];
        }));
        if (fields.event && fields.data) receive(Number(fields.id), fields.event, JSON.parse(fields.data));
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export const requestKey = () => crypto.randomUUID();
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function awaitRun(id, progress = () => {}) {
  const path = '/v1/runs/' + id;
  for (let sample = 0; sample < 120; sample++) {
    const run = await api(path);
    progress(run);
    if (run.state === 'succeeded') return { run, output: await api(path + '/output.json') };
    if (run.state === 'failed') throw new RequestError(422, run.error_code);
    await sleep(run.state === 'waiting' ? 900 : 260);
  }
  throw new Error('This report is taking longer than expected. Check Schedules and status or try again.');
}

export async function download(id, format, provisional) {
  const response = await request('/v1/runs/' + id + '/output.' + format);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = (provisional ? 'provisional-' : '') + 'quarterly-report.' + format;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
