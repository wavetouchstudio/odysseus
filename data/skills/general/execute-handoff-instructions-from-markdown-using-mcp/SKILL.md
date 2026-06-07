---
name: execute-handoff-instructions-from-markdown-using-mcp
description: Execute handoff instructions from an Obsidian markdown file using append-only MCP tools
version: 2.0.0
category: general
tags: [obsidian, mcp, markdown, automation, handoff]
status: published
confidence: 0.85
source: corrected
owner: "deadlyjrmint@gmail.com"
created: "2026-06-04T23:58:15Z"
---

## When to Use

Apply the actions described in an Obsidian handoff markdown file to the vault (e.g., appending logs, writing summaries to target files).

## Procedure

1. Read the handoff file: `obsidian_get_file_contents(filepath="AI/obsidian_handoff.md")`
2. Parse the file to identify each action block: the operation (append), the target file path, and the content to write.
3. For each action, execute the operation using `obsidian_append_content`: ``` obsidian_append_content( filepath="TARGET_FILE", content="CONTENT_FROM_HANDOFF" ) ```
4. Read each target file back to confirm the content landed: `obsidian_get_file_contents(filepath="TARGET_FILE")`

## Pitfalls

- Do NOT attempt to "mark steps as Done" in the handoff file using `obsidian_patch_content` — that tool has a persistent header bug and must never be used.
- Do NOT call a separate "save" step — `obsidian_append_content` writes immediately.
- If a step requires editing an existing line (not appending), append a corrected version with a note instead.
- Vault folder naming: always use numbered prefixes (`3 Game Design`, `4 Unreal`, etc.).

## Verification

- After each append, confirm with `obsidian_get_file_contents` that the content is present.
- If the handoff file itself needs an update (e.g., logging completion), append a completion note rather than patching.
