---
name: create-and-read-files-in-obsidian-via-mcp
description: Create and read markdown files in an Obsidian vault using obsidian_append_content and obsidian_get_file_contents
version: 2.0.0
category: general
tags: [obsidian, mcp, filecreation, automation]
status: active
confidence: 0.97
source: corrected
owner: "deadlyjrmint@gmail.com"
created: "2026-06-05T01:34:19Z"
updated: "2026-06-06"
---

## When to Use

Add or retrieve a markdown file in an Obsidian vault using MCP tools.

## Procedure

1. To create a new file, call `obsidian_append_content` with the target path and content. If the file does not exist, appending creates it automatically.

```
obsidian_append_content(
  filepath="TestingArea/2026-06-04_interactable-ui_blueprint.md",
  content="Your markdown text here"
)
```

2. To read a file back, call `obsidian_get_file_contents` with the same path:

```
obsidian_get_file_contents(
  filepath="TestingArea/2026-06-04_interactable-ui_blueprint.md"
)
```

3. Confirm the returned content matches what was written.

## Pitfalls

- Do NOT use `create_file` — this tool does not exist in the Obsidian MCP server.
- Do NOT use `read_file` — this tool does not exist. Use `obsidian_get_file_contents`.
- Do NOT use `obsidian_patch_content` — known header bug, append only.
- All top-level vault folders use numeric prefixes: `3 Game Design`, `4 Unreal`, `5 S&Box`, `6 Blender`. Never use bare folder names.

## Verification

- `obsidian_get_file_contents` returns the expected content.
