---
name: list-obsidian-files
description: List files and folders in the Obsidian vault using MCP tools via subagent
version: 1.0.0
category: general
tags: [obsidian, vault, files, subagent]
status: published
confidence: 0.95
source: user
owner: "deadlyjrmint@gmail.com"
created: "2026-06-06T00:00:00Z"
---

## When to Use

Use this skill to identify files or folders in the Obsidian vault before performing actions like reading a file, verifying a write operation, or browsing a directory. Avoid using it for recursive searches or when direct path knowledge is available.

## Procedure

1. ### List the Entire Vault Root **Tool Call:** Use `obsidian_list_files_in_vault` via subagent to retrieve top-level items. **Example via app_api:** ```json { "prompt": "Call obsidian_list_files_in_vault and return all files and folders in the vault root.", "model": "gpt-oss:20b", "agent": true, "tools": ["obsidian_list_files_in_vault"], "timeout": 60 } ``` **Expected Output:** A list of top-level files/folders (e.g., `1 Reference/`, `TestingArea/`, `NewFile.md`). --- ### List a Specific Folder **Tool Call:** Use `obsidian_list_files_in_dir` with the exact folder path (no trailing slash). **Example via app_api:** ```json { "prompt": "Call obsidian_list_files_in_dir with dirpath=\"TestingArea\" and return all filenames.", "model": "gpt-oss:20b", "agent": true, "tools": ["obsidian_list_files_in_dir"], "timeout": 60 } ``` **Example via Script:** ```bash python scripts/odysseus-dispatch "[obsidian] list TestingArea" ``` **Expected Output:** A list of filenames/folders within the specified directory (e.g., `notes.md`, `test.md`). ---

## Pitfalls

- **Path Formatting:** Folder paths must match exactly (e.g., `TestingArea` not `TestingArea/`).
- **Empty Results:** If no items are returned, verify the path spelling or check the vault root first.
- **Tool Availability:** Ensure `obsidian_list_files_in_vault` and `obsidian_list_files_in_dir` are accessible via subagent.

## Verification

- Confirm the output is a structured list of filenames/folders. If empty or erroneous:
- Recheck the vault root to validate the path.
- Ensure the tool is correctly invoked with the exact path. --- **Key Fixes:**
- Updated `created` date to a valid past date.
- Removed `mcp` tag (tool not referenced in body).
- Clarified path formatting (no trailing slashes).
- Simplified tool references to match actual usage.
