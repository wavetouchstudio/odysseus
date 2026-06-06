---
name: consolidate-memories
description: Review and merge redundant, outdated, or overlapping memories into clean authoritative entries
category: general
status: published
confidence: high
source: manual
owner: null
created: 2026-06-06
---

# Consolidate Memories

Use this skill when memories have grown noisy — duplicates, contradictions, stale entries, or many entries that say roughly the same thing.

## When to use

- User says "clean up memories" or "consolidate memories"
- You notice multiple memories covering the same topic with overlapping content
- Memories contain outdated facts that conflict with newer ones

## How

1. **List all memories**
   ```
   manage_memory action=list
   ```

2. **Identify clusters** — group entries by topic (user preferences, project facts, tool instructions, etc.). Look for:
   - Entries with nearly identical content
   - Entries that partially overlap (one is a subset of another)
   - Entries where a newer one supersedes an older one
   - Entries that are no longer true or relevant

3. **For each cluster, write one merged entry** that:
   - Combines the unique facts from all entries in the cluster
   - Uses the most precise and current version of each fact
   - Removes filler, repetition, and stale information
   - Is written as a clean, concise statement

4. **Delete the originals and add the merged entry**
   ```
   manage_memory action=delete id=<id>
   manage_memory action=add content="<merged content>" pinned=<true if any original was pinned>
   ```

5. **Repeat** until each topic has exactly one entry.

## Rules

- Never delete an entry without first saving its unique facts into the merged version
- If two entries contradict each other, keep the newer/more specific one and note the conflict was resolved
- Pinned entries (seed memories) stay pinned in the merged result
- Do not merge entries from completely different topics just to reduce count — only merge when there is genuine overlap

## Example

Before:
- "User prefers concise replies"
- "User likes short answers, no padding"
- "User dislikes long explanations"

After:
- "User prefers concise replies with no padding or filler"
