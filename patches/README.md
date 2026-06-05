# Odysseus Local Patches

Custom changes to Odysseus that need to be re-applied after `git pull`.

---

## Applying After an Update

```
git apply patches/claude-mcp-fixes.patch
```

If upstream changed the same lines (conflict):
```
git apply --3way patches/claude-mcp-fixes.patch
```
Resolve any conflicts, then `git add src/agent_loop.py`.

---

## Patches

### `claude-mcp-fixes.patch`

**File:** `src/agent_loop.py`

Three changes:

1. **`_select_api_tool_schemas` helper (line ~500)**
   MCP tool schemas were being filtered through the same RAG relevance check as built-in tools, causing them to drop out of context whenever the user's message didn't match the tool description. The new helper always appends MCP schemas unconditionally.

2. **`_MCP_USAGE_INSTRUCTIONS` constant + injection (line ~169 / ~1093)**
   Adds explicit decision rules and common sequences for Obsidian and Unreal MCP tools to the system prompt. Injected immediately after the MCP tool schema block so the model sees rules in context. Only injects when MCP tools are actually present.

3. **`stream_agent_loop` filtering block replaced (line ~1659)**
   Old inline if/else replaced with a call to `_select_api_tool_schemas`.

---

## Regenerating the Patch

If you make further edits to `agent_loop.py` and want to update the patch:

```
git diff src/agent_loop.py > patches/claude-mcp-fixes.patch
```
