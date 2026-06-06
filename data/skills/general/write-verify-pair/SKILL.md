---
title: Write-Verify Pair Pattern
version: 1.0.0
tags: pattern, verification, obsidian, file-writing, agent-workflow
---

## Problem

After writing to an external tool (Obsidian, file system, API), the write may silently fail, truncate, or land in the wrong location. Assuming success from the write tool's response alone is unreliable.

## Rule

Every write must be immediately paired with a read-back in the same agent loop.
This applies to single operations and multi-step sequences.

## Single Operation

1. Call the write tool (e.g. obsidian_append_content)
2. Call the read tool on the same target (e.g. obsidian_get_file_contents)
3. Confirm content is present, non-empty, and structurally correct

## Multi-Step Tasks

When a task involves multiple writes, each write must be paired with its own immediate read — do NOT batch all writes and then read at the end.

CORRECT order:
  write1 -> read1 (verify) -> write2 -> read2 (verify)

WRONG order:
  write1 -> write2 -> read1 -> read2

## How to Prompt for This Pattern

Always include both the write tool AND the read tool in the tools list.
Always include this explicit instruction in the prompt:

  "Make two separate tool calls: first use [write_tool] to write,
   then use [read_tool] to read it back and confirm it is complete and correct."

Without the explicit two-call instruction, models tend to reason about what they wrote rather than actually re-reading it.

## Verification Checklist

When reading back, confirm:
- File exists and is non-empty
- Expected top-level structure is present (headings, sections)
- No truncation (content ends where expected)
- Report: PASS or FAIL with specific reason
