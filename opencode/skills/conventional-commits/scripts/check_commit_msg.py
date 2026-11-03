#!/usr/bin/env python3
"""Check a commit message against the Conventional Commits rules in SKILL.md.

usage: check_commit_msg.py FILE      (or pipe the message on stdin)
Exit 0 when the message passes, 1 with one line per problem otherwise.
"""
import re
import sys

TYPES = "feat|fix|refactor|perf|style|test|docs|build|ops|chore"
HEADER = re.compile(rf"^(?P<type>{TYPES})(\((?P<scope>[^()\s][^()]*)\))?(?P<bang>!)?: (?P<desc>.+)$")
PAST_TENSE = re.compile(r"^(added|fixed|removed|changed|updated|adds|fixes|removes|changes|updates)\b")
ATTRIBUTION = re.compile(r"co-authored-by:.*(claude|opencode|gpt|copilot)|generated with", re.I)


def check(text):
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or not lines[0].strip():
        return ["empty commit message"]
    header = lines[0]
    if re.match(r"^(Merge branch '.+'|Revert \".+\")", header):
        return []

    errors = []
    m = HEADER.match(header)
    if not m:
        errors.append(f"header must be '<type>(<scope>): <description>' with type one of {TYPES.replace('|', ', ')}")
    else:
        desc = m["desc"]
        if desc[0].isupper():
            errors.append("description must start with a lowercase letter")
        if desc.endswith("."):
            errors.append("description must not end with a period")
        if PAST_TENSE.match(desc.lower()):
            errors.append("description must use the imperative ('add', not 'added' or 'adds')")
        if m["scope"] and re.fullmatch(r"#?\d+|[A-Z]+-\d+", m["scope"]):
            errors.append("scope must not be an issue identifier")
    if len(header) > 100:
        errors.append(f"header is {len(header)} characters; the limit is 100 (aim for 72)")
    if len(lines) > 1 and lines[1].strip():
        errors.append("leave a blank line between the header and the body")
    if ATTRIBUTION.search(text):
        errors.append("remove AI attribution lines")
    return errors


def main():
    text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    errors = check(text)
    for e in errors:
        print(f"error: {e}")
    if not errors:
        print("ok")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
