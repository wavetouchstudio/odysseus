// subagentMonitor.js — Live monitor for subagent runs
// Shows active and recent subagent calls with model, status, tool calls, elapsed time.

import { makeWindowDraggable } from './windowDrag.js';
import { snapModalToZone } from './tileManager.js';

const API = window.location.origin;
const POLL_MS = 3000;

let _pollTimer = null;
let _expanded = new Set();   // run ids whose detail row is open
let _dragWired = false;

// ── Open / close ─────────────────────────────────────────────────────────────

export function openSubagentMonitor() {
  const modal = document.getElementById('subagent-monitor-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  _wireDrag();
  _startPolling();
  _refresh();
}

export function closeSubagentMonitor() {
  const modal = document.getElementById('subagent-monitor-modal');
  if (modal) modal.classList.add('hidden');
  _stopPolling();
}

// ── Drag wiring ───────────────────────────────────────────────────────────────

function _wireDrag() {
  if (_dragWired) return;
  const modal = document.getElementById('subagent-monitor-modal');
  const content = modal && modal.querySelector('.modal-content');
  const header = modal && modal.querySelector('.modal-header');
  if (!modal || !content || !header) return;
  _dragWired = true;
  makeWindowDraggable(modal, {
    content,
    header,
    skipSelector: 'button, input',
    enableDock: true,
    enableLeftDock: true,
    onEnterFullscreen: () => {
      snapModalToZone(modal, {
        name: 'fullscreen',
        rect: { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight },
      });
    },
  });
}

// ── Polling ───────────────────────────────────────────────────────────────────

function _startPolling() {
  _stopPolling();
  _pollTimer = setInterval(_refresh, POLL_MS);
}

function _stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

async function _refresh() {
  try {
    const res = await fetch(`${API}/api/subagent/runs`, { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    _render(data.runs || []);
  } catch (_) {}
}

// ── Render ────────────────────────────────────────────────────────────────────

function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _statusIcon(status) {
  if (status === 'running') {
    return '<span class="sa-status-dot sa-running" title="Running">●</span>';
  }
  if (status === 'done') {
    return '<span class="sa-status-dot sa-done" title="Done">✓</span>';
  }
  return '<span class="sa-status-dot sa-failed" title="Failed">✗</span>';
}

function _elapsed(run) {
  if (run.elapsed_s != null) return `${run.elapsed_s}s`;
  if (run.status === 'running') {
    const s = Math.round(Date.now() / 1000 - run.started_at);
    return `${s}s…`;
  }
  return '—';
}

function _toolChips(toolCalls) {
  if (!toolCalls || !toolCalls.length) return '<span style="opacity:0.4">—</span>';
  const seen = new Set();
  return toolCalls.map(tc => {
    const name = tc.tool || '?';
    const key = `${name}:${tc.status}`;
    if (seen.has(key)) return '';
    seen.add(key);
    const cls = tc.status === 'done' ? 'sa-chip sa-chip-done' : 'sa-chip sa-chip-run';
    return `<span class="${cls}">${_esc(name)}</span>`;
  }).join('');
}

function _detailRow(run) {
  const toolRows = (run.tool_calls || []).map((tc, i) => `
    <tr>
      <td style="padding:3px 6px;opacity:0.5;font-size:10px;white-space:nowrap">${_esc(tc.tool)}</td>
      <td style="padding:3px 6px;font-family:monospace;font-size:10px;word-break:break-all;max-width:300px">${_esc((tc.command || '').slice(0, 120))}</td>
      <td style="padding:3px 6px;font-family:monospace;font-size:10px;word-break:break-all;max-width:300px;opacity:0.7">${_esc((tc.output || '').slice(0, 300))}</td>
    </tr>
  `).join('');

  const toolTable = toolRows ? `
    <table style="width:100%;border-collapse:collapse;margin-top:6px">
      <thead><tr>
        <th style="text-align:left;padding:2px 6px;font-size:10px;opacity:0.5;font-weight:600">Tool</th>
        <th style="text-align:left;padding:2px 6px;font-size:10px;opacity:0.5;font-weight:600">Command</th>
        <th style="text-align:left;padding:2px 6px;font-size:10px;opacity:0.5;font-weight:600">Output</th>
      </tr></thead>
      <tbody>${toolRows}</tbody>
    </table>
  ` : '<div style="opacity:0.4;font-size:11px;padding:4px 6px">No tool calls</div>';

  const responseBlock = run.response
    ? `<div style="margin-top:8px"><div style="font-size:10px;opacity:0.5;margin-bottom:3px">Response</div><pre style="font-size:11px;white-space:pre-wrap;word-break:break-word;max-height:120px;overflow-y:auto;background:var(--bg2,#111);border-radius:4px;padding:6px;margin:0">${_esc(run.response)}</pre></div>`
    : '';

  const errorBlock = run.error
    ? `<div style="margin-top:6px;color:var(--red,#f55);font-size:11px">Error: ${_esc(run.error)}</div>`
    : '';

  return `
    <tr class="sa-detail-row" id="sa-detail-${_esc(run.id)}">
      <td colspan="5" style="padding:4px 12px 8px 28px;border-bottom:1px solid var(--border,#333)">
        <div style="font-size:11px;opacity:0.5;margin-bottom:4px">Full prompt</div>
        <pre style="font-size:11px;white-space:pre-wrap;word-break:break-word;max-height:80px;overflow-y:auto;background:var(--bg2,#111);border-radius:4px;padding:6px;margin:0">${_esc(run.prompt)}</pre>
        ${toolTable}
        ${responseBlock}
        ${errorBlock}
      </td>
    </tr>
  `;
}

function _render(runs) {
  const list = document.getElementById('sa-runs-list');
  if (!list) return;

  const badge = document.getElementById('sa-running-badge');
  const running = runs.filter(r => r.status === 'running').length;
  if (badge) {
    badge.textContent = running > 0 ? `${running} running` : '';
    badge.style.display = running > 0 ? '' : 'none';
  }

  if (!runs.length) {
    list.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;opacity:0.4;font-size:12px">No runs yet</td></tr>';
    return;
  }

  const rows = runs.map(run => {
    const detail = _expanded.has(run.id) ? _detailRow(run) : '';
    return `
      <tr class="sa-run-row" data-run-id="${_esc(run.id)}" style="cursor:pointer;border-bottom:1px solid var(--border,#2a2a2a)">
        <td style="padding:6px 8px;white-space:nowrap">${_statusIcon(run.status)}</td>
        <td style="padding:6px 8px;font-family:monospace;font-size:11px;white-space:nowrap;max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${_esc(run.model)}">${_esc(run.model)}</td>
        <td style="padding:6px 8px;font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_esc(run.prompt)}">${_esc(run.prompt.slice(0, 80))}</td>
        <td style="padding:6px 8px;font-size:11px">${_toolChips(run.tool_calls)}</td>
        <td style="padding:6px 8px;font-size:11px;white-space:nowrap;opacity:0.6">${_elapsed(run)}</td>
      </tr>
      ${detail}
    `;
  }).join('');
  list.innerHTML = rows;

  list.querySelectorAll('.sa-run-row').forEach(row => {
    row.addEventListener('click', () => {
      const id = row.dataset.runId;
      if (_expanded.has(id)) _expanded.delete(id);
      else _expanded.add(id);
      _render(runs);
    });
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

export function initSubagentMonitor() {
  const btn = document.getElementById('tool-subagent-btn');
  if (btn) btn.addEventListener('click', openSubagentMonitor);

  const closeBtn = document.getElementById('close-subagent-monitor');
  if (closeBtn) closeBtn.addEventListener('click', closeSubagentMonitor);

  const refreshBtn = document.getElementById('sa-refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', _refresh);
}

initSubagentMonitor();
