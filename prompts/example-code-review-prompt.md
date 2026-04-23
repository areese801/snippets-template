---
id: 00000000-0000-0000-0000-000000000004
title: "AI Code Review Prompt"
language: "markdown"
tags: [prompt, code-review, ai, example]
description: "Reusable prompt for asking an AI to review a diff - demonstrates snippet format for prompts/"
created: "2026-03-06"
last_updated: "2026-03-06"
---

Review this code change. Focus on high-confidence findings only — skip
stylistic nits unless they affect readability.

Check for:

1. **Security** — injection, hardcoded secrets, missing input validation,
   unsafe deserialization, authz bypasses.
2. **Correctness bugs** — off-by-one, null/undefined dereferences, race
   conditions, wrong error handling.
3. **Performance** — unnecessary work in hot paths, N+1 queries, missing
   indexes, blocking I/O in async code.
4. **Maintainability** — unclear names, dead code, duplicated logic,
   comments that describe *what* instead of *why*.
5. **Testing gaps** — untested branches, missing edge cases.

For each finding, cite `file:line` and explain the failure mode in one
sentence.
