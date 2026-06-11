// obsidianBrowser.js — Dedicated Obsidian vault side-panel browser
//
// A right-side drawer that persists open while browsing. Features:
//   • File tree with search (same data as obsidianVault.js modal)
//   • Click file → inline content preview with action buttons
//   • Open in Editor — sends file to doc editor
//   • Chat with AI — loads file into chat context + opens editor
//   • New Note — create file in vault
//   • Delete — remove file from vault
//   • Refresh — reload vault listing
//
// Triggered via #rail-obsidian button in the icon rail.

import documentModule from './document.js';
import sessionModule from './sessions.js';

const API = window.location.origin;

let _panel = null;
let _isOpen = false;
let _allFiles = [];
let _tree = {};
let _openFolders = new Set();
let _expandedFile = null;   // path currently showing inline preview
let _searchTimer = null;

// ── Public ────────────────────────────────────────────────────────────────────

export function openBrowser() {
  if (!_panel) _build();
  _panel.classList.add('open');
  _isOpen = true;
  document.getElementById('rail-obsidian')?.classList.add('active');
  if (!_allFiles.length) _loadVault();
}

export function closeBrowser() {
  if (!_panel) return;
  _panel.classList.remove('open');
  _isOpen = false;
  document.getElementById('rail-obsidian')?.classList.remove('active');
}

export function toggleBrowser() {
  if (_isOpen) closeBrowser(); else openBrowser();
}

export function isBrowserOpen() { return _isOpen; }

export default { openBrowser, closeBrowser, toggleBrowser, isBrowserOpen };

// ── Build panel ───────────────────────────────────────────────────────────────

function _build() {
  _panel = document.createElement('div');
  _panel.id = 'obsidian-browser-panel';
  _panel.className = 'obsidian-browser-panel';
  _panel.setAttribute('aria-label', 'Obsidian Vault Browser');
  _panel.innerHTML = `
    <div class="obsidian-br-header">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.65;flex-shrink:0">
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
      </svg>
      <span class="obsidian-br-title">Obsidian</span>
      <span style="flex:1"></span>
      <button class="obsidian-br-tool-btn" id="obsidian-br-new-btn" title="New note">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
      <button class="obsidian-br-tool-btn" id="obsidian-br-refresh-btn" title="Refresh vault">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
      </button>
      <button class="obsidian-br-tool-btn" id="obsidian-br-close-btn" title="Close" aria-label="Close browser">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="obsidian-br-search-row">
      <input id="obsidian-br-search" class="obsidian-br-search" type="search" placeholder="Search vault…" autocomplete="off" spellcheck="false" />
    </div>
    <div id="obsidian-br-body" class="obsidian-br-body">
      <div class="obsidian-br-status">Loading vault…</div>
    </div>
  `;
  document.body.appendChild(_panel);

  _panel.querySelector('#obsidian-br-close-btn').addEventListener('click', closeBrowser);
  _panel.querySelector('#obsidian-br-new-btn').addEventListener('click', _newNote);
  _panel.querySelector('#obsidian-br-refresh-btn').addEventListener('click', () => _loadVault());

  const searchEl = _panel.querySelector('#obsidian-br-search');
  searchEl.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    const q = searchEl.value.trim();
    if (!q) { _renderTree(_tree); return; }
    _searchTimer = setTimeout(() => _doSearch(q), 300);
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _isOpen) closeBrowser();
  });
}

// ── Data ──────────────────────────────────────────────────────────────────────

async function _loadVault() {
  const body = document.getElementById('obsidian-br-body');
  if (!body) return;
  body.innerHTML = '<div class="obsidian-br-status">Loading vault…</div>';
  _expandedFile = null;
  try {
    const res = await fetch(`${API}/api/codex/obsidian/vault`, { credentials: 'same-origin' });
    if (res.status === 503) {
      body.innerHTML = '<div class="obsidian-br-status obsidian-br-status-error">Obsidian not connected.<br>Check <code>OBSIDIAN_API_KEY</code> and ensure Obsidian is running with the Local REST API plugin.</div>';
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _allFiles = (data.files || []).filter(f => typeof f === 'string' && !f.endsWith('/'));
    _tree = _buildTree(_allFiles);
    _renderTree(_tree);
  } catch (e) {
    body.innerHTML = `<div class="obsidian-br-status obsidian-br-status-error">Failed to load vault: ${_esc(e.message)}</div>`;
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
  const body = document.getElementById('obsidian-br-body');
  if (!body) return;
  body.innerHTML = '<div class="obsidian-br-status">Searching…</div>';
  try {
    const res = await fetch(`${API}/api/codex/obsidian/search?query=${encodeURIComponent(q)}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const results = Array.isArray(data) ? data : (data.results || []);
    if (!results.length) {
      body.innerHTML = '<div class="obsidian-br-status">No results.</div>';
      return;
    }
    body.innerHTML = results.map(r => {
      const path = r.filename || r.path || '';
      const name = path.split('/').pop();
      const excerpt = (r.matches?.[0]?.context || '').slice(0, 150);
      const isImage = _IMAGE_EXT_RE.test(path);
      const actionBtns = isImage
        ? `<button class="obsidian-br-action-btn obsidian-br-insert-btn" data-path="${_esc(path)}" title="Insert into document editor">Insert</button>`
        : `<button class="obsidian-br-action-btn obsidian-br-editor-btn" data-path="${_esc(path)}" title="Open in Editor">Editor</button>
          <button class="obsidian-br-action-btn obsidian-br-chat-btn" data-path="${_esc(path)}" title="Chat with AI about this note">Chat AI</button>`;
      return `<div class="obsidian-br-file-row" data-path="${_esc(path)}">
        <div class="obsidian-br-file-main">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.4;flex-shrink:0"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
          <span class="obsidian-br-file-name">${_esc(name)}</span>
          <span class="obsidian-br-file-path">${_esc(path)}</span>
          <span style="flex:1"></span>
          ${actionBtns}
          <button class="obsidian-br-action-btn obsidian-br-del-btn" data-path="${_esc(path)}" title="Delete">✕</button>
        </div>
        ${excerpt ? `<div class="obsidian-br-excerpt">${_esc(excerpt)}</div>` : ''}
      </div>`;
    }).join('');
    _wireFileRows(body);
  } catch (e) {
    body.innerHTML = `<div class="obsidian-br-status obsidian-br-status-error">Search failed: ${_esc(e.message)}</div>`;
  }
}

// ── Tree rendering ────────────────────────────────────────────────────────────

function _renderTree(node) {
  const el = document.getElementById('obsidian-br-body');
  if (!el) return;
  if (!Object.keys(node).length && !node._files?.length) {
    el.innerHTML = '<div class="obsidian-br-status">Vault is empty or no markdown files found.</div>';
    return;
  }
  el.innerHTML = _renderNode(node, '');
  _wireFileRows(el);
  el.querySelectorAll('.obsidian-br-folder-row').forEach(row => {
    row.addEventListener('click', e => {
      if (e.target.closest('button')) return;
      const p = row.dataset.path;
      if (_openFolders.has(p)) _openFolders.delete(p);
      else _openFolders.add(p);
      _renderTree(_tree);
    });
  });
}

function _renderNode(node, prefix) {
  let html = '';
  const folders = Object.keys(node).filter(k => k !== '_files').sort();
  for (const folder of folders) {
    const path = prefix ? `${prefix}/${folder}` : folder;
    const open = _openFolders.has(path);
    html += `<div class="obsidian-br-folder-row" data-path="${_esc(path)}">
      <span class="obsidian-br-folder-arrow">${open ? '▾' : '▸'}</span>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.5;flex-shrink:0"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      <span class="obsidian-br-folder-name">${_esc(folder)}</span>
    </div>`;
    if (open) html += `<div class="obsidian-br-folder-children">${_renderNode(node[folder], path)}</div>`;
  }
  for (const file of (node._files || []).sort((a, b) => a.name.localeCompare(b.name))) {
    const isExpanded = _expandedFile === file.path;
    const isImage = _IMAGE_EXT_RE.test(file.path);
    const actionBtns = isImage
      ? `<button class="obsidian-br-action-btn obsidian-br-insert-btn" data-path="${_esc(file.path)}" title="Insert into document editor">Insert</button>`
      : `<button class="obsidian-br-action-btn obsidian-br-editor-btn" data-path="${_esc(file.path)}" title="Open in Editor">Editor</button>
        <button class="obsidian-br-action-btn obsidian-br-chat-btn" data-path="${_esc(file.path)}" title="Chat with AI about this note">Chat AI</button>`;
    html += `<div class="obsidian-br-file-row${isExpanded ? ' expanded' : ''}" data-path="${_esc(file.path)}">
      <div class="obsidian-br-file-main">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.4;flex-shrink:0"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
        <span class="obsidian-br-file-name" data-path="${_esc(file.path)}">${_esc(file.name)}</span>
        <span style="flex:1"></span>
        ${actionBtns}
        <button class="obsidian-br-action-btn obsidian-br-del-btn" data-path="${_esc(file.path)}" title="Delete">✕</button>
      </div>
      ${isExpanded ? `<div class="obsidian-br-preview" id="obsidian-br-preview-${_esc(file.path.replace(/\//g,'_'))}"><div class="obsidian-br-preview-loading">Loading…</div></div>` : ''}
    </div>`;
  }
  return html;
}

// Files whose content can't be sensibly opened in the text/markdown editor.
const _BINARY_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|ico|svg|pdf|mp3|mp4|wav|mov|webm|zip|woff2?|ttf|otf)$/i;
// Images get a thumbnail preview + "Insert" (into the doc editor) instead of Editor/Chat AI.
const _IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;

// ── Wire interaction ──────────────────────────────────────────────────────────

function _wireFileRows(container) {
  // File name click → expand/collapse inline preview
  container.querySelectorAll('.obsidian-br-file-name').forEach(span => {
    span.style.cursor = 'pointer';
    span.addEventListener('click', async e => {
      e.stopPropagation();
      const path = span.dataset.path;
      if (!path) return;
      if (_expandedFile === path) {
        _expandedFile = null;
      } else {
        _expandedFile = path;
      }
      _renderTree(_tree);
      if (_expandedFile === path) await _loadPreview(path);
    });
  });

  // Open in Editor
  container.querySelectorAll('.obsidian-br-editor-btn').forEach(btn => {
    if (_BINARY_EXT_RE.test(btn.dataset.path || '')) {
      btn.disabled = true;
      btn.title = 'Binary files cannot be opened in the text editor';
      return;
    }
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const path = btn.dataset.path;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        await _openInEditor(path);
        btn.textContent = '✓';
      } catch (err) {
        btn.textContent = 'Editor';
        btn.disabled = false;
        console.error('[obsidianBrowser] editor open failed:', err);
      }
    });
  });

  // Chat with AI
  container.querySelectorAll('.obsidian-br-chat-btn').forEach(btn => {
    if (_BINARY_EXT_RE.test(btn.dataset.path || '')) {
      btn.disabled = true;
      btn.title = 'Binary files cannot be loaded into chat as text';
      return;
    }
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const path = btn.dataset.path;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        await _callAI(path);
        btn.textContent = 'Chat AI';
        btn.disabled = false;
      } catch (err) {
        btn.textContent = 'Chat AI';
        btn.disabled = false;
        console.error('[obsidianBrowser] chat AI failed:', err);
      }
    });
  });

  // Insert image into doc editor
  container.querySelectorAll('.obsidian-br-insert-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const path = btn.dataset.path;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        await _insertImage(path);
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = 'Insert'; btn.disabled = false; }, 1200);
      } catch (err) {
        btn.textContent = 'Insert';
        btn.disabled = false;
        console.error('[obsidianBrowser] insert image failed:', err);
      }
    });
  });

  // Delete
  container.querySelectorAll('.obsidian-br-del-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const path = btn.dataset.path;
      const name = path.split('/').pop();
      if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return;
      btn.textContent = '…';
      btn.disabled = true;
      try {
        const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, {
          method: 'DELETE', credentials: 'same-origin',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        _allFiles = _allFiles.filter(f => f !== path);
        _tree = _buildTree(_allFiles);
        if (_expandedFile === path) _expandedFile = null;
        _renderTree(_tree);
      } catch (err) {
        btn.textContent = '✕';
        btn.disabled = false;
        console.error('[obsidianBrowser] delete failed:', err);
      }
    });
  });
}

// ── File actions ──────────────────────────────────────────────────────────────

async function _loadPreview(path) {
  const safeId = path.replace(/\//g, '_');
  const previewEl = document.getElementById(`obsidian-br-preview-${safeId}`);
  if (!previewEl) return;
  if (_IMAGE_EXT_RE.test(path)) {
    const src = `${API}/api/codex/obsidian/raw/${encodeURIComponent(path)}`;
    previewEl.innerHTML = `<img class="obsidian-br-preview-img" style="max-width:100%;border-radius:4px;display:block" src="${_esc(src)}" alt="${_esc(path.split('/').pop())}" />`;
    return;
  }
  if (_BINARY_EXT_RE.test(path)) {
    previewEl.innerHTML = '<div class="obsidian-br-status">Binary file — preview not available.</div>';
    return;
  }
  try {
    const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const preview = (data.content || '').slice(0, 800);
    previewEl.innerHTML = `<pre class="obsidian-br-preview-text">${_esc(preview)}${data.content?.length > 800 ? '\n…' : ''}</pre>`;
  } catch (e) {
    previewEl.innerHTML = `<div class="obsidian-br-status-error">Failed to load: ${_esc(e.message)}</div>`;
  }
}

async function _openInEditor(path) {
  const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const title = path.split('/').pop().replace(/\.md$/i, '');
  const sessionId = sessionModule.getCurrentSessionId ? sessionModule.getCurrentSessionId() : null;
  const docRes = await fetch(`${API}/api/document`, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content: data.content || '', language: 'markdown', session_id: sessionId || undefined }),
  });
  if (!docRes.ok) throw new Error(`Document create failed: HTTP ${docRes.status}`);
  const doc = await docRes.json();
  if (documentModule.injectFreshDoc) documentModule.injectFreshDoc(doc);
  else if (documentModule.loadDocument) await documentModule.loadDocument(doc.id || doc.doc_id);
  if (!documentModule.isPanelOpen || !documentModule.isPanelOpen()) documentModule.openPanel();
}

// Fetch a vault image's raw bytes, store it as an upload, and insert a
// markdown image reference into the currently open document (or a new one).
async function _insertImage(path) {
  const name = path.split('/').pop();
  const rawRes = await fetch(`${API}/api/codex/obsidian/raw/${encodeURIComponent(path)}`, { credentials: 'same-origin' });
  if (!rawRes.ok) throw new Error(`HTTP ${rawRes.status}`);
  const blob = await rawRes.blob();

  const fd = new FormData();
  fd.append('files', blob, name);
  const upRes = await fetch(`${API}/api/upload`, { method: 'POST', credentials: 'same-origin', body: fd });
  if (!upRes.ok) throw new Error(`Upload failed: HTTP ${upRes.status}`);
  const upData = await upRes.json();
  const uploaded = upData.files?.[0];
  if (!uploaded) throw new Error('Upload returned no file');

  const md = `![${name}](${API}/api/upload/${uploaded.id})`;
  const docId = documentModule.getCurrentDocId ? documentModule.getCurrentDocId() : null;

  if (docId) {
    const docRes = await fetch(`${API}/api/document/${docId}`, { credentials: 'same-origin' });
    if (!docRes.ok) throw new Error(`Document fetch failed: HTTP ${docRes.status}`);
    const doc = await docRes.json();
    const sep = doc.content && !doc.content.endsWith('\n') ? '\n\n' : '\n';
    const newContent = `${doc.content || ''}${sep}${md}\n`;
    const putRes = await fetch(`${API}/api/document/${docId}`, {
      method: 'PUT', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: newContent }),
    });
    if (!putRes.ok) throw new Error(`Document update failed: HTTP ${putRes.status}`);
    const updated = await putRes.json();
    if (documentModule.handleDocUpdate) {
      documentModule.handleDocUpdate({ doc_id: docId, content: updated.current_content, version: updated.version_count });
    }
  } else {
    const title = name.replace(/\.[^.]+$/, '');
    const sessionId = sessionModule.getCurrentSessionId ? sessionModule.getCurrentSessionId() : null;
    const docRes = await fetch(`${API}/api/document`, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content: md, language: 'markdown', session_id: sessionId || undefined }),
    });
    if (!docRes.ok) throw new Error(`Document create failed: HTTP ${docRes.status}`);
    const doc = await docRes.json();
    if (documentModule.injectFreshDoc) documentModule.injectFreshDoc(doc);
  }
  if (!documentModule.isPanelOpen || !documentModule.isPanelOpen()) documentModule.openPanel();
}

async function _callAI(path) {
  // Open the file in the doc editor
  await _openInEditor(path);

  // Fetch content for context
  const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, { credentials: 'same-origin' });
  const data = res.ok ? await res.json() : { content: '' };
  const title = path.split('/').pop().replace(/\.md$/i, '');
  const excerpt = (data.content || '').slice(0, 600);
  const hasMore = (data.content || '').length > 600;

  // Pre-fill chat input with doc context
  const chatInput = document.getElementById('message');
  if (chatInput) {
    chatInput.value = `Working on note: **${title}**\n\n${excerpt}${hasMore ? '\n…[full note in editor]' : ''}\n\n`;
    chatInput.dispatchEvent(new Event('input', { bubbles: true }));
    chatInput.focus();
    // Place cursor at end
    chatInput.selectionStart = chatInput.selectionEnd = chatInput.value.length;
  }

  closeBrowser();
}

async function _newNote() {
  const name = window.prompt('New note path (e.g. "Ideas/my-note.md"):');
  if (!name) return;
  const path = name.endsWith('.md') ? name : `${name}.md`;
  const title = path.split('/').pop().replace(/\.md$/i, '');
  try {
    const res = await fetch(`${API}/api/codex/obsidian/files/${encodeURIComponent(path)}`, {
      method: 'PUT', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: `# ${title}\n\n` }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await _loadVault();
  } catch (e) {
    alert(`Failed to create note: ${e.message}`);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────────

function _init() {
  const btn = document.getElementById('rail-obsidian');
  if (btn) btn.addEventListener('click', toggleBrowser);

  const sectionTitle = document.getElementById('obsidian-section-title');
  if (sectionTitle) sectionTitle.addEventListener('click', toggleBrowser);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init);
} else {
  _init();
}
