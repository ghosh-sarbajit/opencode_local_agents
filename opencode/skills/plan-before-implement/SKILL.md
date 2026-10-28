---
name: plan-before-implement
description: Explore the codebase and get an approved implementation plan before editing code. Use for non-trivial tasks with several valid approaches, multi-file changes, unclear requirements, or architectural impact; skip for one-line fixes.
---

# Plan first, then implement

## When to plan
Plan when **any** of these is true:
- a new feature touching several files or modules
- several reasonable approaches with different trade-offs
- unclear requirements, where you'd otherwise be guessing at what the user wants
- changes to architecture, data models, public APIs, or migrations
- the user asks for a plan

Skip it for typo fixes, single obvious bug fixes, or when the user has given precise instructions.

## 1. Explore (read-only; no edits)
- Find the relevant code with grep/glob; read the key files fully, not just the lines that matched.
- Learn the existing patterns you should follow: similar features, helpers, tests, conventions.
- For broad sweeps across many directories, use `task` subagents to explore in parallel and report back only the conclusions.
- Note constraints: test commands, build steps, config, anything that is deployed separately.

## 2. Resolve real ambiguity
Ask only questions the code can't answer and whose answer changes the plan. Batch them into one
message, offer options, and put your recommendation first. Don't ask permission for things that have an obvious default.

## 3. Write the plan
Save it to `plans/<slug>.md` (or show it inline if it's short):

```
# Plan: <goal>

## Context
What exists today and why it is changing (2-4 sentences).

## Approach
The chosen design and why; the alternatives you rejected, in one line each.

## Changes
1. `path/to/file.ts`: what changes
2. `path/to/new_file.ts` (new): purpose
...

## Verification
How you will prove it works: tests to add or run, commands, manual checks.

## Risks / open questions
```

Keep it concrete: real file paths and function names, no filler. Small tasks need small plans.

## 4. Get approval, then execute
- Present the plan and **wait for approval** before editing. Incorporate any feedback.
- Once approved, turn the Changes list into `todowrite` items and work through them in order,
  marking each one complete as you go.
- If reality forces a big deviation, stop and tell the user rather than quietly changing the plan.
- Finish with the verify-change skill.
