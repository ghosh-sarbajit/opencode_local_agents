---
name: conventional-commits
description: Write git commit messages in the Conventional Commits format (type(scope): description, body, BREAKING CHANGE footer) and check them before committing. Use whenever you write, amend or review a commit message.
---

# Conventional Commits

Format (based on qoomon's cheatsheet, https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13,
which follows https://www.conventionalcommits.org/):

```
<type>(<optional scope>)<optional !>: <description>

<optional body>

<optional footer>
```

Separate header, body and footer with one blank line.

## Types
| Type | Use for |
|---|---|
| `feat` | adding, changing or removing a feature of the API or UI |
| `fix` | fixing a bug in API or UI behaviour |
| `refactor` | restructuring code without changing API or UI behaviour |
| `perf` | a refactor whose purpose is performance |
| `style` | formatting, whitespace, semicolons; no behaviour change |
| `test` | adding or correcting tests |
| `docs` | documentation only |
| `build` | build tools, dependencies, project version |
| `ops` | infrastructure, deployment, CI/CD, backups, monitoring |
| `chore` | everything else: initial commit (`chore: init`), `.gitignore`, ... |

If a change needs two types, it is probably two commits.

## Header rules
- **description** is required: imperative present tense ("add", not "added" or "adds"; it completes
  "This commit will ..."), first letter lowercase, no trailing period.
- **scope** is optional: a short noun for the area touched (`api`, `skills`, `parser`). Reuse the
  scopes in `git log --oneline -30`. Never use an issue number as the scope.
- **breaking change**: put `!` before the colon, e.g. `feat(api)!: remove status endpoint`.
- Keep the whole header under 72 characters (100 is the hard limit).

## Body and footer
- Body (optional): why the change was made and how it differs from the old behaviour. Imperative
  present tense. Wrap at about 72 characters.
- Footer (optional): issue references (`Closes #123`, `Refs JIRA-456`) and breaking changes.
  A breaking change footer starts with `BREAKING CHANGE: ` and is required when the header has `!`
  and the description alone does not explain what breaks.
- Never add AI attribution (`Co-Authored-By`, "Generated with ..."), and keep the user's own git identity.

## Merge and revert commits
Keep git's default messages: `Merge branch '<name>'` and `Revert "<reverted subject>"`.

## Procedure
1. `git status`, `git diff --staged` (or `git diff`), and `git log --oneline -15` to see the change
   and the scopes already in use.
2. Pick the type that describes the user-visible effect, then the scope, then write the description.
3. Write the message to a file and check it:
   ```bash
   python3 ~/.claude/skills/conventional-commits/scripts/check_commit_msg.py msg.txt
   ```
   Fix every error it reports, then `git commit -F msg.txt` and delete the file.
4. If the repo enforces a different convention (commitlint config, a `CONTRIBUTING.md` rule, a
   commit-msg hook), follow the repo and say so.

## Versioning (when cutting a release)
A breaking change bumps the major version; otherwise any `feat` bumps the minor version; otherwise
bump the patch version.

## Examples
```
feat: add email notifications on new direct messages
feat(shopping-cart): add the checkout button
fix(api): fix wrong calculation of request body checksum
perf: reduce memory use of unique-visitor counting with HyperLogLog
build(release): bump version to 1.0.0
docs(readme): list the install path of every file
```
```
feat!: remove ticket list endpoint

Listing every ticket timed out on large projects and nobody used it.

Refs JIRA-1337
BREAKING CHANGE: ticket endpoints no longer support listing all entities.
```
