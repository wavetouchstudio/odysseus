---
name: consolidate-skills
description: Audit and merge redundant or overlapping skills, remove broken ones, and sharpen descriptions
category: general
status: published
confidence: high
source: manual
owner: null
created: 2026-06-06
---

# Consolidate Skills

Use this skill when the skill library has grown messy — duplicate procedures, skills with outdated approaches, or multiple skills that cover the same task differently.

## When to use

- User says "clean up skills" or "consolidate skills"
- You notice skills with overlapping purpose or near-identical names
- Skills reference tools or endpoints that no longer exist
- A skill's approach was superseded by a better method

## How

1. **List all skills**
   ```
   manage_skills action=list
   ```

2. **Read each skill** that looks potentially redundant
   ```
   manage_skills action=view name=<name>
   ```

3. **Identify problems** in each skill:
   - **Duplicate**: two skills teach the same task (keep the better-written one)
   - **Superseded**: skill uses an old method (e.g. raw HTTP where a tool now exists)
   - **Broken**: skill references a tool, endpoint, or model that no longer exists
   - **Scope overlap**: two skills partially cover the same ground — merge into one
   - **Wrong category**: skill is filed under the wrong category

4. **For duplicates/overlaps** — write a merged SKILL.md that:
   - Combines unique content from both
   - Uses the best examples and clearest wording
   - Has a single clear `name` and sharp `description`
   - Delete the originals after the merged one is saved

5. **For broken/superseded skills** — either update the approach or delete if no longer needed:
   ```
   manage_skills action=delete name=<name>
   ```

6. **For scope overlaps** — create one merged skill and delete both originals

## Rules

- Never delete a skill without first checking it has no unique content worth preserving
- Keep the `name` slug short and action-oriented (verb-noun: `list-obsidian-files`, not `how-to-list-files-in-obsidian`)
- A skill's `description` (one line) is what the agent uses to decide whether to fetch it — make it specific enough to be useful as a search hint
- After merging, update the Obsidian Skills Register if one exists: `1 Reference/WaveTouchOS Skills Register.md`

## Quality checklist for a good skill

- [ ] `name` is unique and action-oriented
- [ ] `description` is one line, specific, useful as a search hint
- [ ] `How` section is concrete — code, exact tool calls, field names
- [ ] No references to removed tools or deprecated patterns
- [ ] Pitfalls section covers the most common failure mode
