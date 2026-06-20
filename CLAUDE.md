# WaveTouchOS — Claude Code Context

WaveTouchOS is a local AI assistant platform built on FastAPI. It runs at **http://localhost:7000** and orchestrates LLM calls, tools, memory, skills, Obsidian, and Unreal Engine via MCP.

---

## Auth

The server binds to `127.0.0.1` by default. Loopback callers bypass the key check automatically. If running from a different context, include the header:

```
X-Subagent-Key: ody-sub-7f3k9x2mQpLvNwBt
```

No session cookie is needed for subagent calls from localhost.

---

## Primary Endpoint: POST /api/subagent

This is the main way Claude Code interacts with WaveTouchOS — fire a one-shot LLM task with optional tool access.

```bash
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "your task here",
    "model": "gpt-oss:20b",
    "agent": true,
    "tools": ["obsidian_list_files_in_vault"],
    "timeout": 60
  }'
```

**Fields:**
| Field | Type | Default | Description |
|---|---|---|---|
| `prompt` | string | required | The task or question |
| `system` | string | null | Optional system prompt override |
| `model` | string | null | Specific model to use (see models below) |
| `timeout` | int | 120 | Seconds before timeout |
| `agent` | bool | false | Enable tool access (MCP + native tools) |
| `tools` | list | [] | Which tools to give the agent (only when `agent=true`) |

**Response:**
```json
{ "response": "...", "model": "gpt-oss:20b", "endpoint": "http://...", "elapsed_s": 1.2 }
```

**Model omitted** → WaveTouchOS auto-cascades through its hierarchy:
`gpt-oss:120b` → `Mistral-Small-4-119B` → `qwen3-coder-next` → OpenRouter (free) → `ministral-14b-latest` → `gemma4:12b-it-qat`

---

## Obsidian MCP Tools (use via subagent with agent=true)

Vault root: `D:\WaveTouchObsidian\WaveTouch Studio\`

| Tool name | What it does | Key args |
|---|---|---|
| `obsidian_list_files_in_vault` | List all files in vault root (top-level only) | none |
| `obsidian_list_files_in_dir` | List files in a subdirectory | `dirpath` (relative to vault, e.g. `"1 Reference"`) |
| `obsidian_get_file_contents` | Read a file | `filepath` (relative to vault) |
| `obsidian_append_content` | Append text to a file | `filepath`, `content` |
| `obsidian_simple_search` | Search across vault | `query` |

**Example — read a note:**
```bash
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Call obsidian_get_file_contents with filepath=\"1 Reference/WaveTouchOS Skills Register.md\" and return the full content.",
    "agent": true,
    "tools": ["obsidian_get_file_contents"]
  }'
```

**Example — list vault root:**
```bash
curl -s -X POST http://localhost:7000/api/subagent \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Call obsidian_list_files_in_vault and return all files.",
    "agent": true,
    "tools": ["obsidian_list_files_in_vault"]
  }'
```

---

## mcp_dispatch Shorthand (inside WaveTouchOS agent sessions only)

When the WaveTouchOS internal agent calls the `mcp_dispatch` tool, it accepts one-line shorthand:

```
[obsidian] read 1 Reference/WaveTouchOS Skills Register.md
[obsidian] append 1 Reference/MyNote.md  some text to add
[obsidian] search keyword
[obsidian] list 1 Reference
[obsidian] listvault
[unreal] exec print("hello")
[unreal] actors BP_
```

This shorthand is for the WaveTouchOS internal model (gpt-oss:20b) to use in chat. Claude Code should call `/api/subagent` directly with the tool name instead.

---

## Skills API

Skills are reusable procedure documents the WaveTouchOS agent consults.

```bash
# List all skills
curl http://localhost:7000/api/skills

# Get a skill's index (brief)
curl http://localhost:7000/api/skills/index

# Read a skill's full SKILL.md
curl http://localhost:7000/api/skills/{skill_id}/markdown

# Add a skill (POST body: name, description, category, content)
curl -X POST http://localhost:7000/api/skills/add \
  -H "Content-Type: application/json" \
  -d '{"name": "my-skill", "description": "...", "category": "general", "content": "..."}'
```

Skill files live at: `data/skills/{category}/{name}/SKILL.md`

---

## Memory API

```bash
# List memories
curl http://localhost:7000/api/memory

# Add a memory
curl -X POST http://localhost:7000/api/memory \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "pinned": false}'

# Pinned seed memories (loaded every session)
# File: data/memory.seed.json   (currently empty — cleared intentionally)
# File: data/memory.json        (accumulated memories — currently empty)
```

---

## Research API

```bash
# Start a deep research session
curl -X POST http://localhost:7000/api/research/start \
  -H "Content-Type: application/json" \
  -d '{"query": "your research question"}'

# Probe endpoint reachability (returns latency_ms + ok/error)
curl -X POST http://localhost:7000/api/research/probe \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## Session / Chat API

```bash
# List sessions
curl http://localhost:7000/api/sessions

# Send a chat message to an existing session
curl -X POST http://localhost:7000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "message": "..."}'

# Create a new session
curl -X POST http://localhost:7000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-oss:20b"}'
```

---

## Subagent Run History

```bash
# See last 50 subagent runs (useful for debugging)
curl http://localhost:7000/api/subagent/runs
```

---

## Key File Locations

| What | Path |
|---|---|
| App entry point | `app.py` |
| SQLite database | `data/app.db` |
| Settings | `data/settings.json` |
| Skills | `data/skills/{category}/{name}/SKILL.md` |
| Memory (seed) | `data/memory.seed.json` |
| Memory (accumulated) | `data/memory.json` |
| Presets | `data/presets.json` |
| Subagent run history | `data/subagent_history.json` |
| Obsidian vault | `D:\WaveTouchObsidian\WaveTouch Studio\` |

---

## Local Models (Ollama at 10.0.0.175:11434)

The WaveTouchOS subagent uses these models internally. Claude Code does not call Ollama directly — it always goes through `/api/subagent`.

- `gpt-oss:120b` — primary choice; native tool calling, strong reasoning
- `Mistral-Small-4-119B` (`hf.co/unsloth/Mistral-Small-4-119B-2603-GGUF:UD-IQ3_S`) — agentic coding lineage (Devstral), confirmed working well with tools (Obsidian MCP) despite Ollama not listing a `tools` capability for this quant
- `qwen3-coder-next` (`qwen3-coder-next:q4_K_M`) — native tool calling, MoE
- `gemma4:12b-it-qat` — smaller fallback when the above are unavailable

---

## When to use /api/subagent vs direct file editing

- **Obsidian reads/writes** → always via `/api/subagent` with MCP tools (the vault is accessed through the Obsidian MCP server, not the filesystem)
- **WaveTouchOS code changes** → edit files directly (`src/`, `routes/`, `static/`)
- **WaveTouchOS config** → edit `data/settings.json`, `data/presets.json`, `data/memory.seed.json` directly
- **Unreal Engine** → via `/api/subagent` with `execute_python_code` or `get_actors_in_level` tools
