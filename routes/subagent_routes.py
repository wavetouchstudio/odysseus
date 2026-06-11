"""Subagent route — one-shot LLM call for external orchestrator use (e.g. Claude Code).

POST /api/subagent
    body: { prompt, system?, model?, timeout?, agent?, tools? }
    returns: { response, model, endpoint, elapsed_s }

Modes:
  agent=false (default) — direct llm_call_async, no tool access, fast
  agent=true            — stream_agent_loop with MCP tool access, scoped to `tools` list

Model resolution:
  - model supplied  → find the first enabled endpoint that has it, call it
  - model omitted   → cascade through SUBAGENT_HIERARCHY until one succeeds

Auth:
  - If SUBAGENT_SECRET env var is set, callers must send X-Subagent-Key: <secret>
  - If unset, open (server binds 127.0.0.1 by default so localhost-only)
"""

import json
import logging
import os
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Set

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import SessionLocal, ModelEndpoint
from src.llm_core import llm_call_async
from src.endpoint_resolver import build_chat_url, build_headers
from src.model_context import get_context_length

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Run registry (in-memory, last 50 runs) ───────────────────────────────────
_MAX_RUNS = 50
_runs: Dict[str, dict] = {}
_run_order: deque = deque()
_HISTORY_PATH = Path(__file__).parent.parent / "data" / "subagent_history.json"


def _load_history() -> None:
    """Populate _runs/_run_order from the persisted history file on startup."""
    if not _HISTORY_PATH.exists():
        return
    try:
        with open(_HISTORY_PATH, encoding="utf-8") as f:
            saved: list = json.load(f)
        for run in saved[-_MAX_RUNS:]:
            rid = run.get("id")
            if rid:
                _runs[rid] = run
                _run_order.append(rid)
    except Exception as e:
        logger.debug("subagent history load skipped: %s", e)


def _persist_run(run: dict) -> None:
    """Append / update a completed run in the history file."""
    try:
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if _HISTORY_PATH.exists():
            with open(_HISTORY_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        # Replace if same id, else append
        ids = {r.get("id") for r in existing}
        if run.get("id") in ids:
            existing = [run if r.get("id") == run.get("id") else r for r in existing]
        else:
            existing.append(run)
        # Keep only last _MAX_RUNS entries
        existing = existing[-_MAX_RUNS:]
        with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("subagent history save skipped: %s", e)


_load_history()


def _new_run(model: str, prompt: str, tools: List[str], agent: bool,
             label: Optional[str] = None) -> Tuple[str, dict]:
    run_id = uuid.uuid4().hex[:8]
    run = {
        "id": run_id,
        "model": model or "auto",
        "prompt": prompt[:300],
        "label": label or None,
        "tools": tools,
        "agent": agent,
        "status": "running",
        "tool_calls": [],
        "response": None,
        "error": None,
        "started_at": time.time(),
        "elapsed_s": None,
    }
    _runs[run_id] = run
    _run_order.append(run_id)
    while len(_run_order) > _MAX_RUNS:
        old = _run_order.popleft()
        _runs.pop(old, None)
    return run_id, run

_FEW_SHOT_PATH = Path(__file__).parent.parent / "data" / "few_shot_examples.json"


def _load_few_shot(tools: List[str]) -> List[Dict]:
    """Return interleaved user/assistant message pairs for the requested tools.

    Read fresh per request so examples can be updated without a server restart.
    One unique example per tool — duplicate user prompts are skipped.
    """
    try:
        with open(_FEW_SHOT_PATH, encoding="utf-8") as f:
            library = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    pairs: List[Dict] = []
    seen: set = set()
    for tool in tools:
        for ex in library.get(tool, []):
            key = ex.get("user", "")[:80]
            if key and key not in seen:
                seen.add(key)
                pairs.append({"role": "user",      "content": ex["user"]})
                pairs.append({"role": "assistant",  "content": ex["assistant"]})
    return pairs

# ── Auth ─────────────────────────────────────────────────────────────────────
_SECRET = os.getenv("SUBAGENT_SECRET", "")


def _is_loopback(req: Request) -> bool:
    """True for direct loopback connections — no proxy-forwarding headers."""
    client = getattr(req, "client", None)
    host = (client.host if client else "") or ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        return False
    _PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-real-ip",
                      "cf-connecting-ip", "cf-ray", "forwarded")
    return not any(req.headers.get(h) for h in _PROXY_HEADERS)

_DEFAULT_AGENT_SYSTEM = (
    "Complete the task using the available tools. "
    "Be concise and direct. Do not explain what you are doing — just do it."
)

# ── Per-model minimum timeouts ────────────────────────────────────────────────
# Enforced regardless of what the caller requests. Substring match on model id.
MODEL_MIN_TIMEOUTS: Dict[str, int] = {
    "devstral-small": 600,
}


def _apply_model_timeout(model: str, requested: int) -> int:
    """Return the effective timeout — at least the model's minimum if defined."""
    name = (model or "").lower()
    for key, min_t in MODEL_MIN_TIMEOUTS.items():
        if key in name:
            return max(requested, min_t)
    return requested


# ── Default model hierarchy ───────────────────────────────────────────────────
SUBAGENT_HIERARCHY: List[Tuple[str, Optional[str]]] = [
    ("10.0.0.175:11434",              "gemma4:12b"),            # primary model
    ("10.0.0.175:11434",              "gpt-oss:20b"),           # reliable fallback
    ("10.0.0.175:11434",              "hermes:8b"),             # fast warm calls
    ("10.0.0.175:11434",              "devstral-small-2:latest"),# slow but capable
    ("openrouter.ai",                 "openrouter/free"),       # free tier cascade
    ("generativelanguage.googleapis", None),
    ("api.mistral.ai",                None),
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _enabled_llm_endpoints(db) -> List[ModelEndpoint]:
    return (
        db.query(ModelEndpoint)
        .filter(ModelEndpoint.is_enabled == True)
        .filter(ModelEndpoint.model_type != "image")
        .all()
    )


def _endpoint_model_list(ep: ModelEndpoint) -> List[str]:
    cached = json.loads(ep.cached_models or "[]")
    pinned = json.loads(ep.pinned_models or "[]")
    hidden = set(json.loads(ep.hidden_models or "[]"))
    seen: set = set()
    result = []
    for m in pinned + cached:
        if m not in seen and m not in hidden:
            seen.add(m)
            result.append(m)
    return result


def _resolve_to_triple(ep: ModelEndpoint, model: str) -> Tuple[str, str, Dict]:
    url     = build_chat_url(ep.base_url)
    headers = build_headers(ep.api_key or "", ep.base_url)
    return url, model, headers


def _find_for_model(db, model: str) -> Optional[Tuple[str, str, Dict]]:
    for ep in _enabled_llm_endpoints(db):
        if model in _endpoint_model_list(ep):
            return _resolve_to_triple(ep, model)
    return None


def _build_hierarchy_candidates(db) -> List[Tuple[str, str, Dict]]:
    endpoints = _enabled_llm_endpoints(db)
    candidates = []
    for base_sub, preferred in SUBAGENT_HIERARCHY:
        for ep in endpoints:
            if base_sub.lower() not in (ep.base_url or "").lower():
                continue
            available = _endpoint_model_list(ep)
            if preferred:
                if preferred not in available:
                    continue
                model = preferred
            elif available:
                model = available[0]
            else:
                continue
            candidates.append(_resolve_to_triple(ep, model))
            break
    return candidates


def _get_admin_owner() -> Optional[str]:
    """Return the first admin username so the agent loop grants full tool access."""
    try:
        from core.auth import AuthManager
        auth = AuthManager()
        if not auth.is_configured:
            return None  # single-user mode — no owner needed
        for user in auth.list_users():
            if user.get("is_admin"):
                return user["username"]
    except Exception:
        pass
    return None


async def _run_agent(url: str, model: str, messages: list,
                     headers: dict, tools: List[str], timeout: int,
                     run: Optional[dict] = None) -> str:
    """Run stream_agent_loop and collect the final text response."""
    from src.agent_loop import stream_agent_loop

    relevant: Optional[Set[str]] = set(tools) if tools else None
    owner = _get_admin_owner()
    chunks = []
    async for chunk in stream_agent_loop(
        url, model, messages,
        headers=headers,
        temperature=0.3,
        max_tokens=0,
        max_rounds=6,
        owner=owner,
        relevant_tools=relevant,
        context_length=get_context_length(url, model),
    ):
        if not chunk.startswith("data: "):
            continue
        raw = chunk[6:].strip()
        if raw in ("[DONE]", ""):
            continue
        try:
            data = json.loads(raw)
            logger.info("[subagent-debug] event: %s", json.dumps(data)[:200])
            etype = data.get("type")
            if run is not None:
                if etype == "tool_start":
                    run["tool_calls"].append({
                        "tool": data.get("tool", ""),
                        "command": (data.get("command") or "")[:120],
                        "status": "running",
                        "output": None,
                    })
                elif etype == "tool_output":
                    tool_name = data.get("tool", "")
                    for tc in reversed(run["tool_calls"]):
                        if tc["tool"] == tool_name and tc["status"] == "running":
                            tc["status"] = "done"
                            out = data.get("output") or ""
                            tc["output"] = out[:400] if out else None
                            break
            delta = data.get("delta", "")
            if delta:
                chunks.append(delta)
                # Update in-memory response so polling frontend sees live progress
                if run is not None:
                    run["response"] = "".join(chunks)
        except (json.JSONDecodeError, AttributeError):
            logger.info("[subagent-debug] raw chunk: %s", repr(raw[:200]))

    return "".join(chunks).strip()


# ── Route ─────────────────────────────────────────────────────────────────────
class SubagentRequest(BaseModel):
    prompt:  str
    system:  Optional[str] = None
    model:   Optional[str] = None
    timeout: int = 120
    agent:   bool = False
    tools:   List[str] = []
    label:   Optional[str] = None   # user-visible job name shown in the monitor


@router.get("/api/subagent/runs")
async def get_subagent_runs(req: Request):
    """Return the last N subagent runs, newest first."""
    runs = [_runs[rid] for rid in reversed(list(_run_order)) if rid in _runs]
    return {"runs": runs}


@router.delete("/api/subagent/runs")
async def clear_subagent_runs(req: Request):
    """Clear all in-memory subagent run history."""
    _runs.clear()
    _run_order.clear()
    try:
        if _HISTORY_PATH.exists():
            _HISTORY_PATH.write_text("{}", encoding="utf-8")
    except Exception:
        pass
    return {"cleared": True}


@router.post("/api/subagent")
async def subagent(req: Request):
    # Loopback callers (e.g. LLM agent using shell/curl) bypass the key check —
    # the server binds to 127.0.0.1 by default so localhost is the trust boundary.
    # External callers must still supply X-Subagent-Key when SUBAGENT_SECRET is set.
    if _SECRET and req.headers.get("X-Subagent-Key", "") != _SECRET:
        if not _is_loopback(req):
            raise HTTPException(401, "Missing or invalid X-Subagent-Key")

    # ── Parse body, unwrapping {"body": {...}} if the LLM added a spurious wrapper ──
    # gpt-oss:20b misreads FastAPI's loc:["body"] validation error as meaning it
    # needs to add a top-level "body" key. Accept both formats transparently.
    try:
        raw = await req.json()
    except Exception as exc:
        raise HTTPException(
            400,
            f"Could not parse request body as JSON: {exc}. "
            'Expected: {"prompt": "...", "model": "...", ...}'
        )
    if not isinstance(raw, dict):
        raise HTTPException(
            400,
            'Request body must be a JSON object. '
            'Expected: {"prompt": "...", "model": "...", ...}'
        )
    if "body" in raw and "prompt" not in raw and isinstance(raw["body"], dict):
        raw = raw["body"]
    try:
        body = SubagentRequest(**raw)
    except Exception as exc:
        raise HTTPException(
            422,
            f"Invalid subagent request: {exc}. "
            "Required: prompt (str). "
            "Optional: system, model, timeout (int), agent (bool), tools (list)."
        )

    sys_content = body.system or (_DEFAULT_AGENT_SYSTEM if body.agent else None)
    messages = []
    if sys_content:
        messages.append({"role": "system", "content": sys_content})
    if body.agent and body.tools:
        messages.extend(_load_few_shot(body.tools))
    messages.append({"role": "user", "content": body.prompt})

    db = SessionLocal()
    try:
        if body.model:
            result = _find_for_model(db, body.model)
            if not result:
                raise HTTPException(404, f"Model '{body.model}' not found in any enabled endpoint")
            candidates = [result]
        else:
            # Check for a user-configured override before falling back to hierarchy
            from src.settings import get_setting
            _override = (get_setting("subagent_model_override") or "").strip()
            if _override:
                _ov_result = _find_for_model(db, _override)
                candidates = [_ov_result] if _ov_result else []
            if not _override or not candidates:
                candidates = _build_hierarchy_candidates(db)
            if not candidates:
                raise HTTPException(503, "No models available in subagent hierarchy")
    finally:
        db.close()

    last_err: Optional[Exception] = None
    for url, model, headers in candidates:
        run_id, run = _new_run(model, body.prompt, body.tools, body.agent, label=body.label)
        t0 = time.monotonic()
        effective_timeout = _apply_model_timeout(model, body.timeout)
        try:
            if body.agent:
                response = await _run_agent(url, model, messages, headers,
                                            body.tools, effective_timeout, run=run)
            else:
                response = await llm_call_async(
                    url, model, messages,
                    headers=headers,
                    timeout=effective_timeout,
                    temperature=0.3,
                )
            elapsed = round(time.monotonic() - t0, 2)
            run["status"] = "done"
            run["response"] = response[:800]
            run["elapsed_s"] = elapsed
            _persist_run(run)
            return {
                "response":  response,
                "model":     model,
                "endpoint":  url,
                "elapsed_s": elapsed,
                "agent":     body.agent,
                "run_id":    run_id,
            }
        except Exception as e:
            run["status"] = "failed"
            run["error"] = str(e)[:200]
            run["elapsed_s"] = round(time.monotonic() - t0, 2)
            _persist_run(run)
            logger.warning("[subagent] %s @ %s failed: %s", model, url, e)
            last_err = e

    raise HTTPException(503, f"All subagent candidates failed. Last error: {last_err}")


@router.post("/api/subagent/runs/{run_id}/format-to-doc")
async def format_run_to_doc(run_id: str, req: Request):
    """Format a subagent run's prompt/response into a markdown document via the utility LLM."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")

    parts = [f"**Prompt**\n\n{run['prompt']}"]
    if run.get("tool_calls"):
        tool_lines = []
        for tc in run["tool_calls"]:
            line = f"- **{tc.get('tool', '?')}**"
            if tc.get("command"):
                line += f": `{tc['command'][:200]}`"
            if tc.get("output"):
                line += f"\n  → {tc['output'][:300]}"
            tool_lines.append(line)
        parts.append("**Tool Calls**\n\n" + "\n".join(tool_lines))
    if run.get("response"):
        parts.append(f"**Response**\n\n{run['response']}")
    if run.get("error"):
        parts.append(f"**Error**\n\n{run['error']}")

    run_text = "\n\n---\n\n".join(parts)
    model_label = run.get("model", "agent")
    import datetime as _dt
    ts = run.get("started_at")
    date_str = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""

    from src.endpoint_resolver import resolve_endpoint
    from src.llm_core import llm_call_async

    url = model = headers = None
    for role_key in ("utility", "default", "chat"):
        url, model, headers = resolve_endpoint(role_key)
        if url and model:
            break
    if not url:
        raise HTTPException(503, "No LLM endpoint available for formatting")

    formatting_prompt = (
        "You are a document formatter. Convert the following AI agent run into a "
        "clean, well-structured markdown document suitable for reference. "
        "Organise it with clear headings, preserve all important details and outputs, "
        "and make it easy to scan. Output only the formatted markdown — no preamble.\n\n"
        f"Model: {model_label} | Time: {date_str}\n\n{run_text}"
    )

    try:
        formatted = await llm_call_async(
            url, model,
            [{"role": "user", "content": formatting_prompt}],
            temperature=0.2,
            max_tokens=2048,
            headers=headers,
            timeout=60,
        )
    except Exception as e:
        raise HTTPException(502, f"LLM formatting failed: {e}")

    from core.database import SessionLocal, Document, DocumentVersion
    doc_id = str(uuid.uuid4())
    title = f"Agent run {run_id} — {date_str or model_label}"
    db = SessionLocal()
    try:
        doc = Document(
            id=doc_id,
            title=title,
            language="markdown",
            current_content=formatted,
            version_count=1,
            is_active=True,
            archived=False,
        )
        db.add(doc)
        ver = DocumentVersion(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            version_number=1,
            content=formatted,
        )
        db.add(ver)
        db.commit()
        db.refresh(doc)
        result = {
            "id": doc.id,
            "title": doc.title,
            "language": doc.language,
            "current_content": doc.current_content,
            "version_count": doc.version_count,
            "is_active": doc.is_active,
            "archived": doc.archived,
            "session_id": None,
        }
    finally:
        db.close()

    return result


def setup_subagent_routes() -> APIRouter:
    return router
