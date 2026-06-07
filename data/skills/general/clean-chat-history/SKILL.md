---
name: clean-chat-history
description: Review and archive or delete old chat sessions while preserving pinned (starred) ones
version: 1.0.0
category: general
status: published
confidence: 0.95
source: manual
owner: "deadlyjrmint@gmail.com"
created: 2026-06-06
---

## When to Use

- User says "clean up chats", "tidy chat history", or "archive old sessions"
- Chat list has grown long and noisy with one-off or resolved conversations
- User wants to keep history lean before a backup or review

# Clean Chat History

Pinned (starred) sessions are protected — never archive or delete them. All other sessions are candidates for cleanup based on age, length, and relevance.

1. **List all sessions**
   ```
   manage_session action=list
   ```
   Note which sessions have `is_important: true` — these are pinned and must be skipped.

2. **Identify cleanup candidates** — sessions that are safe to remove:
   - One-off test conversations (short, no meaningful output)
   - Sessions where the task is fully resolved and documented elsewhere
   - Very old sessions (30+ days) with no recent activity
   - Duplicate sessions covering the same topic

3. **Confirm with the user** before bulk-archiving — show a list of what you plan to remove and ask for approval.

4. **Archive (not delete) by default**
   ```
   manage_session action=archive session_id=<id>
   ```
   Archive is reversible. Only delete if the user explicitly says to delete permanently.

5. **Skip pinned sessions unconditionally**
   A session with `is_important: true` (the ★ star in the UI) must never be archived or deleted, even if it looks old or short.

- Always list and review before acting — never blindly archive everything old
- Pinned = protected, no exceptions
- Archive before delete — give the user a recovery window
- After cleanup, offer to run "Format to Editor" on important sessions before archiving them, so the content is preserved as a document

Users can pin a session by clicking the ★ icon in the session sidebar or using ⋯ → Favorite. Pinned sessions appear with a bookmark indicator and are excluded from all bulk cleanup operations.
