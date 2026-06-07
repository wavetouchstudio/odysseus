---
name: clarify-email-rewrite
description: Prompt the user for missing email draft and context before attempting a rewrite
version: 1.0.0
category: communication
status: published
confidence: 0.95
source: teacher-escalation
teacher_model: "gpt-oss:120b@Ollama Cloud"
owner: "deadlyjrmint@gmail.com"
created: "2026-06-07T06:09:05Z"
---

## When to Use

When the user asks to rewrite an email but does not provide the draft or key details

## Procedure

1. Step 1: Respond asking the user to share the current email draft (or the main points they want to convey).
2. Step 2: Ask for the recipient role (e.g., colleague, client, manager) to gauge appropriate formality.
3. Step 3: Ask what the desired outcome of the email is (e.g., request a meeting, follow‑up, deliver news).
4. Step 4: Ask which tone they prefer (formal, friendly, concise, persuasive, etc.).
5. Step 5: Once the user supplies this information, proceed to craft a polished rewrite.

## Pitfalls

- Do not assume the tone or purpose; always ask for clarification.
- Avoid guessing missing content; the rewrite will be inaccurate without the draft.
- Make sure to keep the conversation concise and focused on gathering the needed details.

## Verification

- User provides the draft and answers all three clarification questions.
- You have enough context to produce a rewritten email that matches the requested tone and goal.
