# Patch: Subagent Route

## What
Adds `POST /api/subagent` — a one-shot LLM call endpoint designed for external
orchestrator use (e.g. Claude Code delegating cheap tasks to a local model).

## Files changed
- `routes/subagent_routes.py` — new route
- `app.py` — import + `include_router` + timeout exemption

## Usage

```bash
# No model specified — cascades through hierarchy automatically
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "List the main components of APickupObject in bullet points."}'

# Specific model
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-oss:20b", "prompt": "...", "system": "You are a UE5 expert."}'

# With auth (if SUBAGENT_SECRET env var is set)
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -H "X-Subagent-Key: your-secret" \
  -d '{"prompt": "..."}'
```

## Response
```json
{
  "response": "...",
  "model": "gpt-oss:20b",
  "endpoint": "http://localhost:11434/v1/chat/completions",
  "elapsed_s": 4.2
}
```

## Model hierarchy (when no model specified)
Tried in order — first success wins:

1. Local Ollama — `gpt-oss:20b` (fast, capable)
2. Local Ollama — `devstral-small-2:latest` (slower, better code tasks)
3. OpenRouter — first available model
4. Google (Gemini) API — first available model
5. Mistral API — first available model

Hierarchy is defined in `SUBAGENT_HIERARCHY` at the top of `subagent_routes.py`.
Edit it directly to reorder or add entries.

## Auth
- Set `SUBAGENT_SECRET` env var to require `X-Subagent-Key: <secret>` on every request
- If unset: no auth (server binds 127.0.0.1 by default, so localhost-only)

## Request body
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `prompt` | string | required | User message |
| `system` | string | null | System prompt |
| `model` | string | null | Specific model; omit to use hierarchy |
| `timeout` | int | 120 | Seconds before giving up on a candidate |
