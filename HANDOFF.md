# WaveTouchOS — AI Handoff Procedure

You are a substitute AI assistant working on the WaveTouchOS codebase on behalf of the user. The primary AI (Claude Code) is unavailable. Your job is to make the requested changes carefully and document every decision so Claude can review before pushing.

**Do not push to GitHub.** Stage and commit locally only if confident. Claude will review and push.

---

## Step 1 — Orient yourself

Read these files before touching any code:

1. **`CLAUDE.md`** — WaveTouchOS API reference, file locations, how to call subagent, Obsidian vault path
2. **`git log --oneline -20`** — recent commit history so you understand what was just done
3. **`git status`** — current working tree state

---

## Step 2 — Understand the architecture

WaveTouchOS is a FastAPI app at `http://localhost:7000` backed by SQLite at `data/app.db`.

### Adding or modifying a tool (touch all 4 files in order)

| File | What to change |
|---|---|
| `src/tool_schemas.py` | Add schema to `FUNCTION_TOOL_SCHEMAS` + conversion branch in `function_call_to_tool_block()` |
| `src/agent_tools.py` | Add tool name to `TOOL_TAGS` set + import `do_*` from implementations |
| `src/tool_implementations.py` | Write `do_*` async handler |
| `src/tool_execution.py` | Add `elif tool == "name":` dispatch branch |

### Adding a route

- Routes live in `routes/` — one file per domain (history, sessions, subagent, etc.)
- Registered in `app.py` via `app.include_router(...)`
- FastAPI, Pydantic models for request bodies

### Frontend

- Static files served from `static/`
- JS modules in `static/js/` — ES module imports, no bundler
- Main HTML: `static/index.html`
- Server sets `Cache-Control: no-cache` on `.js/.css/.html` — hard refresh clears browser cache

### Memory & Skills

- Skills: `data/skills/{category}/{name}/SKILL.md` — YAML frontmatter + markdown body
- Memory: `data/memory.seed.json` (pinned, loaded every session), `data/memory.json` (accumulated)
- **Do not add orchestration/identity instructions to memory** — causes role confusion in gpt-oss:20b

### Obsidian

- Vault: `D:\WaveTouchObsidian\WaveTouch Studio\`
- MCP server handles all Obsidian reads/writes — do not write directly via filesystem unless MCP is unavailable
- Skills register: `1 Reference/WaveTouchOS Skills Register.md`

---

## Step 3 — Make the changes

- Edit files directly for code changes
- Keep changes minimal and scoped — no cleanup or refactoring beyond what was asked
- No comments explaining what the code does — only add a comment if the WHY is non-obvious
- Do not add error handling for impossible cases
- Run `python -c "import <module>"` to syntax-check Python files after editing

---

## Step 4 — Document everything in Obsidian

After completing your changes, write a log entry to:

```
D:\WaveTouchObsidian\WaveTouch Studio\1 Reference\Claude Handoff Log.md
```

If the file doesn't exist, create it. Append a new entry using this exact format:

---

```markdown
## Handoff — {DATE} {TIME}

**Requested by:** {user's instruction, verbatim or summarized}
**Status:** complete | partial | blocked

### Files changed
- `path/to/file.py` — {one line: what changed and why}
- `static/js/file.js` — {one line: what changed and why}

### Decisions made
- {Decision}: chose {approach} over {alternative} because {reason}
- {Decision}: ...

### Things for Claude to review
- {Anything uncertain, a judgment call, or a pattern you weren't sure about}
- {Any deviation from the existing code style and why}
- {Any TODO left incomplete and why}

### Concerns
- {Anything that might break, a test to run, a dependency to check}

### Commit message suggestion
{Suggested git commit message in the style of existing commits}
```

---

## Step 5 — Stage (do not push)

If the changes are complete and you are confident:

```bash
git add <specific files>
git status  # verify staged set looks right
```

Do **not** run `git push`. Do **not** amend previous commits. Leave pushing to Claude.

If you are uncertain about any change, leave the file unstaged and note it in the Obsidian log under "Things for Claude to review."

---

## Style rules

- Commit messages: imperative mood, first line ≤72 chars, body explains why not what
- Always include at the end of commit message body:
  `Co-Authored-By: {your model name} <noreply@ai.com>`
- Python: async where the surrounding code is async, no bare `except`, no print() in production paths
- JS: ES modules, no jQuery, match the style of the surrounding file exactly
- No trailing summary comments in code ("# end of function", etc.)
- Do not create markdown documentation files unless explicitly asked

---

## What Claude will do when back

1. Read `1 Reference/Claude Handoff Log.md` in Obsidian
2. Review the diff of staged/unstaged changes
3. Run any checks noted in "Concerns"
4. Push or request revisions

---

## Quick reference

| Task | Command / Path |
|---|---|
| Run server | `uvicorn app:app --reload` (from `d:\AI\odysseus`) |
| Check syntax | `python -c "import routes.history_routes"` |
| Recent commits | `git log --oneline -10` |
| Staged diff | `git diff --cached` |
| Subagent API | `POST http://localhost:7000/api/subagent` |
| Obsidian vault | `D:\WaveTouchObsidian\WaveTouch Studio\` |
| Handoff log | `1 Reference/Claude Handoff Log.md` |
