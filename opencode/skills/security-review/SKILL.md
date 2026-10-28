---
name: security-review
description: Audits a finished diff (current branch, pending changes or a PR) and reports only high-confidence, exploitable vulnerabilities that the diff introduces, filtering out false positives. Use when asked for a security review of changes before merge. For writing secure code while building a feature, use security-and-hardening instead.
---

# Security review of a diff

Goal: the short list of findings a senior security engineer would confidently raise on this PR.
Missing a theoretical issue is better than flooding the report with noise.

## 1. Collect the change (read-only)
```bash
git status
git diff --name-only origin/HEAD...     # or <base>...HEAD / `gh pr diff N --name-only`
git log --no-decorate origin/HEAD...
git diff origin/HEAD...
```
If `origin/HEAD` is missing, use the default branch (`git remote show origin | sed -n 's/.*HEAD branch: //p'`).
Do not run, build or exploit anything; judge by reading code.

## 2. Find candidates (one subagent, or yourself)
Phase A, context: how does the repo already handle auth, input validation, escaping, secrets, and
queries? Which framework protections are in play?
Phase B, compare: where does the new code deviate from those patterns or add attack surface?
Phase C, trace: follow untrusted input from its source to sensitive sinks in each changed file.

Categories to look at:
- **Injection**: SQL/NoSQL, OS command, template, XXE, path traversal, eval, unsafe deserialization (pickle, YAML load, Java serialization)
- **AuthN/AuthZ**: bypass, missing server-side checks, privilege escalation, session/JWT flaws, IDOR
- **Crypto & secrets**: hardcoded credentials, weak algorithms, bad randomness, disabled TLS/cert checks
- **Web**: XSS (reflected/stored/DOM), SSRF that controls host or protocol, CSRF on state-changing endpoints
- **Data exposure**: secrets/PII in logs or responses, debug endpoints, over-broad API output

Only issues **introduced or made reachable by this diff** count.

## 3. Filter false positives (parallel subagents, one per candidate)
Give each verifier the candidate, the relevant code, and these rules. Each returns a confidence score from 1 to 10.

Drop automatically:
- DoS, resource or CPU/memory exhaustion, rate limiting, ReDoS, resource leaks
- missing hardening, best-practice gaps, missing audit logs, missing validation without a security impact
- theoretical races or timing attacks; outdated dependencies (tracked elsewhere)
- memory-safety issues in memory-safe languages; test-only files; docs/markdown
- log spoofing; regex injection; user content in LLM prompts; SSRF that controls only the path
- tabnabbing, XS-Leaks, prototype pollution, open redirect (unless extremely concrete)

Assume trusted unless shown otherwise:
- environment variables, CLI flags, server config
- UUIDs (unguessable)
- React/Angular/Vue output (safe unless `dangerouslySetInnerHTML`, `bypassSecurityTrust*`, `v-html`)
- missing auth checks in client-side code (the server is responsible)
- shell scripts, notebooks and CI workflows: report only with a specific untrusted-input path

Logging secrets, passwords or PII **is** a finding; logging URLs or non-sensitive data is not.

Keep only findings with confidence **≥ 8**. Report MEDIUM only when it is obvious and concrete.
Issues exploitable only from the local network can still be HIGH.

## 4. Report (markdown only)
```
# Vuln 1: <Category>: `path/file.py:42`
* Severity: High | Medium
* Confidence: 9/10
* Description: what is wrong and why it is reachable
* Exploit scenario: concrete attacker steps and input
* Recommendation: specific fix
```
Severity: **High** = directly exploitable (RCE, auth bypass, data breach); **Medium** = needs
specific conditions but has significant impact. If nothing survives the filter, say
"No high-confidence vulnerabilities found in this diff" and list what you checked.
