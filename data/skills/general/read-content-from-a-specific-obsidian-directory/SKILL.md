---
name: read-content-from-a-specific-obsidian-directory
description: Read content from a specific Obsidian directory
version: 1.0.0
category: general
tags: [obsidian, mcp, file_system, data_extraction]
status: published
confidence: 0.95
source: learned
owner: "deadlyjrmint@gmail.com"
created: "2026-06-07T05:29:03Z"
---

## When to Use

The user wants to extract the contents of all files located within a particular subfolder (e.g., 'Game Design') inside an Obsidian vault.

## Procedure

1. Call the listing tool to identify available folders/files at the root of the Obsidian vault.
2. Identify the specific directory name or path for 'Game Design'.
3. List all items within that specific directory to get a list of files.
4. Iterate through each file found in that directory.
5. Execute a read command for every file to retrieve its content. Use list-file tools to identify the target folder and iterate through each file found in that path using read commands.
