---
name: hello-world
description: Responds with a friendly custom "Hello, world!" greeting message. Use ONLY when the user explicitly types "hello world", says "hello world", or directly invokes this skill by name. Do not trigger on generic greetings like "hi" or "hello".
---

# Hello World

## Purpose

This skill makes the agent reply with a warm, slightly enthusiastic "Hello, world!" greeting whenever the user explicitly types the phrase `hello world` (case-insensitive) or asks the agent to invoke the `hello-world` skill.

## When to Apply

Apply this skill ONLY when one of the following is true:

- The user message contains the exact phrase `hello world` (case-insensitive).
- The user explicitly asks the agent to "run the hello-world skill" or similar.

Do NOT apply this skill for:

- Generic greetings such as "hi", "hello", "hey", or "good morning".
- Programming questions that merely mention a hello-world program (use normal coding tools instead).
- Any message that does not contain the phrase `hello world`.

## Response Format

When the trigger is matched, reply with exactly this message and nothing else:

```
Hello, world! Greetings from your Cursor agent — ready to help you build something great today.
```

Rules:

- Output the greeting as plain text (no code block, no extra prose, no emojis).
- Do not call any tools before sending the greeting.
- Do not append follow-up questions or additional explanation.
- After delivering the greeting, end your turn and wait for the user's next instruction.

## Example

**User:** hello world

**Agent:**
```
Hello, world! Greetings from your Cursor agent — ready to help you build something great today.
```

**User:** Can you run the hello-world skill?

**Agent:**
```
Hello, world! Greetings from your Cursor agent — ready to help you build something great today.
```

**User:** hi there

**Agent:** (does NOT apply this skill; responds normally to the greeting)
