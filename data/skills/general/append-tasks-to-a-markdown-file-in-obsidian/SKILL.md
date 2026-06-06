---
name: append-tasks-to-a-markdown-file-in-obsidian
description: Append task items to a markdown file in Obsidian using obsidian_append_content
version: 2.0.0
category: general
tags: [obsidian, mcp, markdown, file-edit, automation]
status: active
confidence: 0.97
source: corrected
owner: "deadlyjrmint@gmail.com"
created: "2026-06-05T05:44:35Z"
updated: "2026-06-06"
---

## When to Use

User wants to add new task items to a specific markdown file in their Obsidian vault.

## Procedure

1. Optionally read the file first to verify the correct format: `obsidian_get_file_contents(filepath="path/to/file.md")`
2. Format the new bullet-point entries as markdown, e.g. `- Task Name (ID)`.
3. Call `obsidian_append_content` with the target path and the new lines:

```
obsidian_append_content(
  filepath="4 Unreal/scheduled.md",
  content="- New Task (ID)\n- Another Task (ID)"
)
```

4. Confirm the append succeeded by reading the file back with `obsidian_get_file_contents`.

## Pitfalls

- There is NO save step. `obsidian_append_content` writes immediately — no separate save or commit call is needed.
- Do NOT use `obsidian_patch_content` — known header bug, always use append.
- Use numbered folder prefixes: `3 Game Design`, `4 Unreal`, `5 S&Box`, `6 Blender`.

## Verification

- Read the file back and confirm the new lines appear at the end.
