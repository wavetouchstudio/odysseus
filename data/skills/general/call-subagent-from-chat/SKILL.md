---
name: call-subagent-from-chat
description: Spawn a new independent agent from within an Odysseus chat session using a shell curl call to /api/subagent
version: 1.0.0
category: general
tags: [orchestration, subagent, shell, curl, agent]
status: active
confidence: 0.97
source: learned
owner: "deadlyjrmint@gmail.com"
created: "2026-06-06"
---

## When to Use

You (the orchestrator model) want to delegate a subtask to a new independent agent without sharing your current conversation context. The new agent runs with MCP tool access and no knowledge of this session.

## Procedure

Use the shell tool to POST to the local `/api/subagent` endpoint. The new agent starts fresh — it does not inherit your context.

```bash
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -H "X-Subagent-Key: $SUBAGENT_SECRET" \
  -d '{
    "prompt": "YOUR_TASK_DESCRIPTION",
    "model": "gpt-oss:20b",
    "agent": true,
    "tools": ["obsidian_get_file_contents", "obsidian_append_content"],
    "timeout": 120
  }'
```

`SUBAGENT_SECRET` is the value set in your `.env` file.

The response is JSON: `{ "response": "...", "model": "...", "elapsed_s": ... }`

Parse the `response` field for the result.

## Parameters

- `prompt` — the full task instruction for the new agent (be explicit and complete; the agent has no prior context)
- `model` — which model to use; defaults to the hierarchy if omitted. Prefer `gpt-oss:20b` for MCP tasks.
- `agent` — `true` to give the agent MCP tool access; `false` (default) for a plain LLM call
- `tools` — list of MCP tool names to scope the agent's access; omit for all tools
- `timeout` — seconds before giving up (default 120; use 600 for devstral)

## Common tool names

- `obsidian_get_file_contents` — read a vault file
- `obsidian_append_content` — write/append to a vault file
- `obsidian_list_files_in_dir` — list folder contents
- `obsidian_simple_search` — keyword search across vault
- `execute_python_code` — run Python in Unreal Editor

## Pitfalls

- The subagent has NO memory of your current conversation. Write the full task in `prompt` — do not assume shared context.
- Do NOT include sensitive data in the prompt (it logs to the subagent result).
- Use `agent: true` for any task that requires tool calls. Without it the model gets no MCP access.
- `SUBAGENT_SECRET` must be forwarded to the container (docker-compose environment section). Without it the key header is ignored and the call returns 401.

## Verification

Check `elapsed_s` and `response` in the JSON. If `response` is empty or missing, the agent failed — retry with a simpler prompt or a different model.
