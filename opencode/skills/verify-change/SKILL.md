---
name: verify-change
description: Independently verify that an implemented change actually works before reporting it done, by running it rather than trusting self-checks. Use before claiming completion of any non-trivial change (3+ files, API/backend, infra, or anything user-facing).
---

# Verify before you say "done"

Rule: "the code compiles" and "it looks right" are not verification. Run the actual behaviour.
If you cannot verify, say so plainly; never claim success you didn't observe.

## 1. Define pass criteria
From the original request, write 3–7 checkable statements: "`GET /users?limit=5` returns 5 items",
"`tool --help` lists the new flag", "the old test suite still passes". Include at least one edge or
error case.

## 2. Pick how to verify each one
| Change type | How |
|---|---|
| Library / logic | run the existing test suite plus a targeted new test or a one-off script |
| CLI | run the real command with realistic arguments; check output and exit code |
| HTTP API | start the server, `curl` the endpoints, check status and body |
| Web UI | start the dev server; drive it with Playwright (MCP or script); take a screenshot |
| Config / infra | dry-run or plan mode, a validation command, then a smoke test |

Also run the project's lint, type check and build commands if they exist (check package.json, Makefile or CI config).

## 3. Verify independently
For non-trivial work, hand verification to a fresh `task` subagent. Give it only the
original request, the list of changed files, and the pass criteria, **not** your own claims that it works.
Ask it to return, for each criterion: PASS/FAIL, the exact command it ran, and the relevant output.

## 4. Loop
- FAIL: fix it, then re-verify the failed criteria (and anything the fix might have affected).
- PASS: spot-check by re-running 1–2 of the verifier's commands yourself. A PASS without any
  command output counts as unverified.
- Not verifiable here (needs credentials, hardware or production): report it as **unverified** and
  say exactly how the user can check it.

## 5. Report
```
Verified:
- ✅ criterion: `command` → observed result
Not verified:
- ⚠️ criterion: why, and how to check it
```
Clean up afterwards: stop dev servers, delete temporary files and test data you created.
