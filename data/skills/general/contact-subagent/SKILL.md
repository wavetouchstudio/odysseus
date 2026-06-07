---
name: contact-subagent
description: contact-subagent
version: 1.0.0
category: general
tags: [subagent, orchestration, mcp, obsidian, unreal, dispatch, windows, shell]
status: published
confidence: 0.95
source: user
owner: "deadlyjrmint@gmail.com"
created: "2026-06-06T19:24:45Z"
---

## When to Use

When you need to delegate a task to a worker subagent — any time you would call an MCP tool (Obsidian, Unreal), run a task requiring specific tool access, or execute something from the shell. Use instead of curl or subprocess — both fail on Windows due to shell quoting issues.

## Procedure

1. Three methods are available. Use in order of preference.
2. ### Method 1 — app_api Tool (Preferred)
3. Use the `app_api` tool to POST directly to `/api/subagent`. No shell involved, no JSON escaping, no Windows quoting issues.
4. ```
5. app_api POST /api/subagent
6. {
7. "prompt": "Call obsidian_append_content with filepath=\"TestingArea/notes.md\" and content=\"# Hello\"",
8. "model": "gpt-oss:20b",
9. "agent": true,
10. "tools": ["obsidian_append_content"],
11. "timeout": 120,
12. "system": "You are a tool executor. Call the tool immediately with the exact arguments given. No reasoning, no explanation."
13. }
14. ```
15. The X-Subagent-Key header is added automatically when using app_api. The subagent has no session memory — the prompt must be fully self-contained.
16. ### Method 2 — Dispatch Script (MCP Commands)
17. For common Obsidian and Unreal operations. One line, no JSON, no curl required.
18. ```
19. python scripts/odysseus-dispatch "[obsidian] read TestingArea/notes.md"
20. python scripts/odysseus-dispatch "[obsidian] append TestingArea/notes.md | # Heading\n\nContent here"
21. python scripts/odysseus-dispatch "[obsidian] search query"
22. python scripts/odysseus-dispatch "[obsidian] list TestingArea/"
23. python scripts/odysseus-dispatch "[obsidian] listvault"
24. python scripts/odysseus-dispatch "[unreal] exec | import unreal; print(unreal.SystemLibrary.get_engine_version())"
25. python scripts/odysseus-dispatch "[unreal] actors LLM"
26. ```
27. Pipe `|` separates the filepath from content. Everything right of `|` is passed as the content string — newlines allowed.
28. Available commands:
29. `[obsidian] read <filepath>` — read full file
30. `[obsidian] append <filepath> | <content>` — write/append (creates if missing)
31. `[obsidian] search <query>` — keyword search across vault
32. `[obsidian] list [<directory>]` — list folder contents
33. `[obsidian] listvault` — list all files and folders in vault root
34. `[unreal] exec | <python_code>` — run Python in Unreal Editor
35. `[unreal] actors [<name_prefix>]` — list actors in level
36. Always verify after append:
37. ```
38. python scripts/odysseus-dispatch "[obsidian] read <filepath>"
39. ```
40. ### Method 3 — Python urllib (Shell Fallback)
41. When app_api is unavailable and the task is not covered by the dispatch script. Always use Python — never curl.
42. ```python
43. python -c "
44. import json, urllib.request
45. payload = json.dumps({
46. 'prompt': 'Call obsidian_append_content with filepath=TestingArea/notes.md and content=# Hello',
47. 'model': 'gpt-oss:20b',
48. 'agent': True,
49. 'tools': ['obsidian_append_content'],
50. 'timeout': 120,
51. 'system': 'You are a tool executor. Call the tool immediately.'
52. }).encode()
53. req = urllib.request.Request(
54. 'http://localhost:7000/api/subagent',
55. payload,
56. {'Content-Type': 'application/json', 'X-Subagent-Key': 'ody-sub-7f3k9x2mQpLvNwBt'}
57. )
58. print(urllib.request.urlopen(req, timeout=135).read().decode())
59. "
60. ```
61. Why not curl? Single quotes are literal characters on Windows — `curl -d '{"k":"v"}'` sends the quote as the first byte of the body, breaking JSON parsing immediately. Backslash line continuation in cmd.exe also silently drops flags from multiline curl commands.
62. ### SubagentRequest Fields
63. | Field   | Type   | Notes                                                             |
64. |---------|--------|-------------------------------------------------------------------|
65. | prompt  | string | Required. Fully self-contained — subagent has no session memory   |
66. | model   | string | Default: gpt-oss:20b                                              |
67. | system  | string | Optional system prompt override                                   |
68. | agent   | bool   | true = run full agent loop with tools                             |
69. | tools   | list   | Restrict to these tool names only (reduces context bloat)         |
70. | timeout | int    | Seconds before hard kill (default 120)                            |
71. ### Fallback Order
72. If one method fails, try the next:
73. app_api tool
74. Dispatch script (`[server] verb args`)
75. Python urllib
76. Bash/filesystem (write a file the subagent can read)
77. Ask the user
