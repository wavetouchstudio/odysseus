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


def _new_run(model: str, prompt: str, tools: List[str], agent: bool) -> Tuple[str, dict]:
    run_id = uuid.uuid4().hex[:8]
    run = {
        "id": run_id,
        "model": model or "auto",
        "prompt": prompt[:300],
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
    ("localhost:11434",               "gpt-oss:20b"),           # best content quality, high priority
    ("localhost:11434",               "hermes:8b"),            # fast warm calls, good format
    ("localhost:11434",               "gemma4:12b"),            # best reasoning, inconsistent speed
    ("localhost:11434",               "devstral-small-2:latest"),# slow but capable fallback
    ("openrouter.ai",                 "gpt-oss-120b"),           # free tier cascade
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


@router.get("/api/subagent/runs")
async def get_subagent_runs(req: Request):
    """Return the last N subagent runs, newest first."""
    runs = [_runs[rid] for rid in reversed(list(_run_order)) if rid in _runs]
    return {"runs": runs}


@router.post("/api/subagent")
async def subagent(req: Request, body: SubagentRequest):
    if _SECRET and req.headers.get("X-Subagent-Key", "") != _SECRET:
        raise HTTPException(401, "Missing or invalid X-Subagent-Key")

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
            candidates = _build_hierarchy_candidates(db)
            if not candidates:
                raise HTTPException(503, "No models available in subagent hierarchy")
    finally:
        db.close()

    last_err: Optional[Exception] = None
    for url, model, headers in candidates:
        run_id, run = _new_run(model, body.prompt, body.tools, body.agent)
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


def setup_subagent_routes() -> APIRouter:
    return router
