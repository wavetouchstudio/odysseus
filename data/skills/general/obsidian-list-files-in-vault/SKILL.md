---
name: obsidian-list-files-in-vault
description: Obsidian_list_files_in_vault
version: 1.0.0
category: general
tags: [Obsidian, vault, MCP, tools, subagent, automation, retrieval]
status: published
confidence: 0.95
source: user
owner: "deadlyjrmint@gmail.com"
created: "2026-06-07T07:58:31Z"
---

## When to Use

When use asks for a list of files in the Obsidian vault

## Procedure

1. ---
2. name: obsidian_list_files_in_vault
3. description: List files and folders in the Obsidian vault using MCP tools via subagent
4. version: 1.0.0
5. category: general
6. tags: [obsidian, vault, files, subagent]
7. status: published
8. confidence: 0.95
9. source: user
10. owner: "deadlyjrmint@gmail.com"
11. created: "2026-06-06T00:00:00Z"
12. ---
13. ## When to Use
14. Use this skill to identify files or folders in the Obsidian vault before performing actions like reading a file, verifying a write operation, or browsing a directory. Avoid using it for recursive searches or when direct path knowledge is available.
15. ## Procedure
16. ### List the Entire Vault Root **Tool Call:** Use `obsidian_list_files_in_vault` via subagent to retrieve top-level items. **Example via app_api:** ```json { "prompt": "Call obsidian_list_files_in_vault and return all files and folders in the vault root.", "model": "gpt-oss:20b", "agent": true, "tools": ["obsidian_list_files_in_vault"], "timeout": 60 } ``` **Expected Output:** A list of top-level files/folders (e.g., `1 Reference/`, `TestingArea/`, `NewFile.md`). --- ### List a Specific Folder **Tool Call:** Use `obsidian_list_files_in_dir` with the exact folder path (no trailing slash). **Example via app_api:** ```json { "prompt": "Call obsidian_list_files_in_dir with dirpath=\"TestingArea\" and return all filenames.", "model": "gpt-oss:20b", "agent": true, "tools": ["obsidian_list_files_in_dir"], "timeout": 60 } ``` **Example via Script:** ```bash python scripts/odysseus-dispatch "[obsidian] list TestingArea" ``` **Expected Output:** A list of filenames/folders within the specified directory (e.g., `notes.md`, `test.md`). ---
17. ## Pitfalls
18. **Path Formatting:** Folder paths must match exactly (e.g., `TestingArea` not `TestingArea/`).
19. **Empty Results:** If no items are returned, verify the path spelling or check the vault root first.
20. **Tool Availability:** Ensure `obsidian_list_files_in_vault` and `obsidian_list_files_in_dir` are accessible via subagent.
21. ## Verification
22. Confirm the output is a structured list of filenames/folders. If empty or erroneous:
23. Recheck the vault root to validate the path.
24. Ensure the tool is correctly invoked with the exact path. --- **Key Fixes:**
25. Updated `created` date to a valid past date.
26. Removed `mcp` tag (tool not referenced in body).
27. Clarified path formatting (no trailing slashes).
28. Simplified tool references to match actual usage.
