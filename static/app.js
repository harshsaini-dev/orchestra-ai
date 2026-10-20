import { AgentGraph, renderGantt } from './graph.js';
'use strict';
const spatialGraph = new AgentGraph(document.getElementById('spatial-graph'), index => { selected = index; renderTrace(); });
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
} [c]));
const human = v => String(v ?? '').replaceAll('_', ' ');
const money = p => new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR'
}).format(p / 100);
const clock = s => new Date(s).toLocaleTimeString([], {
  hour12: false
});
const agents = [{
  name: 'Planner Agent',
  short: 'Planner',
  icon: '01',
  role: 'Understands the task',
  purpose: 'Reads the customer message, identifies the requested operation, and plans the next steps.'
}, {
  name: 'Data Agent',
  short: 'Data',
  icon: '02',
  role: 'Reads the order',
  purpose: 'Uses the permitted get_order_status tool to read the order from SQLite.'
}, {
  name: 'Policy Agent',
  short: 'Policy',
  icon: '03',
  role: 'Finds the evidence',
  purpose: 'Retrieves relevant policies using BM25 lexical search and intent routing, including approval controls.'
}, {
  name: 'Decision Agent',
  short: 'Decision',
  icon: '04',
  role: 'Checks eligibility',
  purpose: 'Applies business rules to the order and policy evidence. Proposes an action or escalates the request.'
}, {
  name: 'Action Agent',
  short: 'Action',
  icon: '05',
  role: 'Executes after review',
  purpose: 'Waits for your approval, rechecks order and policy changes, then commits the allowed action and audit in one transaction.'
}];
const terminal = new Set(['done', 'failed', 'cancelled', 'interrupted']);
let events = [],
  selected = 0,
  busy = false,
  source = null,
  job = null,
  workflow = null,
  replaying = false,
  cursor = 0,
  history = [],
  orders = [],
  view = 'console',
  finishing = false;

function error(message = '') {
  $('error').textContent = message;
  $('error').hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data
    .detail || data));
  return data;
}
const post = (path, body) => api(path, {
  method: 'POST',
  body: JSON.stringify(body)
});

function pill(el, status, label) {
  el.textContent = label || human(status);
  el.dataset.status = status;
}

function setBusy(value) {
  busy = value;
  if (!value) {
    $('stop').disabled = false;
    $('stop').textContent = 'Stop run';
  }
  $('run').disabled = value;
  $('stop').hidden = !value || job?.kind !== 'run';
  document.querySelectorAll('#review-form button').forEach(b => b.disabled = value || replaying);
  $('replay-toggle').disabled = value || !events.length;
}

function showView(name) {
  view = name;
  document.querySelectorAll('.view').forEach(e => e.hidden = e.id !== 'view-' + name);
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  const names = {
    console: ['Live console', 'Operations, in motion.',
      'Follow the agents, inspect their work, and stay in control.'
    ],
    history: ['Run history', 'A record of every decision.',
      'Inspect past runs or pick up an action waiting for review.'
    ],
    orders: ['Order records', 'The data behind the decision.',
      'Current synthetic order records, with versioned updates.'
    ],
    knowledge: ['Policy library', 'The rules behind every action.',
      'Inspect the evidence your agents use to make a decision.'
    ],
    rag: ['RAG knowledge', 'Answers grounded in your documents.',
      'Upload, index, retrieve and inspect the sources behind a generated answer.'
    ],
    guide: ['How it works', 'Understand what you are building.',
      'A practical walkthrough of the agents, tools and controls.'
    ]
  };
  $('breadcrumb').textContent = names[name][0];
  $('page-title').textContent = names[name][1];
  $('page-subtitle').textContent = names[name][2];
}

function record(event) {
  if (events.some(e => e.id === event.id)) return;
  events.push(event);
  events.sort((a, b) => a.id - b.id);
  if (event.kind === 'agent_started') {
    const index = agents.findIndex(a => a.name === event.agent);
    if (index >= 0) selected = index;
  }
  $('live-announcement').textContent = event.agent + ': ' + human(event.kind);
  if (!replaying) { renderTrace(); if (event.kind === 'message_sent') spatialGraph.packet(event.detail); }
}

function stateFor(name, visible) {
  const own = visible.filter(e => e.agent === name);
  const latest = own.filter(e => ['agent_state_changed', 'agent_started', 'agent_completed', 'agent_waiting', 'agent_skipped'].includes(e.kind)).at(-1);
  let state = ({
    agent_started: 'running',
    agent_completed: 'complete',
    agent_waiting: 'waiting',
    agent_skipped: 'skipped'
  })[latest?.kind] || ({thinking: 'running', retrieving: 'running', working: 'running', waiting_approval: 'waiting', done: 'complete', error: 'failed', recovering: 'running', cancelled: 'stopped'})[latest?.detail?.state] || 'idle';
  const end = visible.at(-1);
  if (state === 'running' && ['failed', 'cancelled', 'interrupted'].includes(end?.kind)) state = end.kind ===
    'failed' ? 'failed' : 'stopped';
  return {
    state,
    own,
    latest,
    input: own.findLast(e => e.kind === 'agent_started'),
    output: own.findLast(e => ['agent_completed', 'agent_skipped', 'agent_waiting'].includes(e.kind))
  };
}

function eventMessage(e) {
  const d = e.detail;
  if (e.kind === 'message_sent') return `${d.from} → ${d.to} · ${d.type}`;
  if (e.kind === 'agent_state_changed') return `${d.previous} → ${d.state}`;
  return d.error || d.message || d.reason || d.result || d.purpose || ({
    agent_completed: 'Finished · ' + (d.duration_ms ?? '—') + ' ms compute',
    agent_started: 'Working',
    agent_waiting: 'Waiting for review',
    agent_skipped: 'No execution required'
  })[e.kind] || human(e.kind);
}

function renderTrace() {
  const visible = replaying ? events.slice(0, cursor) : events;
  let resolved = 0;
  const states = agents.map(a => stateFor(a.name, visible));
  spatialGraph.update(states, selected, visible, replaying);
  renderGantt($('gantt'), visible, agents);
  $('trace-id').textContent = visible.findLast(e => e.detail?.trace_id)?.detail.trace_id || 'AWAITING RUN';
  const focusedAgent = document.activeElement?.closest('[data-agent]')?.dataset.agent;
  $('agent-map').innerHTML = agents.map((a, i) => {
    const s = states[i];
    if (['complete', 'skipped'].includes(s.state)) resolved++;
    return `<button class="agent ${s.state} ${i===selected?'selected':''}" style="--agent-color:${['#c7b8ff','#8ec9ed','#d5c58d','#92d8b7','#efaa85'][i]}" data-agent="${i}" aria-pressed="${i===selected}" aria-label="${a.name}: ${s.state}"><span class="agent-icon">${s.state==='complete'?'✓':a.icon}</span><h3>${a.short}</h3><span class="role">${a.role}</span><span class="agent-state">${s.state==='waiting'?'Review needed':s.state}</span></button>`;
  }).join('');
  if (focusedAgent !== undefined) $('agent-map').querySelector(`[data-agent="${focusedAgent}"]`)?.focus({preventScroll:true});
  $('stage-count').textContent = resolved + ' / 5 stages resolved';
  const a = agents[selected],
    s = states[selected];
  $('inspector-title').textContent = a.name;
  $('inspector-state').textContent = s.state.toUpperCase();
  $('inspector-purpose').textContent = s.input?.detail.purpose || a.purpose;
  $('inspector-duration').textContent = s.output?.detail.duration_ms !== undefined ? s.output.detail
    .duration_ms + ' ms' : '—';
  $('inspector-time').textContent = s.latest ? clock(s.latest.created_at) : '—';
  $('inspector-input').textContent = s.input ? JSON.stringify(s.input.detail, null, 2) : 'No input yet.';
  $('inspector-output').textContent = s.output ? JSON.stringify(s.output.detail, null, 2) : 'No output yet.';
  $('event-count').textContent = visible.length + ' EVENTS';
  $('timeline').innerHTML = visible.length ? visible.slice().reverse().map(e =>
    `<li class="${e.kind==='agent_started'?'running':e.kind==='agent_waiting'?'waiting':''}"><div><b>${esc(e.agent)}</b><small>${esc(eventMessage(e))}</small></div><time>${clock(e.created_at)}</time></li>`
  ).join('') : '<li class="empty">Your live execution log will appear here.</li>';
  $('replay-toggle').disabled = busy || !events.length;
  $('replay-toggle').textContent = replaying ? 'Return to full trace' : 'Inspect past steps';
  $('replay-label').textContent = replaying ? `REPLAY ${cursor} / ${events.length}` : busy ? 'LIVE' :
    'RECORDED';
  $('replay-controls').hidden = !replaying;
  $('replay-range').max = Math.max(1, events.length);
  $('replay-range').value = cursor;
  $('step-back').disabled = cursor <= 1;
  $('step-next').disabled = cursor >= events.length;
  document.querySelectorAll('#review-form button').forEach(b => b.disabled = busy || replaying);
  if (replaying) {
    pill($('run-status'), 'replay', 'HISTORICAL REPLAY');
    $('execution-subtitle').textContent =
      'Recorded events only. Replaying does not execute agents or change orders.';
  } else if (busy) {
    pill($('run-status'), 'running', visible.some(e => e.kind === 'agent_started') ? 'RUNNING' : 'QUEUED');
    const active = states.findIndex(s => s.state === 'running');
    $('execution-subtitle').textContent = active >= 0 ? agents[active].name + ' is working' + (job?.guided ?
      ' · presentation pace enabled.' : '.') : 'Waiting for the next server event…';
  } else if (job && ['failed', 'cancelled', 'interrupted'].includes(job.status)) {
    pill($('run-status'), job.status);
    $('execution-subtitle').textContent = job.error || human(job.status);
  } else if (workflow) {
    pill($('run-status'), workflow.status, workflow.status === 'pending_approval' ? 'WAITING FOR YOU' : human(
      workflow.status));
    $('execution-subtitle').textContent = workflow.status === 'pending_approval' ?
      'Action Agent is paused. Review the proposed change below.' :
      'Select an agent to inspect its input, output, and measured compute time.';
  } else if (job && terminal.has(job.status)) {
    pill($('run-status'), job.status);
    $('execution-subtitle').textContent = job.error || human(job.status);
  }
}
async function refresh() {
  const [m, rows, records] = await Promise.all([api('/api/metrics'), api('/api/workflows'), api(
    '/api/orders')]);
  for (const key of ['workflows', 'pending', 'completed', 'audit_events']) $('metric-' + key).textContent =
    m[key];
  history = rows;
  orders = records;
  $('history-count').textContent = m.workflows;
  const chosen = $('order').value;
  $('order').innerHTML = records.map(o =>
    `<option value="${esc(o.id)}">${esc(o.id)} · ${esc(o.product)}</option>`).join('');
  if (chosen) $('order').value = chosen;
  renderHistory();
  $('orders-body').innerHTML = records.map(o =>
    `<tr><td><b>${esc(o.id)}</b><small>${esc(o.customer)}</small></td><td>${esc(o.product)}</td><td>${money(o.amount_paise)}</td><td>${esc(o.status)}</td><td>${esc(o.payment_status)}</td><td class="mono">v${o.version}</td></tr>`
  ).join('');
}

function filteredHistory() {
  const q = $('history-search').value.toLowerCase();
  const status = $('history-filter').value;
  return history.filter(w => (status === 'all' || w.status === status) && [w.id, w.order_id, w.response, w
    .intent
  ].join(' ').toLowerCase().includes(q));
}

function renderHistory() {
  const rows = filteredHistory();
  $('history-total').textContent = rows.length + ' RUNS';
  $('history-body').innerHTML = rows.length ? rows.map(w =>
    `<tr><td><b class="mono">${esc(w.id)}</b><small>${new Date(w.created_at).toLocaleString()}</small></td><td>${esc(w.order_id)}</td><td>${esc(human(w.intent))}</td><td><span class="status-pill" data-status="${esc(w.status)}">${esc(human(w.status))}</span></td><td><button class="text-button" data-workflow="${esc(w.id)}" ${busy?'disabled':''}>Open run ↗</button></td></tr>`
  ).join('') : '<tr><td colspan="5" class="muted">No workflows match this view.</td></tr>';
}
async function renderResult() {
  const w = workflow;
  if (!w) {
    $('result').hidden = true;
    return;
  }
  $('result').hidden = false;
  $('result-title').textContent = w.intent === 'cancel' ? 'Cancellation review' : w.intent === 'refund' ?
    'Refund review' : 'Workflow resolution';
  pill($('result-status'), w.status);
  $('result-response').textContent = w.response;
  $('workflow-rag').hidden = !w.decision.rag;
  $('workflow-rag').innerHTML = w.decision.rag ? renderRagAnswer(w.decision.rag) : '';
  $('export').href = '/api/workflows/' + encodeURIComponent(w.id) + '/export';
  $('result-meta').innerHTML =
    `<span>${esc(w.id)}</span><span>${esc(w.order_id)}</span><span>${esc(human(w.mode))}</span>`;
  $('approval').hidden = w.status !== 'pending_approval';
  $('approval-description').textContent =
    `Proposed operation: ${human(w.decision.action)}. Amount: ${money(w.decision.amount_paise||0)}. The order and policy are checked again before execution.`;
  $('evidence').innerHTML = w.evidence.map(p =>
    `<article><b>${esc(p.id)} · ${esc(p.title||'Policy')}</b><p>${esc(p.text)}</p><p>Retrieval score: ${esc(p.score??'—')}</p></article>`
  ).join('') + `<pre>${esc(JSON.stringify(w.decision,null,2))}</pre>`;
  const current = await api('/api/orders/' + encodeURIComponent(w.order_id));
  if (workflow?.id !== w.id) return;
  const before = w.snapshot;
  const compare = o =>
    `<dl><dt>Order</dt><dd class="${o.status!==before.status?'changed':''}">${esc(o.status)}</dd><dt>Payment</dt><dd class="${o.payment_status!==before.payment_status?'changed':''}">${esc(o.payment_status)}</dd><dt>Record version</dt><dd class="${o.version!==before.version?'changed':''}">v${o.version}</dd></dl>`;
  $('comparison').innerHTML =
    `<div class="compare"><div><h4>SNAPSHOT AT REQUEST</h4>${compare(before)}</div><div><h4>CURRENT ORDER RECORD</h4>${compare(current)}</div></div><p class="compare-note">Current state can include changes from other workflows. The downloadable audit records this workflow's own action.</p>`;
}

function closeStream() {
  if (source) {
    source.close();
    source = null;
  }
}
async function completeJob() {
  if (finishing) return;
  finishing = true;
  closeStream();
  try {
    job = await api('/api/jobs/' + job.id);
    job.events.forEach(record);
    $('connection').textContent = 'Local server connected';
    if (job.error) error(job.error);
    localStorage.removeItem('agentflow-active-job');
    if (job.workflow_id) {
      workflow = await api('/api/workflows/' + job.workflow_id);
      localStorage.setItem('agentflow-last-workflow', workflow.id);
      await renderResult();
    }
    await refresh();
  } catch (e) {
    error(e.message);
  } finally {
    finishing = false;
    setBusy(false);
    renderHistory();
    renderTrace();
  }
}

function connectStream() {
  closeStream();
  const jid = job.id;
  const last = events.filter(e => e.job_id === jid).at(-1)?.id || 0;
  source = new EventSource('/api/jobs/' + encodeURIComponent(jid) + '/events?after=' + last);
  source.onopen = () => {
    $('connection').textContent = 'Stream connected';
  };
  source.onmessage = e => {
    if (job?.id !== jid) return;
    const event = JSON.parse(e.data);
    record(event);
    if (terminal.has(event.kind)) completeJob();
  };
  source.onerror = () => {
    $('connection').textContent = 'Reconnecting to stream…';
  };
}
async function attachJob(value, clear = true) {
  job = value;
  closeStream();
  if (clear) {
    events = [];
    workflow = null;
    $('result').hidden = true;
    selected = 0;
  }
  replaying = false;
  cursor = 0;
  setBusy(true);
  job.events.forEach(record);
  $('execution-title').textContent = job.kind === 'review' ? 'Human decision → controlled execution.' :
    'Following the request, step by step.';
  if (terminal.has(job.status)) {
    await completeJob();
  } else {
    localStorage.setItem('agentflow-active-job', job.id);
    connectStream();
  }
  renderTrace();
}
async function loadWorkflow(id) {
  if (busy) throw new Error('Finish or stop the active run before opening another workflow.');
  closeStream();
  error();
  workflow = await api('/api/workflows/' + encodeURIComponent(id));
  const traces = await api('/api/workflows/' + encodeURIComponent(id) + '/jobs');
  events = traces.flatMap(t => t.events).sort((a, b) => a.id - b.id);
  job = traces.at(-1) || null;
  replaying = false;
  selected = 0;
  setBusy(false);
  localStorage.setItem('agentflow-last-workflow', id);
  showView('console');
  $('execution-title').textContent = 'Recorded workflow · ' + workflow.order_id;
  await renderResult();
  renderTrace();
  if (!traces.length) $('execution-subtitle').textContent =
    'This earlier workflow has an audit record but no live execution trace. Download its audit below.';
}

function guarded(fn) {
  return async e => {
    try {
      await fn(e);
    } catch (err) {
      error(err.message);
    }
  };
}
document.querySelectorAll('.nav').forEach(b => b.addEventListener('click', () => showView(b.dataset.view)));
$('agent-map').addEventListener('click', e => {
  const b = e.target.closest('[data-agent]');
  if (b) {
    selected = Number(b.dataset.agent);
    renderTrace();
  }
});
$('run-form').addEventListener('submit', guarded(async e => {
  e.preventDefault();
  if (busy) return;
  error();
  setBusy(true);
  try {
    const request = {
      order_id: $('order').value,
      intent: $('intent').value,
      message: $('message').value,
      use_gemini: $('gemini').checked,
      use_rag: $('use-rag').checked,
      request_key: crypto.randomUUID()
    };
    const value = await post('/api/jobs', {
      request,
      guided: $('guided').checked
    });
    await attachJob(value);
  } catch (err) {
    setBusy(false);
    throw err;
  }
}));
$('stop').addEventListener('click', guarded(async () => {
  if (!job || !busy) return;
  await post('/api/jobs/' + job.id + '/stop', {});
  $('stop').disabled = true;
  $('stop').textContent = 'Stopping…';
}));
$('review-form').addEventListener('submit', guarded(async e => {
  e.preventDefault();
  if (busy || replaying || !workflow) return;
  error();
  setBusy(true);
  try {
    const value = await post('/api/workflows/' + workflow.id + '/review-job', {
      review: {
        approve: e.submitter.value === 'approve',
        reviewer: $('reviewer').value,
        note: $('review-note').value
      },
      guided: $('guided').checked
    });
    await attachJob(value, false);
  } catch (err) {
    setBusy(false);
    throw err;
  }
}));
$('open-queue').addEventListener('click', () => {
  $('history-filter').value = 'pending_approval';
  $('history-search').value = '';
  renderHistory();
  showView('history');
});
$('history-filter').addEventListener('change', renderHistory);
$('history-search').addEventListener('input', renderHistory);
$('history-body').addEventListener('click', guarded(async e => {
  const b = e.target.closest('[data-workflow]');
  if (b) await loadWorkflow(b.dataset.workflow);
}));
const scenarios = {
  cancel: {
    order: 'ORD-1001',
    intent: 'cancel',
    message: 'Please cancel my order and refund the payment.'
  },
  refund: {
    order: 'ORD-1003',
    intent: 'refund',
    message: 'Please refund my recently delivered order.'
  },
  status: {
    order: 'ORD-1002',
    intent: 'status',
    message: 'Where is my order? Please check its current status.'
  }
};
document.querySelectorAll('[data-scenario]').forEach(b => b.addEventListener('click', () => {
  const s = scenarios[b.dataset.scenario];
  $('order').value = s.order;
  $('intent').value = s.intent;
  $('message').value = s.message;
}));
$('replay-toggle').addEventListener('click', () => {
  if (busy) return;
  replaying = !replaying;
  cursor = replaying ? 1 : events.length;
  renderTrace();
});
$('replay-range').addEventListener('input', () => {
  cursor = Number($('replay-range').value);
  renderTrace();
});
$('step-back').addEventListener('click', () => {
  cursor = Math.max(1, cursor - 1);
  renderTrace();
});
$('step-next').addEventListener('click', () => {
  cursor = Math.min(events.length, cursor + 1);
  renderTrace();
});
$('csv-export').addEventListener('click', () => {
  const fields = ['id', 'order_id', 'intent', 'status', 'mode', 'created_at', 'response'];
  const quote = v => '"' + String(v ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""') + '"';
  const csv = [fields, ...filteredHistory().map(w => fields.map(k => w[k]))].map(row => row.map(quote)
    .join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob(['\ufeff' + csv], {
    type: 'text/csv;charset=utf-8;'
  }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'agentflow-workflows.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
async function init() {
  renderTrace();
  $('guide-agents').innerHTML = agents.map(a =>
    `<article class="panel"><span class="eyebrow">${a.icon} / AGENT</span><h3>${a.short}</h3><p>${a.purpose}</p></article>`
  ).join('');
  const health = await api('/api/health');
  $('connection').textContent = 'Local server connected';
  $('gemini').disabled = !health.gemini_configured;
  $('gemini-hint').textContent = health.gemini_configured ? 'Optional advisory model assistance.' :
    'No API key needed for offline mode.';
  const policies = await api('/api/policies');
  $('policies').innerHTML = policies.map(p =>
    `<article class="panel"><span class="eyebrow">${esc(p.id)}</span><h3>${esc(p.title)}</h3><p>${esc(p.text)}</p></article>`
  ).join('');
  await refresh();
  await refreshRag();
  const active = localStorage.getItem('agentflow-active-job');
  if (active) {
    try {
      const saved = await api('/api/jobs/' + active);
      if (saved.kind === 'review' && saved.workflow_id) {
        await loadWorkflow(saved.workflow_id);
        await attachJob(saved, false);
      } else await attachJob(saved);
    } catch (e) {
      localStorage.removeItem('agentflow-active-job');
      error(e.message);
    }
  } else {
    const last = localStorage.getItem('agentflow-last-workflow');
    if (last) {
      try {
        await loadWorkflow(last);
      } catch {
        localStorage.removeItem('agentflow-last-workflow');
      }
    }
  }
}
// Document RAG is opt-in. The server, not the UI, validates citations and actions.
let ragBusy = false;
let ragStatus = null;

function renderRagAnswer(r) {
  const sources = r.sources || [];
  const answer = r.answer ?
    `<h3>${r.insufficient_context ? 'Insufficient context' : 'Generated answer'}</h3><p class="rag-answer-text">${esc(r.answer)}</p>` :
    '<h3>Retrieved context only</h3><p class="muted rag-small">No answer-generation call was made.</p>';
  return `${answer}<div class="rag-meta"><span>${esc(r.method)}</span><span>Retrieval: ${esc(r.retrieval_ms)} ms</span>${r.generation_ms !== undefined ? `<span>Generation: ${esc(r.generation_ms)} ms</span>` : ''}</div>${r.generation_model ? `<p class="footnote">Model: ${esc(r.generation_model)} · ${esc(r.citation_check)}</p>` : ''}<div class="rag-sources">${sources.map(s => `<details><summary>[${esc(s.source_id)}] ${esc(s.name)} · ${s.page ? 'page '+s.page+', ' : ''}chunk ${s.chunk}</summary><p class="rag-small">${esc(s.text)}</p><p class="footnote">Cosine distance: ${esc(s.cosine_distance)} (lower is closer; not a confidence score)</p>${(r.citations || []).filter(c => c.source_id === s.source_id).map(c => `<blockquote>${esc(c.quote)}</blockquote>`).join('')}</details>`).join('')}</div>`;
}

function ragControls() {
  const ready = !!ragStatus?.ready;
  $('rag-index').disabled = ragBusy || !ragStatus?.configured || !ragStatus?.chroma_installed;
  $('rag-ask').disabled = ragBusy || !ready;
  $('rag-retrieve').disabled = ragBusy || !ready;
  $('rag-upload-form').querySelector('button').disabled = ragBusy;
  $('rag-refresh').disabled = ragBusy;
  $('use-rag').disabled = !ready;
  if (!ready) $('use-rag').checked = false;
}
async function refreshRag() {
  ragStatus = await api('/api/rag/status');
  const s = ragStatus;
  pill($('rag-status'), s.ready ? 'completed' : 'waiting', s.ready ? 'READY FOR RAG' : 'SETUP REQUIRED');
  $('rag-count').textContent = `${s.indexed_chunks} / ${s.chunks} CHUNKS INDEXED`;
  const missing = [];
  if (!s.chroma_installed) missing.push('Install RAG dependencies with start_rag.bat.');
  if (!s.configured) missing.push('Add GEMINI_API_KEY to .env locally, then restart.');
  if (s.pending_chunks) missing.push(`${s.pending_chunks} chunks need indexing.`);
  if (s.issue) missing.push(s.issue);
  $('rag-notice').textContent = s.ready ?
    `${s.embedding_model} · ${s.dimensions} dimensions · Chroma cosine search → ${s.generation_model}. A successful live answer still depends on model access and quota.` :
    missing.join(' ');
  $('workflow-rag-hint').textContent = s.ready ? 'Chroma retrieval + cited Gemini explanation.' :
    'Open RAG knowledge to configure and build the index.';
  $('rag-documents').innerHTML = s.documents.map(d =>
    `<article><div><b>${esc(d.name)}</b><small>${esc(d.id)} · ${d.chunks} chunks · ${d.kind === 'policy' ? 'governing policy' : 'supplementary upload'}</small></div><button class="text-button" data-chunks="${esc(d.id)}">Inspect chunks</button>${d.kind === 'upload' ? `<button class="text-button" data-remove-doc="${esc(d.id)}">Remove</button>` : ''}</article>`
    ).join('');
  ragControls();
}
async function runRagTask(message, action) {
  if (ragBusy) return;
  ragBusy = true;
  ragControls();
  error();
  $('rag-progress').textContent = message;
  try {
    await action();
  } catch (err) {
    $('rag-progress').textContent =
      'Request failed. No successful result was produced; see the error above.';
    throw err;
  } finally {
    ragBusy = false;
    await refreshRag();
  }
}
$('rag-refresh').addEventListener('click', guarded(refreshRag));
$('rag-upload-form').addEventListener('submit', guarded(async e => {
  e.preventDefault();
  const file = $('rag-file').files[0];
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) throw new Error('Choose a file no larger than 2 MB.');
  await runRagTask('Reading and chunking the document…', async () => {
    const encoded = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(new Error('Could not read the selected file.'));
      reader.readAsDataURL(file);
    });
    const result = await post('/api/rag/documents', {
      filename: file.name,
      content_base64: encoded
    });
    $('rag-progress').textContent =
      `${result.reused ? 'Existing document found' : 'Document stored'} · ${result.chunks} chunks. Build the vector index before asking questions.`;
    $('rag-upload-form').reset();
    $('rag-answer').hidden = true;
  });
}));
$('rag-index').addEventListener('click', guarded(async () => {
  await runRagTask(
    'Requesting document embeddings and writing the Chroma index. Large documents can take several calls…',
    async () => {
      const result = await post('/api/rag/index', {});
      $('rag-progress').textContent =
        `Index ready: ${result.indexed_now} new vectors, ${result.total_chunks} total chunks · ${result.duration_ms} ms.`;
    });
}));
async function askRag(generate) {
  if (!$('rag-ask-form').reportValidity()) return;
  await runRagTask(generate ?
    'Embedding the question, retrieving passages and requesting a grounded answer…' :
    'Embedding the question and retrieving passages…', async () => {
      $('rag-answer').hidden = true;
      const result = await post(generate ? '/api/rag/ask' : '/api/rag/retrieve', {
        question: $('rag-question').value,
        scope: $('rag-scope').value,
        top_k: 4
      });
      $('rag-answer').innerHTML = renderRagAnswer(result);
      $('rag-answer').hidden = false;
      $('rag-progress').textContent = generate ?
        'Response received. Expand the sources to inspect the supporting passages.' :
        'Retrieval complete. No LLM answer was generated.';
    });
}
$('rag-ask-form').addEventListener('submit', guarded(async e => {
  e.preventDefault();
  await askRag(true);
}));
$('rag-retrieve').addEventListener('click', guarded(() => askRag(false)));
$('rag-documents').addEventListener('click', guarded(async e => {
  const inspect = e.target.closest('[data-chunks]');
  const remove = e.target.closest('[data-remove-doc]');
  if (inspect) {
    const chunks = await api('/api/rag/documents/' + encodeURIComponent(inspect.dataset.chunks) +
      '/chunks');
    $('rag-chunks').innerHTML = chunks.map(c =>
      `<article><b>Chunk ${c.ordinal}${c.page ? ' · page '+c.page : ''}</b><pre>${esc(c.text)}</pre></article>`
      ).join('');
    $('rag-chunk-panel').hidden = false;
    $('rag-chunk-panel').open = true;
  } else if (remove && !ragBusy) {
    await api('/api/rag/documents/' + encodeURIComponent(remove.dataset.removeDoc), {
      method: 'DELETE'
    });
    $('rag-chunk-panel').hidden = true;
    $('rag-answer').hidden = true;
    await refreshRag();
  }
}));

init().catch(e => error('Could not load the workspace: ' + e.message));

const themeToggle = $('theme-toggle');
function setTheme(light) {
  document.documentElement.dataset.theme = light ? 'light' : 'dark';
  themeToggle.textContent = light ? 'Dark mode' : 'Light mode';
  localStorage.setItem('orchestra-theme', light ? 'light' : 'dark');
}
setTheme(localStorage.getItem('orchestra-theme') === 'light');
themeToggle.addEventListener('click', () => setTheme(document.documentElement.dataset.theme !== 'light'));
