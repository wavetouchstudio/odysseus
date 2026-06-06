---
name: list-obsidian-files
description: List files and folders in the Obsidian vault using MCP tools via subagent
version: 1.0.0
category: general
tags: [obsidian, mcp, listing, vault, files, subagent]
status: active
confidence: 0.9
source: user
owner: "deadlyjrmint@gmail.com"
created: "2026-06-06T00:00:00Z"
---

## When to Use

When you need to know what files or folders exist in the Obsidian vault — before reading a file, checking if a path exists, browsing a folder, or confirming a write landed in the right place.

## Procedure

Two tools are available: `obsidian_list_files_in_vault` (entire vault root) and `obsidian_list_files_in_dir` (specific folder). Both are called via subagent.

### List the entire vault root

```
python scripts/odysseus-dispatch "[obsidian] listvault"
```

Or via app_api:
```
app_api POST /api/subagent
{
  "prompt": "Call obsidian_list_files_in_vault and return all files and folders in the vault root.",
  "model": "gpt-oss:20b",
  "agent": true,
  "tools": ["obsidian_list_files_in_vault"],
  "timeout": 60
}
```

### List a specific folder

```
python scripts/odysseus-dispatch "[obsidian] list TestingArea/"
python scripts/odysseus-dispatch "[obsidian] list 1 Reference/"
python scripts/odysseus-dispatch "[obsidian] list AI/"
```

Or via app_api:
```
app_api POST /api/subagent
{
  "prompt": "Call obsidian_list_files_in_dir with dirpath=\"TestingArea/\" and return all filenames.",
  "model": "gpt-oss:20b",
  "agent": true,
  "tools": ["obsidian_list_files_in_dir"],
  "timeout": 60
}
```

## Pitfalls

- The vault root is `D:\WaveTouchObsidian\WaveTouch Studio\` — Obsidian MCP tools use paths relative to this root, not the project root.
- `obsidian_list_files_in_vault` returns the top-level structure; it does not recurse into subfolders. Use `obsidian_list_files_in_dir` for folder contents.
- Folder names with spaces (e.g. `1 Reference/`) must be passed exactly — do not URL-encode or escape them.
- If a folder returns empty, verify the path spelling; a typo silently returns nothing.

## Verification

The response should be a list of filenames or folder names. If it returns empty or an error, read back the vault root first to confirm the correct folder name.
