"use strict";

const $ = (id) => document.getElementById(id);
const terminal = new Set(["succeeded", "failed", "cancelled"]);
const pageSize = 12;
let identity = "";
let reasons = {};
let session = new AbortController();
let view = "reports";
let reportsOffset = 0;
let reportWatch = 0;
let report = null;
let draft = null;
let sectionId = null;
let conversation = null;
let turn = null;
let stream = null;
let cursor = 0;
let run = null;
let runWatch = 0;

function node(tag, value, className) {
  const element = document.createElement(tag);
  if (value !== undefined) element.textContent = value;
  if (className) element.className = className;
  return element;
}
function button(label, fn, className) {
  const element = node("button", label, className);
  element.type = "button";
  element.addEventListener("click", () => work(fn, element));
  return element;
}
function option(value, label) {
  const item = node("option", label);
  item.value = value;
  return item;
}
function json(value) {
  return node("pre", JSON.stringify(value, null, 2));
}
function detail(label, content) {
  const element = node("details");
  element.append(node("summary", label), content);
  return element;
}
function actions(...children) {
  const row = node("div", undefined, "actions");
  row.append(...children);
  return row;
}
function list(items, label) {
  if (!items.length) return node("p", label, "empty");
  const group = node("ul", undefined, "items");
  for (const item of items) group.append(item);
  return group;
}
function item(label, sub, ...controls) {
  const row = node("li", undefined, "item");
  const text = node("div");
  text.append(node("strong", label));
  if (sub) text.append(node("p", sub, "muted"));
  row.append(text);
  if (controls.length) row.append(actions(...controls));
  return row;
}
function definition(values) {
  const dl = node("dl");
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== "") dl.append(node("dt", key), node("dd", value));
  }
  return dl;
}

function announce(id, text) {
  $(id).textContent = text || "";
  $(id).hidden = !text;
}
function wording(code) {
  return reasons[code] || "The request could not be completed.";
}
class ApiError extends Error {
  constructor(status, reason) {
    const message = Array.isArray(reason)
      ? reason.map((issue) => `${(issue.loc || []).slice(1).join(".")}: ${issue.msg}`).join(" ")
      : reasons[reason] || (typeof reason === "string" && reason.includes(" ") ? reason : wording(reason));
    super(message);
    this.status = status;
    this.reason = reason;
  }
}
async function request(path, { method = "GET", body, headers = {}, raw = false, signal } = {}) {
  const ownerSignal = session.signal;
  const response = await fetch(path, {
    method, cache: "no-store",
    headers: { ...headers, ...(identity && path.startsWith("/v1/") ? { "X-Aegis-Local-Identity": identity } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal ? AbortSignal.any([ownerSignal, signal]) : ownerSignal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(response.status, error.detail);
  }
  const value = raw ? response : await response.json();
  ownerSignal.throwIfAborted();
  return value;
}
const post = (path, body) => request(path, { method: "POST", body });
const patch = (path, body) => request(path, { method: "PATCH", body });
const period = () => {
  const year = Number($("year").value);
  if (!Number.isInteger(year) || year < 1900 || year > 2200) throw new Error("Choose a fiscal year from 1900 to 2200.");
  return { year, quarter: Number($("quarter").value) };
};
const periodText = (p) => `FY${p.year} Q${p.quarter}`;
const idPath = (value) => encodeURIComponent(value.trim());
const formData = (form) => Object.fromEntries(new FormData(form));
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const reportPath = (id = report?.id) => `/v1/reports/${idPath(id)}`;
const draftPath = (id = draft?.id) => `/v1/drafts/${idPath(id)}`;
const runPath = (id) => `/v1/runs/${idPath(id)}`;
const turnPath = () => `/v1/conversations/${conversation.id}/turns/${turn.id}`;

async function work(fn, control) {
  const current = session.signal;
  announce("error", "");
  if (control) control.disabled = true;
  try {
    await fn();
  } catch (error) {
    if (!current.aborted && error.name !== "AbortError") {
      announce("status", "");
      announce("error", error.message);
    }
  } finally {
    if (control && !current.aborted) {
      control.disabled = false;
      if (["send-turn", "cancel-turn", "pause-stream", "resume-stream"].includes(control.id)) chatControls();
    }
  }
}
function onClick(id, fn) {
  $(id).addEventListener("click", () => work(fn, $(id)));
}
function bindForm(id, fn) {
  $(id).addEventListener("submit", (event) => {
    event.preventDefault();
    work(() => fn(formData(event.currentTarget || $(id))), event.submitter);
  });
}
const titles = { reports: "Reports", templates: "Templates", draft: "Draft editor", runs: "Runs & evidence", sources: "Source coverage" };
function show(next, focus = true) {
  view = next;
  $("view-title").textContent = titles[view];
  for (const key of Object.keys(titles)) $("view-" + key).hidden = key !== view;
  for (const control of $("nav").querySelectorAll("button")) {
    if (control.dataset.view === view) control.setAttribute("aria-current", "page");
    else control.removeAttribute("aria-current");
  }
  if (focus) $("view-title").focus();
}
async function go(next) {
  if (view === "runs" && next !== "runs") runWatch += 1;
  show(next);
  if (next === "reports") await loadReports();
  if (next === "templates") await loadTemplates();
  if (next === "runs" && run && !terminal.has(run.state)) await openRun(run.id);
}
for (const control of document.querySelectorAll("[data-view], [data-go]")) {
  control.addEventListener("click", () => work(() => go(control.dataset.view || control.dataset.go)));
}

async function loadReports(more = false) {
  if (!more) {
    reportsOffset = 0;
    $("report-list").replaceChildren(node("p", "Loading reports…", "muted"));
  }
  const rows = await request(`/v1/reports?archived=${$("archived").checked}&limit=${pageSize}&offset=${reportsOffset}`);
  const entries = rows.map((row) => item(row.title, `Version ${row.head}${row.archived_at ? " · Archived" : ""}`,
    button("Open", () => loadReport(row.id))));
  if (!more) $("report-list").replaceChildren(list(entries, "No reports for this identity."));
  else $("report-list").querySelector("ul").append(...entries);
  reportsOffset += rows.length;
  $("more-reports").hidden = rows.length < pageSize;
}
$("archived").addEventListener("change", () => work(() => loadReports()));
onClick("more-reports", () => loadReports(true));

function makeField(label, control) {
  const field = node("label", label);
  field.append(control);
  return field;
}
function input(type, value) {
  const element = node("input");
  element.type = type;
  element.value = value ?? "";
  return element;
}
async function loadReport(id) {
  const watch = ++reportWatch;
  const path = reportPath(id);
  const pane = $("report-detail");
  pane.replaceChildren(node("p", "Loading report…", "muted"));
  const current = await request(path);
  const [versions, history, periods, schedule] = await Promise.all([
    request(path + "/versions?limit=20"),
    request(path + "/schedule/runs?limit=20"),
    request(path + "/schedule/periods?limit=20"),
    request(path + "/schedule").catch((error) => {
      if (error.reason === "schedule_not_found") return null;
      throw error;
    }),
  ]);
  if (watch !== reportWatch) return;
  report = current;
  const active = !report.archived_at;
  const revision = report.head;
  const heading = node("h4", report.title);
  const title = input("text", report.title);
  title.maxLength = 100;
  const rename = button("Rename", async () => {
    await patch(path, { title: title.value });
    await loadReports();
    await loadReport(id);
  });
  rename.disabled = !active;
  const archive = button(active ? "Archive" : "Restore", async () => {
    await post(path + (active ? "/archive" : "/restore"));
    await loadReports();
    await loadReport(id);
  });
  const clone = button("Clone", async () => {
    const copy = await post(path + "/clone", {});
    await loadReports();
    await loadReport(copy.id);
  });
  pane.replaceChildren(heading, definition({ ID: report.id, Version: revision }), makeField("Catalog name", title),
    actions(rename, archive, clone));
  const versionList = list(versions.map((version) => item(`Version ${version.version}`, version.created_at,
    button("Inspect", async () => {
      const spec = await request(path + "/versions/" + version.version);
      $("version-spec").replaceChildren(detail("Saved specification", json(spec)));
      $("version-spec").firstChild.open = true;
    }),
    ...(active ? [button("Open as draft", async () => {
      setDraft(await post(path + "/versions/" + version.version + "/drafts"));
      show("draft");
    }), button("Generate", async () => {
      const next = await post(path + "/runs", { version: version.version, period: period(), request_key: crypto.randomUUID() });
      await openRun(next.id);
    })] : []))), "No saved versions.");
  const specContainer = node("div");
  specContainer.id = "version-spec";
  pane.append(detail("Versions", versionList), specContainer);
  const scheduleBox = node("div", undefined, "flow");
  const versionInput = input("number", schedule?.version ?? revision);
  versionInput.min = "1";
  const scheduleYear = input("number", schedule?.period.year ?? $("year").value);
  scheduleYear.min = "1900";
  scheduleYear.max = "2200";
  const scheduleQuarter = node("select");
  for (let quarter = 1; quarter <= 4; quarter++) scheduleQuarter.append(option(quarter, `Q${quarter}`));
  scheduleQuarter.value = schedule?.period.quarter ?? $("quarter").value;
  const timezone = input("text", schedule?.timezone ?? "America/Toronto");
  const quiet = input("number", schedule?.quiet_seconds);
  quiet.min = "0";
  quiet.placeholder = "Deployment default";
  const correction = input("number", schedule?.correction_days ?? 14);
  correction.min = "0";
  correction.max = "90";
  const provisional = input("number", schedule?.provisional_after_hours);
  provisional.min = "0";
  provisional.placeholder = "Wait for complete inputs";
  const enabled = input("checkbox");
  enabled.checked = Boolean(schedule?.enabled);
  const checked = makeField("Enabled", enabled);
  checked.className = "check";
  const save = button("Save schedule", async () => {
    await request(path + "/schedule", { method: "PUT", body: {
      version: Number(versionInput.value), enabled: enabled.checked,
      period: { year: Number(scheduleYear.value), quarter: Number(scheduleQuarter.value) },
      expected_revision: schedule?.revision ?? null, timezone: timezone.value,
      quiet_seconds: quiet.value === "" ? null : Number(quiet.value), correction_days: Number(correction.value),
      provisional_after_hours: provisional.value === "" ? null : Number(provisional.value),
    } });
    await loadReport(id);
  });
  const enqueue = button("Request schedule check", async () => {
    const next = await post(path + "/schedule/enqueue");
    await openRun(next.id);
  });
  save.disabled = !active;
  enqueue.disabled = !active || !schedule?.enabled;
  scheduleBox.append(schedule ? definition({
    "Schedule revision": schedule.revision, "Next target": periodText(schedule.next_period),
  }) : node("p", "No schedule configured.", "empty"),
    makeField("Pinned version", versionInput), makeField("Starting fiscal year", scheduleYear),
    makeField("Starting fiscal quarter", scheduleQuarter), makeField("Timezone", timezone),
    makeField("Quiet period in seconds", quiet), makeField("Correction window in days", correction),
    makeField("Allow a provisional report after hours", provisional), checked, actions(save, enqueue));
  const periodStatuses = node("div", undefined, "flow");
  const statusLabels = { waiting_for_data: "Waiting for data", ready_to_run: "Ready to run", running: "Running",
    published: "Published", provisional: "Provisional", failed: "Failed", superseded: "Superseded" };
  for (const row of periods) {
    const state = node("div", undefined, "flow");
    state.append(definition({
      "Pinned version": row.version, Generation: row.generation,
      "Current output": row.current_kind, "Next check": row.next_check_at ? new Date(row.next_check_at).toLocaleString() : null,
      Detail: row.message,
    }));
    if (row.missing.length) state.append(detail("Pending bank and source scopes", observations(row.missing)));
    if (row.last_correction.length) state.append(detail("Latest correction", list(row.last_correction.map((change) => item(
      `${change.bank || "Scope"} · ${sourceLabels[change.source] || change.source || "Source"}`,
      `${change.change}${change.period ? " · " + periodText(change.period) : ""}`,
    )), "")));
    if (row.current_run_id) state.append(button("Open current output", () => openRun(row.current_run_id)));
    periodStatuses.append(detail(`${periodText(row.period)} · ${statusLabels[row.state] || row.state}`, state));
  }
  if (!periods.length) periodStatuses.append(node("p", "No fiscal periods have been checked yet.", "empty"));
  periodStatuses.append(button("Refresh schedule status", () => loadReport(id)));
  const statuses = detail("Schedule period status", periodStatuses);
  statuses.open = Boolean(schedule?.enabled);
  pane.append(detail("Schedule", scheduleBox), statuses, detail("Scheduled run history", list(history.map((row) => item(
    `${periodText(row.period)} · ${statusLabels[row.publication_state] || row.state}`,
    row.error_code ? wording(row.error_code) : `Version ${row.version}`,
    button("Open run", () => openRun(row.id)))), "No runs have been enqueued by this schedule.")));
  $("template-save").elements.report_id.value = report.id;
}
async function loadTemplates() {
  const rows = await request("/v1/templates");
  $("template-select").replaceChildren(...rows.map((template) => option(template.id, template.title)));
  $("template-list").replaceChildren(list(rows.map((row) => item(row.title, row.kind, button("Use template", async () => {
    $("template-select").value = row.id;
    $("template-start").elements.bank.focus();
  }))), "No templates are available."));
}
bindForm("template-start", async (data) => {
  const created = await post("/v1/drafts", { template: data.template, bank: data.bank.trim() || null });
  setDraft(created);
  show("draft");
  announce("status", "Draft created.");
});
bindForm("template-save", async (data) => {
  await post("/v1/templates", { report_id: data.report_id.trim(), title: data.title, version: Number(data.version) || null });
  await loadTemplates();
  announce("status", "Personal template created.");
});

function setDraft(value, selected = sectionId) {
  if (value.id !== draft?.id) {
    stopStream();
    conversation = turn = null;
    cursor = 0;
    $("chat-message").replaceChildren();
    $("chat-events").replaceChildren();
    $("proposal").replaceChildren();
  }
  draft = value;
  sectionId = value.spec.sections.find((section) => section.id === selected)?.id ?? value.spec.sections[0].id;
  $("draft-title").textContent = draft.spec.title;
  $("draft-revision").textContent = `Draft revision ${draft.revision}${draft.base_version ? ` · Based on v${draft.base_version}` : ""}`;
  $("draft-controls").disabled = $("refresh-draft").disabled = false;
  $("chat-send").elements.message.disabled = false;
  $("conversation-label").textContent = conversation ? `Context: ${periodText(conversation.period)}` : "The first message starts a conversation for the selected period.";
  $("compiled").hidden = true;
  renderSections();
  chatControls();
}
function renderSections() {
  const sections = draft.spec.sections;
  $("section-list").replaceChildren(list(sections.map((section, index) => {
    const row = item(section.title, `${section.kind} · ${section.mode.replace("_", " ")}`,
      button("Edit", async () => {
        sectionId = section.id;
        renderSections();
        $("section-json").focus();
      }),
      ...[-1, 1].filter((delta) => sections[index + delta]).map((delta) => button(delta < 0 ? "Move up" : "Move down", async () => {
        const order = sections.map((entry) => entry.id);
        [order[index], order[index + delta]] = [order[index + delta], order[index]];
        await applyEdit({ op: "reorder_sections", section_ids: order }, section.id);
      })),
      ...(sections.length > 1 ? [button("Remove", () => applyEdit({ op: "remove_section", section_id: section.id }))] : []));
    if (section.id === sectionId) row.classList.add("selected");
    return row;
  }), "No sections."));
  const selected = sections.find((section) => section.id === sectionId) || sections[0];
  $("section-label").textContent = `Section specification · ${selected.title}`;
  $("section-json").value = JSON.stringify(selected, null, 2);
  const scope = $("preview-scope");
  const prior = scope.value;
  scope.replaceChildren(option("", "Whole report"), ...sections.map((section) => option(section.id, section.title)));
  if (sections.some((section) => section.id === prior)) scope.value = prior;
}
async function applyEdit(operation, selected) {
  setDraft(await patch(draftPath() + "/operations", { revision: draft.revision, operations: [operation] }), selected);
  announce("status", "Draft updated.");
}
bindForm("draft-open", async ({ id }) => setDraft(await request(draftPath(id))));
onClick("refresh-draft", async () => setDraft(await request(draftPath())));
onClick("add-section", () => {
  sectionId = null;
  $("section-label").textContent = "New section specification";
  $("section-json").value = JSON.stringify({
    id: "margin", title: "Margin", bank: "SYN1-CA", kind: "highlights", mode: "staged",
    sources: [{ source: "investor_presentation", terms: ["net interest margin"] }],
    instruction: "Find substantive evidence about margins.", output_format: "themes",
  }, null, 2);
  $("section-json").focus();
});
bindForm("edit-section", async () => {
  let section;
  try { section = JSON.parse($("section-json").value); }
  catch { throw new Error("The section specification must be valid JSON."); }
  if (sectionId && section.id !== sectionId) throw new Error("Keep the section ID when editing an existing section.");
  await applyEdit({ op: sectionId ? "replace_section" : "add_section", section }, section.id);
});
onClick("show-stages", async () => {
  $("compiled").textContent = JSON.stringify(await request(draftPath() + "/stages"), null, 2);
  $("compiled").hidden = false;
});
bindForm("draft-preview", async (data) => {
  const next = await post(draftPath() + "/previews", {
    revision: draft.revision, period: period(), baseline_run_id: data.baseline_run_id.trim() || null,
    section_id: data.section_id || null, stop_after: data.gather ? "gather" : null,
  });
  await openRun(next.id);
});
onClick("save-draft", async () => {
  const saved = await post(draftPath() + "/save", { revision: draft.revision });
  setDraft(await request(draftPath()));
  $("template-save").elements.report_id.value = saved.report_id;
  announce("status", `Saved version ${saved.version}.`);
});

function stopStream() {
  stream?.abort();
  stream = null;
}
function chatControls() {
  const active = Boolean(turn && !terminal.has(turn.state));
  $("send-turn").disabled = !draft || active;
  $("pause-stream").disabled = !stream;
  $("resume-stream").disabled = !turn || Boolean(stream);
  $("cancel-turn").disabled = !active;
}
function paintTurn(record) {
  turn = record;
  if (record.message) $("chat-message").textContent = record.message;
  if (record.error_code) $("chat-message").textContent = wording(record.error_code);
  const proposal = $("proposal");
  proposal.replaceChildren();
  if (record.proposal) {
    proposal.append(detail(`Proposed operations · revision ${record.proposal.revision}`, json(record.proposal.operations)));
    proposal.firstChild.open = true;
    if (record.applied_revision) {
      proposal.append(node("p", `Applied at revision ${record.applied_revision}.`, "muted"));
    } else {
      const accept = button("Accept proposal", async () => {
        const applied = await post(turnPath() + "/accept", { revision: record.proposal.revision });
        setDraft(await request(draftPath(applied.draft_id)));
        paintTurn(await request(turnPath()));
        announce("status", `Applied proposal at revision ${applied.revision}.`);
      }, "primary");
      accept.disabled = record.state !== "succeeded" || draft.revision !== record.proposal.revision;
      proposal.append(accept);
      if (draft.revision !== record.proposal.revision) proposal.append(node("p", wording("stale_draft_revision"), "muted"));
    }
  }
  if (record.preview_id) proposal.append(button("Open chat preview", () => openRun(record.preview_id)));
  chatControls();
}
function consumeEvent(frame) {
  let number;
  let kind;
  const payload = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("id:")) number = Number(line.slice(3).trim());
    else if (line.startsWith("event:")) kind = line.slice(6).trim();
    else if (line.startsWith("data:")) payload.push(line.slice(5).trimStart());
  }
  if (!kind || !number || number <= cursor) return;
  cursor = number;
  const data = JSON.parse(payload.join("\n") || "{}");
  const label = kind.replaceAll("_", " ");
  $("chat-events").append(node("li", `${number} · ${label}${data.name ? ` · ${data.name}` : ""}`));
  if (kind === "message") $("chat-message").textContent = data.text;
}
async function resumeStream() {
  if (!turn || stream) return;
  const controller = new AbortController();
  stream = controller;
  const path = turnPath();
  chatControls();
  let retries = 0;
  try {
    while (!controller.signal.aborted) {
      try {
        const response = await request(path + "/events", {
          raw: true, signal: controller.signal,
          headers: { "Accept": "text/event-stream", "Last-Event-ID": String(cursor) },
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          controller.signal.throwIfAborted();
          buffer += decoder.decode(value, { stream: true });
          let boundary;
          while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
            consumeEvent(buffer.slice(0, boundary.index));
            buffer = buffer.slice(boundary.index + boundary[0].length);
          }
        }
        const result = await request(path, { signal: controller.signal });
        paintTurn(result);
        if (terminal.has(result.state)) return;
        retries = 0;
      } catch (error) {
        if (controller.signal.aborted || error.name === "AbortError") return;
        if (error instanceof ApiError || ++retries > 2) {
          const fallback = await request(path, { signal: controller.signal });
          paintTurn(fallback);
          if (!terminal.has(fallback.state)) announce("status", "Stream disconnected. Resume to reconnect from the last event.");
          return;
        }
      }
      await wait(300);
    }
  } finally {
    if (stream === controller) {
      stream = null;
      chatControls();
    }
  }
}
bindForm("chat-send", async ({ message }) => {
  const activePeriod = period();
  if (!conversation || periodText(conversation.period) !== periodText(activePeriod)) {
    conversation = await post("/v1/conversations", { draft_id: draft.id, period: activePeriod });
    $("conversation-label").textContent = `Context: ${periodText(conversation.period)}`;
  }
  stopStream();
  const result = await post(`/v1/conversations/${conversation.id}/turns`, { message, request_key: crypto.randomUUID() });
  cursor = 0;
  $("chat-events").replaceChildren();
  $("chat-message").textContent = "Turn queued.";
  $("chat-send").reset();
  paintTurn(result);
  void work(resumeStream);
});
onClick("pause-stream", () => {
  stopStream();
  chatControls();
  announce("status", "Stream paused. The turn can continue on the server.");
});
onClick("resume-stream", resumeStream);
onClick("cancel-turn", async () => {
  const result = await post(turnPath() + "/cancel");
  paintTurn(result);
  if (result.state === "cancelled") $("chat-message").textContent = "Turn cancelled.";
});

const sourceLabels = {
  benchmarking: "Benchmarking", transcripts: "Earnings transcripts", investor_presentation: "Investor slides",
  rts: "Reports to shareholders", supplementary_financials: "Supplementary financials",
  event_transcripts: "Event transcripts", pillar3: "Pillar 3",
};
function observations(rows) {
  return list(rows.map((entry) => {
    const state = entry.evidence_state === "matched" ? "Evidence returned"
      : entry.evidence_state === "no_match" ? "No matching evidence"
      : entry.state === "ready" ? "Source ready" : "Unavailable";
    return item(`${sourceLabels[entry.source] || entry.source || "Source"} · ${state}`,
      [entry.bank, entry.period && periodText(entry.period), entry.message || (entry.reason && wording(entry.reason)),
        entry.data_stability && `Stability: ${entry.data_stability.replace("_", " ")}`].filter(Boolean).join(" · "));
  }), "No source observations recorded.");
}
function renderRun(record) {
  run = record;
  const box = $("run-status");
  box.replaceChildren(node("span", record.state, "status-tag"),
    definition({ Period: periodText(record.period), Type: record.mode, Trigger: record.trigger_kind, Version: record.version }),
    ...(record.error_code ? [node("p", wording(record.error_code), "error notice")] : []),
  );
  if (Object.keys(record.readiness).length)
    box.append(detail("Run readiness", observations(Object.values(record.readiness))));
}
function citeButton(id) {
  const runId = run.id;
  return button("Citation", async () => {
    const citation = await request(`${runPath(runId)}/evidence/${idPath(id)}/detail`);
    if (run?.id !== runId) return;
    $("citation-detail").replaceChildren(definition({
      Source: sourceLabels[citation.source] || citation.source, Locator: citation.locator, Excerpt: citation.excerpt,
    }));
    $("citation-title").focus();
  });
}
function renderOutput(result) {
  $("exports").hidden = false;
  $("export-pdf").hidden = run.mode !== "generate";
  const pane = $("run-output");
  pane.replaceChildren(node("h3", result.title));
  if (result.publication === "provisional")
    pane.append(node("p", "Provisional report. Required source inputs are still pending.", "notice"));
  if (result.diff) {
    const diff = detail("Diff against saved baseline", json({ summary: result.diff, detail: result.diff_details }));
    diff.open = true;
    pane.append(diff);
  }
  const scoped = Object.entries(result.readiness || {});
  for (const section of result.sections) {
    const group = node("section", undefined, "section-result");
    group.append(node("h4", section.title), node("p", section.resolved_periods.map(periodText).join(" · "), "muted"));
    const sourceRows = scoped.filter(([key, entry]) => (entry.section_id || key.split(":")[0]) === section.id);
    group.append(detail("Section source outcomes", observations(sourceRows.map(([, value]) => value))));
    const evidence = [];
    for (const row of section.rows) {
      evidence.push(item(`${row.bank} · ${row.metric} · ${row.actual} ${row.unit || ""}`,
        [periodText(row.period), row.segment, row.currency && `${row.currency}${row.currency_confirmed ? "" : " (unconfirmed)"}`].filter(Boolean).join(" · "),
        citeButton(row.citation.id)));
    }
    for (const claim of section.claims)
      evidence.push(item(claim.topic, claim.text, ...claim.evidence_ids.map(citeButton)));
    if (section.note) evidence.push(item("Observation note", section.note.text, citeButton(section.note.citation_id)));
    for (const stage of section.stage_outputs) {
      if (stage.kind === "retrieve") {
        for (const passage of stage.passages)
          evidence.push(item("Gathered passage", passage.excerpt, citeButton(passage.citation.id)));
        if (!section.rows.length) for (const row of stage.rows)
          evidence.push(item(`${row.bank} · ${row.metric}`, `${row.actual} ${row.unit || ""}`, citeButton(row.citation.id)));
      }
    }
    group.append(list(evidence, "No cited evidence in this section."));
    if (section.comparisons.length) group.append(detail("Period comparisons", json(section.comparisons)));
    if (section.peers.length) group.append(detail("Peer comparisons", list(section.peers.map((peer) => {
      const label = `${peer.metric} · ${periodText(peer.period)}`;
      if (peer.reason) return item(label, [wording(peer.reason),
        peer.missing_banks?.length && `Missing banks: ${peer.missing_banks.join(", ")}.`].filter(Boolean).join(" "));
      const directions = { higher_is_better: "Higher is better", lower_is_better: "Lower is better", highest_to_lowest: "Highest to lowest" };
      const order = peer.ordered_values?.length ? peer.ordered_values : peer.ranks;
      const currency = peer.currency ? ` · ${peer.currency}${peer.currency_confirmed ? "" : " (unconfirmed)"}` : "";
      const subtitle = `${directions[peer.direction] || "Historical order"}${currency} · High ${peer.high}, low ${peer.low}, median ${peer.median}. `;
      return item(label, subtitle + order.map((row) => `${row.rank ? `#${row.rank} ` : ""}${row.bank}: ${row.value}`).join(" · "));
    }), "No comparable peers.")));
    if (section.stage_outputs.length) group.append(detail("Stage outputs", json(section.stage_outputs)));
    pane.append(group);
  }
}
async function openRun(id) {
  const watch = ++runWatch;
  $("run-open").elements.id.value = id;
  $("exports").hidden = true;
  $("run-output").replaceChildren();
  $("run-status").replaceChildren(node("p", "Loading run…", "muted"));
  $("citation-detail").replaceChildren(node("p", "Open a citation to inspect its source.", "empty"));
  show("runs");
  const read = async () => {
    const record = await request(runPath(id));
    if (watch !== runWatch) return;
    renderRun(record);
    if (record.state === "succeeded") {
      const result = await request(runPath(id) + "/output.json");
      if (watch === runWatch) renderOutput(result);
    } else if (!terminal.has(record.state)) {
      setTimeout(() => {
        if (watch === runWatch) void work(read);
      }, record.state === "waiting" ? 2500 : 850);
    }
  };
  await read();
}
bindForm("run-open", ({ id }) => openRun(id.trim()));
for (const control of document.querySelectorAll("[data-export]")) {
  control.addEventListener("click", () => work(async () => {
    const id = run.id;
    const format = control.dataset.export;
    const response = await request(runPath(id) + "/output." + format, { raw: true });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = node("a");
    link.href = url;
    link.download = `aegis-${id}.${format}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, control));
}
bindForm("probe", async ({ source, bank, metric, segment }) => {
  const result = await post(`/v1/sources/${source}/probe`, {
    bank, metric: metric.trim() || null, segment, period: period(),
  });
  $("probe-result").replaceChildren(definition({ State: result.state, Generation: result.generation,
    Detail: result.reason ? wording(result.reason) : "Usable evidence is available.",
    "Availability hint": result.availability_hint ? "Flagged" : "No flag",
  }));
});

async function changeIdentity(value) {
  stopStream();
  session.abort();
  session = new AbortController();
  identity = value;
  report = draft = conversation = turn = run = null;
  sectionId = null;
  cursor = 0;
  runWatch += 1;
  reportWatch += 1;
  for (const id of ["report-list", "template-list", "template-select", "section-list", "run-status", "run-output", "chat-events",
    "chat-message", "proposal", "citation-detail", "compiled", "draft-revision"]) $(id).replaceChildren();
  $("report-detail").replaceChildren(node("p", "Choose a saved report to open it.", "empty"));
  $("probe-result").replaceChildren(node("p", "Choose a bank, source and period to check coverage.", "empty"));
  for (const id of ["draft-open", "run-open", "template-save", "draft-preview", "chat-send"]) $(id).reset();
  $("draft-title").textContent = "No open draft";
  $("section-json").value = "";
  $("exports").hidden = $("compiled").hidden = true;
  $("conversation-label").textContent = "Open a draft to start a conversation.";
  $("draft-controls").disabled = $("refresh-draft").disabled = $("chat-send").elements.message.disabled = true;
  announce("status", "");
  chatControls();
  reasons = await request("/v1/reasons");
  const banks = await request("/v1/catalog/banks");
  $("banks").replaceChildren(...banks.map((bank) => option(bank.symbol, bank.name)));
  show("reports", false);
  await loadReports();
}
$("identity").addEventListener("change", (event) => {
  const value = event.target.value;
  void changeIdentity(value).catch((error) => { if (error.name !== "AbortError") announce("error", error.message); });
});
void work(async () => {
  const context = await request("/console/context");
  $("identity").replaceChildren(...context.identities.map((entry) => option(entry, entry)));
  await changeIdentity(context.identities[0]);
});
