---
name: pr-review
description: Review a GitHub pull request or GitLab merge request (fresh review, re-review after a push, or checking that a comment was addressed), and self-review your own branch before opening a PR/MR. Reads the full flow from a worktree at the PR head, drafts formal inline comments, and posts nothing until the user approves. Use for any PR/MR review or before raising a PR/MR.
---

# PR / MR review

"The user" is the developer running the agent. These rules apply to every PR/MR
interaction that reads, verifies or comments on code, including quick checks.

## 1. Check out the PR head in a worktree

Never read the PR's code from the current local branch or from the API diff alone:
the local branch may differ and the diff has no surrounding context.

```bash
gh pr view <n> --json headRefName,headRefOid          # GitLab: glab mr view <n>
git fetch origin <branch>
git worktree add /tmp/pr-<n>-review <head-sha>
```

- Read every file from `/tmp/pr-<n>-review`.
- The worktree is read-only: never commit or push from it.
- When done: `git worktree remove /tmp/pr-<n>-review --force`.

## 2. Review the full flow, not just the diff

For each changed file, open the callers, the callees, the module wiring and any
interface being implemented. Look for:

- logic bugs that only show up in the surrounding context;
- edge cases missed in callers or downstream consumers;
- names that do not match what the variable or function actually does;
- departures from the repo's architecture and patterns (folder layout, module
  boundaries, service/repository/controller split);
- simplifications or optimisations visible only across the whole call chain.

## 3. Draft the comments and wait for approval

Never post anything to GitHub, GitLab or any other platform until the user says so.
Show every proposed comment in full, each with `path:line`, so the user can approve,
edit or drop it.

Comment style (formal, for the public record):
- 2-4 sentences: the problem, its impact, then the requested change. Rationale is
  welcome when it explains why.
- Plain, neutral English; no slang, filler, rhetorical questions or asides.
- No contractions ("does not", "cannot").
- Bullets only for several small sub-issues under one point; no "Two problems:" intros.
- No code dumps or long quotes; point at the line and suggest a short fix inline.

## 4. Post as standalone inline comments only

One finding = one inline comment on its own file and line, even when several share a
file. Nothing above them: no summary, no intro, no review body.

```bash
gh api -X POST repos/<owner>/<repo>/pulls/<n>/comments \
  -f commit_id=<head-sha> -f path=<file> -F line=<n> -f side=RIGHT -f body="..."
```

- `side=LEFT` for removed lines or deleted files. For long bodies use `--input file.json`.
- Lines outside the diff: anchor to the nearest line in a hunk and cite the real line
  numbers in the body, or post a file-level comment (`-f subject_type=file`, no
  `line`/`side`).
- Do not use `/pulls/<n>/reviews` with a `comments[]` array (a COMMENT review requires a
  top-level body) and do not use `gh pr review --body`.
- GitLab: one `glab api -X POST projects/<id>/merge_requests/<n>/discussions` per finding,
  with a `position` (base/start/head SHA, `new_path`, `new_line`).
- To replace wrong comments, list them (`gh api repos/<owner>/<repo>/pulls/<n>/comments`),
  delete each with `gh api -X DELETE repos/<owner>/<repo>/pulls/comments/<id>`, then
  re-post, so there are no duplicates.

## Self-review before raising a PR/MR

Never open a PR/MR straight after writing the code. Review your own branch with the same
rigour as section 2:

1. Read the whole diff, file by file, as if it were someone else's:
   `git diff <default-branch>...HEAD`.
2. Apply the section 2 checklist to it.
3. Check it against the ticket or request: it does exactly what was asked. Remove scope
   creep, debug code, commented-out blocks, stray logs and unused additions.
4. Make sure tests cover the new or changed logic and that the test suite and the
   type-check/build pass.
5. Scan for committed secrets, credentials, tokens, `.env` values or hardcoded config.
6. Fix everything before opening the PR/MR. If something needs a decision, ask the user
   instead of opening it with known problems.

Do not run linters or formatters (Prettier, ESLint, etc.) without asking the user first:
they rewrite many tracked files and bury the real change in noise.
