// tailscalePanel.js — Tailscale status side-panel + sidebar quick toggle
//
// Right-side drawer (modeled on obsidianBrowser.js) showing live Tailscale
// connection status with Connect/Disconnect/Refresh controls. Also wires a
// fast quick-toggle switch in the sidebar section header so the user can
// flip Tailscale on/off without opening the panel.
//
// Triggered via #tailscale-section-title (opens panel) and
// #tailscale-quick-toggle (direct up/down).

const API = window.location.origin;

let _panel = null;
let _isOpen = false;
let _busy = false;

// ── Public ───────────────────────────────────────────────────────────────────

export function openPanel() {
  if (!_panel) _build();
  _panel.classList.add('open');
  _isOpen = true;
  _loadStatus();
}

export function closePanel() {
  if (!_panel) return;
  _panel.classList.remove('open');
  _isOpen = false;
}

export function togglePanel() {
  if (_isOpen) closePanel(); else openPanel();
}

export function isPanelOpen() { return _isOpen; }

export default { openPanel, closePanel, togglePanel, isPanelOpen };

// ── Build panel ──────────────────────────────────────────────────────────────

function _build() {
  _panel = document.createElement('div');
  _panel.id = 'tailscale-panel';
  _panel.className = 'obsidian-browser-panel';
  _panel.setAttribute('aria-label', 'Tailscale Status');
  _panel.innerHTML = `
    <div class="obsidian-br-header">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.65;flex-shrink:0">
        <circle cx="12" cy="12" r="3"/>
        <circle cx="4" cy="6" r="2"/><circle cx="20" cy="6" r="2"/>
        <circle cx="4" cy="18" r="2"/><circle cx="20" cy="18" r="2"/>
        <line x1="6" y1="7" x2="10" y2="10"/><line x1="18" y1="7" x2="14" y2="10"/>
        <line x1="6" y1="17" x2="10" y2="14"/><line x1="18" y1="17" x2="14" y2="14"/>
      </svg>
      <span class="obsidian-br-title">Tailscale</span>
      <span style="flex:1"></span>
      <button class="obsidian-br-tool-btn" id="ts-refresh-btn" title="Refresh status">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
      </button>
      <button class="obsidian-br-tool-btn" id="ts-close-btn" title="Close" aria-label="Close panel">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div id="ts-body" class="obsidian-br-body" style="padding:12px;">
      <div class="obsidian-br-status">Loading…</div>
    </div>
  `;
  document.body.appendChild(_panel);

  _panel.querySelector('#ts-close-btn').addEventListener('click', closePanel);
  _panel.querySelector('#ts-refresh-btn').addEventListener('click', () => _loadStatus());

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _isOpen) closePanel();
  });
}

// ── Data ─────────────────────────────────────────────────────────────────────

async function _fetchStatus() {
  const res = await fetch(`${API}/api/auth/tailscale/status`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function _loadStatus() {
  const body = document.getElementById('ts-body');
  if (body) body.innerHTML = '<div class="obsidian-br-status">Loading…</div>';
  try {
    const data = await _fetchStatus();
    if (body) body.innerHTML = _renderStatus(data);
    _syncQuickToggle(data);
  } catch (e) {
    if (body) body.innerHTML = `<div class="obsidian-br-status obsidian-br-status-error">Failed to load status: ${_esc(e.message)}</div>`;
  }
}

function _renderStatus(data) {
  if (!data.installed) {
    return '<div class="obsidian-br-status">Tailscale not installed on this machine.</div>';
  }

  const connected = !!data.running;
  const dotColor = connected ? 'var(--green,#4ade80)' : 'var(--red,#f55)';
  const ips = (data.tailscale_ips || []).join(', ') || '—';

  let html = `
    <div style="display:flex;align-items:center;gap:6px;font-weight:600;margin-bottom:10px;">
      <span style="width:8px;height:8px;border-radius:50%;background:${dotColor};display:inline-block;"></span>
      ${connected ? 'Connected' : 'Not connected'}
      ${data.backend_state ? `<span style="opacity:0.5;font-weight:400;font-size:11px;">(${_esc(data.backend_state)})</span>` : ''}
    </div>
  `;

  if (connected) {
    html += `
      <div style="font-size:12px;line-height:1.7;margin-bottom:12px;">
        <div><strong>Tailnet:</strong> ${_esc(data.tailnet || '—')}</div>
        <div><strong>Hostname:</strong> ${_esc(data.hostname || '—')}</div>
        <div><strong>Tailscale IP:</strong> ${_esc(ips)}</div>
        ${data.dns_name ? `<div><strong>MagicDNS:</strong> ${_esc(data.dns_name)}</div>` : ''}
        <div><strong>Peers online:</strong> ${data.peers_online ?? 0} / ${data.peer_count ?? 0}</div>
      </div>
    `;
  }

  if (data.error) {
    html += `<div class="obsidian-br-status-error" style="font-size:11px;margin-bottom:10px;">${_esc(data.error)}</div>`;
  }

  html += `
    <button id="ts-toggle-btn" class="obsidian-br-action-btn" style="width:100%;padding:6px 10px;font-size:12px;${connected ? 'border-color:var(--red,#f55);color:var(--red,#f55);' : 'border-color:var(--green,#4ade80);color:var(--green,#4ade80);'}">
      ${connected ? 'Disconnect (tailscale down)' : 'Connect (tailscale up)'}
    </button>
  `;

  setTimeout(() => {
    document.getElementById('ts-toggle-btn')?.addEventListener('click', () => _setConnected(!connected));
  }, 0);

  return html;
}

async function _setConnected(connect) {
  if (_busy) return;
  _busy = true;
  const body = document.getElementById('ts-body');
  if (body) body.innerHTML = `<div class="obsidian-br-status">${connect ? 'Connecting…' : 'Disconnecting…'}</div>`;
  try {
    const res = await fetch(`${API}/api/auth/tailscale/${connect ? 'up' : 'down'}`, {
      method: 'POST', credentials: 'same-origin',
    });
    const data = await res.json();
    if (body) body.innerHTML = _renderStatus(data);
    _syncQuickToggle(data);
  } catch (e) {
    if (body) body.innerHTML = `<div class="obsidian-br-status obsidian-br-status-error">Failed: ${_esc(e.message)}</div>`;
  } finally {
    _busy = false;
  }
}

// ── Sidebar quick toggle ─────────────────────────────────────────────────────

function _syncQuickToggle(data) {
  const toggle = document.getElementById('tailscale-quick-toggle');
  if (!toggle) return;
  toggle.checked = !!data.running;
  toggle.disabled = !data.installed;
}

async function _onQuickToggle(e) {
  if (_busy) { e.preventDefault(); return; }
  const wantConnect = e.target.checked;
  _busy = true;
  e.target.disabled = true;
  try {
    const res = await fetch(`${API}/api/auth/tailscale/${wantConnect ? 'up' : 'down'}`, {
      method: 'POST', credentials: 'same-origin',
    });
    const data = await res.json();
    _syncQuickToggle(data);
    if (_isOpen) {
      const body = document.getElementById('ts-body');
      if (body) body.innerHTML = _renderStatus(data);
    }
  } catch (err) {
    console.error('[tailscalePanel] quick toggle failed:', err);
    e.target.checked = !wantConnect;
  } finally {
    e.target.disabled = false;
    _busy = false;
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Init ─────────────────────────────────────────────────────────────────────

function _init() {
  const sectionTitle = document.getElementById('tailscale-section-title');
  if (sectionTitle) sectionTitle.addEventListener('click', togglePanel);

  const quickToggle = document.getElementById('tailscale-quick-toggle');
  if (quickToggle) {
    quickToggle.addEventListener('change', _onQuickToggle);
    _fetchStatus().then(_syncQuickToggle).catch(() => {});
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init);
} else {
  _init();
}
