---
name: resolve-obsidian-path-mismatches
description: Resolves 404 errors in Obsidian by verifying directory names against the root listing.
version: 1.1.0
category: file-system
status: active
confidence: 0.95
source: teacher-escalation
teacher_model: "gemma4:26b@10.0.0.175:11434"
owner: "deadlyjrmint@gmail.com"
created: "2026-06-06T00:05:01Z"
updated: "2026-06-06"
---

## When to Use

When the user asks to access a specific path in Obsidian and the tool returns a 'Not Found' or 404 error.

## Procedure

1. Attempt to call `obsidian_list_files_in_dir(dirpath=USER_REQUESTED_PATH)`.
2. If the result indicates the path was not found (e.g., Error 404), call `obsidian_list_files_in_dir(dirpath='')` to inspect the root directory contents.
3. Compare the user's requested path against the actual names returned in the root listing to identify naming discrepancies (such as numerical prefixes or different casing).
4. Call `obsidian_list_files_in_dir(dirpath=CORRECTED_PATH)` using the verified directory name found in Step 2.

## Pitfalls

- Do not immediately assume a typo; always check the root directory via an empty dirpath to find the true filename.
- Avoid assuming how many levels deep the error might be; the root listing is the source of truth.
- **Known permanent prefixes** — these are hard-coded and will not change. Skip the root-listing step if the target folder matches one of these:

  | Bare name     | Correct vault path  |
  |---------------|---------------------|
  | Game Design   | `3 Game Design`     |
  | Unreal        | `4 Unreal`          |
  | S&Box         | `5 S&Box`           |
  | Blender       | `6 Blender`         |
  | AI            | `AI` (no prefix)    |
  | TestingArea   | `TestingArea` (no prefix) |

## Verification

- Confirm that `obsidian_list_files_in_dir` returns a successful list of files instead of an error message after the correction.
