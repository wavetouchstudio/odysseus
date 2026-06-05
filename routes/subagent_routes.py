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
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Set

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import SessionLocal, ModelEndpoint
from src.llm_core import llm_call_async
from src.endpoint_resolver import build_chat_url, build_headers

logger = logging.getLogger(__name__)

router = APIRouter()

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

# ── Default model hierarchy ───────────────────────────────────────────────────
SUBAGENT_HIERARCHY: List[Tuple[str, Optional[str]]] = [
    ("localhost:11434",               "gpt-oss:20b"),           # best content quality, high priority
    ("localhost:11434",               "hermes:8b"),            # fast warm calls, good format
    ("localhost:11434",               "gemma4:12b"),            # best reasoning, inconsistent speed
    ("localhost:11434",               "devstral-small-2:latest"),# slow but capable fallback
    ("openrouter.ai",                 None),                    # free tier cascade
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
                     headers: dict, tools: List[str], timeout: int) -> str:
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
    ):
        if not chunk.startswith("data: "):
            continue
        raw = chunk[6:].strip()
        if raw in ("[DONE]", ""):
            continue
        try:
            data = json.loads(raw)
            logger.info("[subagent-debug] event: %s", json.dumps(data)[:200])
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
        t0 = time.monotonic()
        try:
            if body.agent:
                response = await _run_agent(url, model, messages, headers,
                                            body.tools, body.timeout)
            else:
                response = await llm_call_async(
                    url, model, messages,
                    headers=headers,
                    timeout=body.timeout,
                    temperature=0.3,
                )
            return {
                "response":  response,
                "model":     model,
                "endpoint":  url,
                "elapsed_s": round(time.monotonic() - t0, 2),
                "agent":     body.agent,
            }
        except Exception as e:
            logger.warning("[subagent] %s @ %s failed: %s", model, url, e)
            last_err = e

    raise HTTPException(503, f"All subagent candidates failed. Last error: {last_err}")


def setup_subagent_routes() -> APIRouter:
    return router
