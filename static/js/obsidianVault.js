// obsidianVault.js — Browse and open Obsidian vault files in the document editor
//
// Uses the Odysseus Obsidian REST API proxy:
//   GET /api/codex/obsidian/vault         → flat list of all file paths
//   GET /api/codex/obsidian/files/{path}  → read file content
//   GET /api/codex/obsidian/search?query= → search vault
//
// Opening a file creates a new document via POST /api/documents and opens it
// in the document editor.

import documentModule from './document.js';
import sessionModule from './sessions.js';

const API = window.location.origin;
let _modal = null;
let _allFiles = [];   // flat list of paths from vault list
let _tree = {};       // {folder: {subfolders: {}, files: []}}
let _openFolders = new Set();

// ── Public ────────────────────────────────────────────────────────────────────

export async function openPanel() {
  if (_modal) { _modal.classList.remove('hidden'); return; }
  _build();
  _loadVault();
}

export function closePanel() {
  if (_modal) { _modal.classList.add('hidden'); }
}

// ── Build modal ───────────────────────────────────────────────────────────────

function _build() {
  _modal = document.createElement('div');
  _modal.className = 'modal obsidian-vault-modal';
  _modal.id = 'obsidian-vault-modal';
  _modal.innerHTML = `
    <div class="modal-content obsidian-vault-content" role="dialog" aria-label="Obsidian Vault">
      <div class="modal-header obsidian-vault-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.6;flex-shrink:0">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
        <span style="font-weight:600;font-size:13px;">Obsidian Vault</span>
        <span style="flex:1"></span>
        <button id="obsidian-new-note-btn" class="obsidian-tool-btn" title="New note" aria-label="New note">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
        <button id="obsidian-refresh-btn" class="obsidian-tool-btn" title="Refresh vault" aria-label="Refresh">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        </button>
        <button id="obsidian-vault-close" class="close-btn" aria-label="Close" title="Close">✖</button>
      </div>
      <div class="obsidian-vault-search-row">
        <input id="obsidian-search-input" class="obsidian-search-input" type="search" placeholder="Search vault…" autocomplete="off" spellcheck="false" />
      </div>
      <div id="obsidian-vault-body" class="obsidian-vault-body">
        <div class="obsidian-status">Loading vault…</div>
      </div>
    </div>
  `;
  document.body.appendChild(_modal);

  _modal.querySelector('#obsidian-vault-close').addEventListener('click', closePanel);
  _modal.addEventListener('click', e => { if (e.target === _modal) closePanel(); });
  document.addEventListener('keydown', _onKey);

  _modal.querySelector('#obsidian-new-note-btn').addEventListener('click', _newNote);
  _modal.querySelector('#obsidian-refresh-btn').addEventListener('click', () => _loadVault());

  const searchInput = _modal.querySelector('#obsidian-search-input');
  let _searchTimer = null;
  searchInput.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    const q = searchInput.value.trim();
    if (!q) { _renderTree(_tree); return; }
    _searchTimer = setTimeout(() => _doSearch(q), 300);
  });
}

function _onKey(e) {
  if (e.key === 'Escape' && _modal && !_modal.classList.contains('hidden')) {
    closePanel();
  }
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function _loadVault() {
  const body = document.getElementById('obsidian-vault-body');
  if (!body) return;
  body.innerHTML = '<div class="obsidian-status">Loading vault…</div>';
  try {
    const res = await fetch(`${API}/api/codex/obsidian/vault`, { credentials: 'same-origin' });
    if (res.status === 503) {
      body.innerHTML = '<div class="obsidian-status obsidian-status-error">Obsidian not connected.<br>Check <code>OBSIDIAN_API_KEY</code> env var and ensure Obsidian is running with the Local REST API plugin.</div>';
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Obsidian REST API returns {files: ["path/to/file.md", ...]}
    _allFiles = (data.files || []).filter(f => typeof f === 'string' && !f.endsWith('/'));
    _tree = _buildTree(_allFiles);
    _renderTree(_tree);
  } catch (e) {
    body.innerHTML = `<div class="obsidian-status obsidian-status-error">Failed to load vault: ${_esc(e.message)}</div>`;
  }
}

function _buildTree(paths) {
  const root = {};
  for (const p of paths) {
    const parts = p.split('/');
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts[i];
      if (!node[seg]) node[seg] = { _files: [] };
      node = node[seg];
    }
    const fname = parts[parts.length - 1];
    if (!node._files) node._files = [];
    node._files.push({ name: fname, path: p });
  }
  return root;
}

// ── Search ────────────────────────────────────────────────────────────────────

async function _doSearch(q) {
  const body = document.getElementById('obsidian-vault-body');
  if (!body) return;
  body.innerHTML = '<div class="obsidian-status">Searching…</div>';
  try {
    const res = await fetch(`${API}/api/codex/obsidian/search?query=${encodeURIComponent(q)}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Obsidian REST search returns [{filename, score, matches: [{context}]}]
    const results = Array.isArray(data) ? data : (data.results || []);
    if (!results.length) {
      body.innerHTML = '<div class="obsidian-status">No results found.</div>';
      return;
    }
    body.innerHTML = results.map(r => {
      const path = r.filename || r.path || '';
      const name = path.split('/').pop();
      const excerpt = (r.matches && r.matches[0] && r.matches[0].context) ? r.matches[0].context.slice(0, 120) : '';
      return `<div class="obsidian-file-row" data-path="${_esc(path)}">
        <div class="obsidian-file-row-name">${_esc(name)}</div>
        <div class="obsidian-file-row-path">${_esc(path)}</div>
        ${excerpt ? `<div class="obsidian-file-row-excerpt">${_esc(excerpt)}</div>` : ''}
        <button class="obsidian-open-btn" data-path="${_esc(path)}" title="Open in Document Editor">Open in Editor</button>
      </div>`;
    }).join('');
    _wireOpenButtons(body);
  } catch (e) {
    body.innerHTML = `<div class="obsidian-status obsidian-status-error">Search failed: ${_esc(e.message)}</div>`;
  }
}

// ── Tree rendering ────────────────────────────────────────────────────────────

function _renderTree(node, body) {
  const el = body || document.getElementById('obsidian-vault-body');
  if (!el) return;
  if (!Object.keys(node).length && !node._files?.length) {
    el.innerHTML = '<div class="obsidian-status">Vault is empty or no markdown files found.</div>';
    return;
  }
  el.innerHTML = _renderNode(node, '');
  _wireOpenButtons(el);
  el.querySelectorAll('.obsidian-folder-row').forEach(row => {
    row.addEventListener('click', () => {
      const p = row.dataset.path;
      if (_openFolders.has(p)) _openFolders.delete(p);
      else _openFolders.add(p);
      _renderTree(_tree);
    });
  });
}

function _renderNode(node, prefix) {
  let html = '';
  // Folders first (keys that aren't _files)
  const folders = Object.keys(node).filter(k => k !== '_files').sort();
  for (const folder of folders) {
    const path = prefix ? `${prefix}/${folder}` : folder;
    const open = _openFolders.has(path);
    html += `<div class="obsidian-folder-row" data-path="${_esc(path)}">
      <span class="obsidian-folder-arrow">${open ? '▾' : '▸'}</span>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.5;flex-shrink:0"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      <span>${_esc(folder)}</span>
    </div>`;
    if (open) {
      html += `<div class="obsidian-folder-children">${_renderNode(node[folder], path)}</div>`;
    }
  }
  // Files
  for (const file of (node._files || []).sort((a, b) => a.name.localeCompare(b.name))) {
    html += `<div class="obsidian-file-row" data-path="${_esc(file.path)}">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.4;flex-shrink:0"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
      <span class="obsidian-file-row-name">${_esc(file.name)}</span>
      <button class="obsidian-open-btn" data-path="${_esc(file.path)}" title="Open in Document Editor">Open</button>
      <button class="obsidian-delete-btn" data-path="${_esc(file.path)}" title="Delete file">✕</button>
    </div>`;
  }
  return html;
}

// ── Open file in editor ───────────────────────────────────────────────────────

function _wireOpenButtons(container) {
  container.querySelectorAll('.obsidian-open-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const path = btn.dataset.path;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        await _openFile(path);
        btn.textContent = '✓';
        closePanel();
      } catch (err) {
        btn.textContent = '✗';
        btn.title = err.message;
        btn.disabled = false;
        console.error('[obsidian] open failed:', err);
      }
    });
  });
  container.querySelectorAll('.obsidian-delete-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const path = btn.dataset.path;
      const name = path.split('/').pop();
      if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        await _deleteFile(path);
        btn.closest('.obsidian-file-row')?.remove();
        _allFiles = _allFiles.filter(f => f !== path);
        _tree = _buildTree(_allFiles);
      } catch (err) {
        btn.textContent = '✕';
        btn.disabled = false;
        console.error('[obsidian] delete failed:', err);
      }
    });
  });
}

async function _openFile(path) {
  const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, {
    credentials: 'same-origin',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const content = data.content || '';
  const title = path.split('/').pop().replace(/\.md$/i, '');

  // Create a new document via the document API and open it in the editor.
  // Tie it to the current chat session so the backend's active-doc lookup
  // (and owner filter) can find it and inject its content for the LLM.
  const sessionId = sessionModule.getCurrentSessionId ? sessionModule.getCurrentSessionId() : null;
  const docRes = await fetch(`${API}/api/document`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content, language: 'markdown', session_id: sessionId || undefined }),
  });
  if (!docRes.ok) throw new Error(`Document create failed: HTTP ${docRes.status}`);
  const doc = await docRes.json();

  if (documentModule.injectFreshDoc) documentModule.injectFreshDoc(doc);
  else if (documentModule.loadDocument) await documentModule.loadDocument(doc.id || doc.doc_id);
  if (!documentModule.isPanelOpen || !documentModule.isPanelOpen()) documentModule.openPanel();
}

// ── Create / Delete ───────────────────────────────────────────────────────────

async function _newNote() {
  const name = window.prompt('New note name (e.g. "Ideas/my-note.md"):');
  if (!name) return;
  const path = name.endsWith('.md') ? name : `${name}.md`;
  try {
    const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: `# ${path.split('/').pop().replace(/\.md$/i, '')}\n\n` }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await _loadVault();
  } catch (e) {
    alert(`Failed to create note: ${e.message}`);
  }
}

async function _deleteFile(path) {
  const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────────

function _init() {
  const btn = document.getElementById('overflow-obsidian-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      // Close overflow menu if open
      document.getElementById('overflow-menu')?.classList.add('hidden');
      openPanel();
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init);
} else {
  _init();
}

export default { openPanel, closePanel };
