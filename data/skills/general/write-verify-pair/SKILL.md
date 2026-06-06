---
name: write-verify-pair
version: 1.1.0
category: general
tags: [pattern, verification, obsidian, file-writing, agent-workflow]
status: draft
confidence: 0.95
source: user
owner: "deadlyjrmint@gmail.com"
created: "2026-06-05T00:00:00Z"
---

After writing to an external tool (Obsidian, file system, API), the write may silently fail, truncate, or land in the wrong location. Assuming success from the write tool's response alone is unreliable.

Every write must be immediately paired with a read-back in the same agent loop.
This applies to single operations and multi-step sequences.

1. Call the write tool (e.g. obsidian_append_content)
2. Call the read tool on the same target (e.g. obsidian_get_file_contents)
3. Confirm content is present, non-empty, and structurally correct

When a task involves multiple writes, each write must be paired with its own immediate read — do NOT batch all writes and then read at the end.

CORRECT order:
  write1 -> read1 (verify) -> write2 -> read2 (verify)

WRONG order:
  write1 -> write2 -> read1 -> read2

Always include both the write tool AND the read tool in the tools list.

Use this instruction pattern:

  "Write to [path], then read it back and paste the first 3 lines of what
   was returned. Report PASS if they match the written content, FAIL if not."

### What NOT to do

Do NOT use "make exactly N tool calls" framing. Specifying a count causes
models to spend tokens counting and inventing extra calls to satisfy the
number rather than focusing on the task. The task description defines the
calls — don't add a numeric constraint on top.

Do NOT accept a bare "PASS" with no evidence. If the model doesn't include
actual returned content in its response, it reasoned about the write rather
than re-reading it.

When reading back, confirm:
- File exists and is non-empty
- Expected top-level structure is present (headings, sections)
- No truncation (content ends where expected)
- Model pasted actual returned content — not just declared PASS
- Report: PASS or FAIL with specific reason
