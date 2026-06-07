---
name: qna-time
description: QnA_Time
version: 1.0.0
category: general
tags: [Loop, stuck, problem solving, research, fix]
status: published
confidence: 0.95
source: user
owner: "deadlyjrmint@gmail.com"
created: "2026-06-07T08:27:30Z"
---

## When to Use

When repeated strategies fail, abandon internal reasoning loops and reconstruct the problem via step-by-step Q&A with the user.

## Procedure

1. Trigger
2. Activate when:
3. ≥3 failed solution attempts OR
4. persistent loop with no new progress
5. Protocol
6. Reset
7. Stop all reasoning.
8. Mark: [FAILURE RESET: Q&A MODE]
9. Discard current solution path assumptions.
10. Minimal State
11. Output only:
12. Goal (1 line)
13. Key unknowns (1–3 items max)
14. No analysis.
15. Q&A Mode
16. Ask ONE question at a time
17. Wait for response before next question
18. No batching
19. Questions must target missing structure, not solutions.
20. Question Order
21. Exact goal
22. Context
23. Constraints
24. Inputs/data/tools
25. Preferences
26. Rebuild Rule
27. After each answer:
28. Update internal model
29. Do not propose solutions until fully specified
30. Exit Condition
31. Exit when:
32. problem is fully specified
33. no critical unknowns remain
34. Anti-patterns
35. Do NOT:
36. ask multiple questions at once
37. infer missing details silently
38. resume solving early
39. re-enter loop mode prematurely
40. Outcome
41. A fully specified problem ready for fresh solution planning.
