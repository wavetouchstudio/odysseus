# Subagent Model Test Results

All tests run via `POST /api/subagent` with `agent=true`. Date: 2026-06-05.

---

## Model Roster (final)

| Model ID | Provider | Endpoint |
|----------|----------|----------|
| `gpt-oss:20b` | Local Ollama | 10.0.0.175:11434 |
| `hermes3:8b` | Local Ollama | 10.0.0.175:11434 |
| `gemma4:12b` | Local Ollama | 10.0.0.175:11434 |
| `devstral-small-2:latest` | Local Ollama | 10.0.0.175:11434 |
| `devstral-medium-latest` | Mistral API | api.mistral.ai |
| `models/gemini-2.5-flash` | Google API | generativelanguage.googleapis.com |
| `gpt-oss:120b-cloud` | Local Ollama 120B | 10.0.0.175:11434 |
| `gpt-oss:120b` | Ollama Cloud | ollama.com |

**Excluded:** `qwen2.5-coder:7b`, `qwen2.5-coder:14b` — both output tool calls as JSON-in-content text, never as native function calls. Replaced by `hermes3:8b`.

---

## Task 1 — Write to Obsidian (obsidian_append_content)

All 8 models passed. Tool was called and files were created in `TestingArea/`.

| Model | Time | Response style |
|-------|------|----------------|
| gpt-oss:20b | 21s | Planning text then "Done" — file created |
| hermes3:8b | 12s | Clean "successfully appended" |
| gemma4:12b | 19s | Planning text then called tool — file created |
| devstral-small-2 | 56s | "Task completed" |
| devstral-medium-latest | 2.3s | "Content successfully appended" |
| models/gemini-2.5-flash | 3.6s | "I have appended the content" |
| gpt-oss:120b-cloud | 2.9s | "content has been appended" |
| gpt-oss:120b | 3.6s | "content has been appended" |

---

## Task 2 — Read Obsidian + Extract Pending Mechanics (obsidian_get_file_contents)

File: `4 Unreal/Mechanics.md`. Task: return only PLANNED mechanics list.

| Model | Result | Accuracy |
|-------|--------|----------|
| gpt-oss:20b | Full list (44 items) with reasoning narration | ✅ Complete |
| hermes3:8b | Only 2 items returned | ❌ Context truncated or file not fully read |
| gemma4:12b | Full list (44 items) with planning text | ✅ Complete |
| devstral-small-2 | 43 items — missing Raccoon Climbing Jump (052) | ✅ Near complete |
| devstral-medium-latest | Full list (44 items), clean output | ✅ Complete |
| models/gemini-2.5-flash | Full list (44 items), used `*` bullets | ✅ Complete |
| gpt-oss:120b-cloud | Listed BUILT mechanics instead of PLANNED | ❌ Section confusion |
| gpt-oss:120b | Response cut off, same confusion | ❌ Section confusion |

**Finding:** 120B models confused by the long file — they identified the wrong section. hermes3:8b context window likely too small for the full Mechanics.md file.

---

## Task 3 — Spawn Actor in Unreal (spawn_actor)

Each model spawned `LLM[modelname]` as a StaticMeshActor at a unique location.

| Model | Spawned? | Notes |
|-------|----------|-------|
| gpt-oss:20b | ✅ LLMgptoss20b | |
| hermes3:8b | ✅ LLMhermes3 | Cleanest response |
| gemma4:12b | ✅ LLMgemma4 | Planning text first, then tool call |
| devstral-small-2 | ❌ | Empty response — timed out or failed |
| devstral-medium-latest | ✅ LLMdevstralmedium | |
| models/gemini-2.5-flash | ❌ | Refused — "spawn_actor has no mesh param" — correct but didn't spawn |
| gpt-oss:120b-cloud | ✅ LLMgptoss120b | Verbose about function signature |
| gpt-oss:120b | ✅ LLMollamacloud120b | Verbose about function signature |

`LLMdevstralsmall` and `LLMgeminiflash` spawned manually to complete the set.

**Finding:** `spawn_actor` schema shows no `mesh` param — models that received the mesh instruction either ignored it or refused. Gemini was the only model to correctly identify this and explain why, but failed to spawn.

---

## Task 4 — Retrieve Actors from Unreal (find_actors_by_name)

**Tool bug:** `find_actors_by_name` returns `{status, result: {actors: []}}` but MCP layer validates against a plain list schema → all calls fail with pydantic validation error. All models reported empty list.

**Workaround:** Use `get_actors_in_level` + filter by name prefix. Or call `find_actors_by_name` directly via Claude Code's MCP tools (same error appears but the raw result is readable).

---

## Capability Summary

| Capability | Reliable models |
|-----------|-----------------|
| Single explicit tool call | All 8 |
| Read long file + summarise | gpt-oss:20b, gemma4, devstral-medium, gemini-flash |
| Spawn Unreal actor | gpt-oss:20b, hermes3, gemma4, devstral-medium, gpt-oss:120b variants |
| Speed (cloud) | devstral-medium (~2s), gemini-flash (~3s) |
| Speed (local) | hermes3:8b (~10s warm), gpt-oss:20b (~20s) |
| Reliability (local) | hermes3:8b best; devstral-small intermittent |

---

## Infrastructure Fixes Applied (2026-06-05)

1. `supports_tools=True` set in DB for all 11 LLM endpoints — was `None` (upstream gate blocked tool schemas)
2. `_shorten_mcp_schemas()` added to `agent_loop.py` — strips `mcp__serverid__` prefix; required for Google (rejects `__` in function names)
3. `build_headers(ep.api_key, ep.base_url)` arg order fixed in `subagent_routes.py` — was reversed, breaking cloud provider auth
4. `generativelanguage.googleapis` added to `_API_HOSTS` in `agent_loop.py` — Google needs this for `_is_api_model=True`
5. SUBAGENT_HIERARCHY updated: `qwen2.5-coder:7b` → `hermes3:8b`

---

## SUBAGENT_HIERARCHY (current)

```python
SUBAGENT_HIERARCHY = [
    ("localhost:11434", "gpt-oss:20b"),
    ("localhost:11434", "hermes3:8b"),
    ("localhost:11434", "gemma4:12b"),
    ("localhost:11434", "devstral-small-2:latest"),
    ("openrouter.ai",   None),
    ("generativelanguage.googleapis", None),
    ("api.mistral.ai",  None),
]
```
