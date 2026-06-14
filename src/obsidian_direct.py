"""Direct client for the Obsidian Local REST API plugin.

Bypasses the MCP obsidian server (and its agent-loop round trip) for vault
file operations. Shared by the /obsidian/* HTTP routes (routes/codex_routes.py)
and the obsidian_vault native tool (src/tool_implementations.py).
"""

import os
from typing import Any

import httpx


class ObsidianNotConfigured(RuntimeError):
    """Raised when OBSIDIAN_API_KEY is not set."""


class ObsidianUnavailable(RuntimeError):
    """Raised when the Obsidian Local REST API plugin is unreachable or errors."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _client() -> tuple[str, dict]:
    api_key = os.getenv("OBSIDIAN_API_KEY", "")
    port = os.getenv("OBSIDIAN_PORT", "27123")
    host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")
    if not api_key:
        raise ObsidianNotConfigured("OBSIDIAN_API_KEY not configured")
    base = f"http://{host}:{port}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    return base, headers


async def list_vault() -> list[str]:
    """Recursively list every file path in the vault."""
    base, headers = _client()
    all_files: list[str] = []

    async def _walk(prefix: str, client: httpx.AsyncClient) -> None:
        url = f"{base}/vault/{prefix}" if prefix else f"{base}/vault/"
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            return
        for item in r.json().get("files", []):
            full = f"{prefix}{item}"
            if item.endswith("/"):
                await _walk(full, client)
            else:
                all_files.append(full)

    async with httpx.AsyncClient(timeout=30) as client:
        r0 = await client.get(f"{base}/vault/", headers=headers)
        if r0.status_code in (503, 404):
            raise ObsidianUnavailable(r0.status_code, "Obsidian not connected")
        if r0.status_code != 200:
            raise ObsidianUnavailable(r0.status_code, r0.text)
        for item in r0.json().get("files", []):
            if item.endswith("/"):
                await _walk(item, client)
            else:
                all_files.append(item)

    return all_files


async def read_file(path: str) -> str:
    """Read a vault file as text/markdown."""
    base, headers = _client()
    hdrs = {**headers, "Accept": "text/markdown, application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{base}/vault/{path}", headers=hdrs)
    if r.status_code != 200:
        raise ObsidianUnavailable(r.status_code, r.text)
    return r.text


async def write_file(path: str, content: str) -> None:
    """Create or overwrite a vault file."""
    base, headers = _client()
    hdrs = {**headers, "Content-Type": "text/markdown"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.put(f"{base}/vault/{path}", headers=hdrs, content=content)
    if r.status_code not in (200, 204):
        raise ObsidianUnavailable(r.status_code, r.text)


async def append_file(path: str, content: str) -> None:
    """Append to a vault file (creates it if missing)."""
    base, headers = _client()
    hdrs = {**headers, "Content-Type": "text/markdown"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{base}/vault/{path}", headers=hdrs, content=content)
    if r.status_code not in (200, 204):
        raise ObsidianUnavailable(r.status_code, r.text)


async def delete_file(path: str) -> None:
    """Delete a vault file."""
    base, headers = _client()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.delete(f"{base}/vault/{path}", headers=headers)
    if r.status_code not in (200, 204):
        raise ObsidianUnavailable(r.status_code, r.text)


async def search(query: str, context_length: int = 100) -> Any:
    """Full-text search across the vault."""
    base, headers = _client()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{base}/search/simple/",
            headers=headers,
            params={"query": query, "contextLength": context_length},
        )
    if r.status_code != 200:
        raise ObsidianUnavailable(r.status_code, r.text)
    return r.json()


async def read_file_raw(path: str) -> httpx.Response:
    """Read a vault file's raw bytes (images, PDFs, etc.) with content-type."""
    base, headers = _client()
    hdrs = {k: v for k, v in headers.items() if k.lower() != "accept"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{base}/vault/{path}", headers=hdrs)
    if r.status_code != 200:
        raise ObsidianUnavailable(r.status_code, r.text)
    return r
