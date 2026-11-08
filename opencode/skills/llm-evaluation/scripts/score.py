"""Score generated answers with code-based metrics and bootstrap confidence intervals.

One file:  score.py gen.jsonl --metric exact
Two files: score.py gen_a.jsonl gen_b.jsonl --metric exact   (paired comparison on shared ids)

Metrics (each item needs "output"; all but judge need "reference"):
  exact     normalized exact match (lowercase, strip punctuation/articles/extra spaces)
  contains  normalized reference appears inside the normalized output
  f1        token-level F1 between output and reference
  regex     extract group 1 of --pattern from the output, then exact match
  judge     mean of the "judge_score" field written by judge.py (1-10)
Standard library only.
"""
import argparse
import json
import random
import re
import string
from collections import Counter

ARTICLES = re.compile(r"\b(a|an|the)\b")


def normalize(s):
    s = str(s).lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = ARTICLES.sub(" ", s)
    return " ".join(s.split())


def token_f1(pred, ref):
    p, r = normalize(pred).split(), normalize(ref).split()
    common = Counter(p) & Counter(r)
    overlap = sum(common.values())
    if not p or not r:
        return float(p == r)
    if overlap == 0:
        return 0.0
    prec, rec = overlap / len(p), overlap / len(r)
    return 2 * prec * rec / (prec + rec)


def item_score(row, metric, pattern):
    out = row.get("output", "")
    if metric == "judge":
        v = row.get("judge_score")
        return None if v is None else float(v)
    ref = row.get("reference")
    if ref is None:
        return None
    refs = ref if isinstance(ref, list) else [ref]
    if metric == "exact":
        return max(float(normalize(out) == normalize(r)) for r in refs)
    if metric == "contains":
        return max(float(normalize(r) in normalize(out)) for r in refs)
    if metric == "f1":
        return max(token_f1(out, r) for r in refs)
    if metric == "regex":
        m = re.search(pattern, out)
        got = m.group(1) if m else ""
        return max(float(normalize(got) == normalize(r)) for r in refs)
    raise ValueError(metric)


def load(path, metric, pattern):
    scores, skipped = {}, 0
    for i, line in enumerate(open(path, encoding="utf-8")):
        if not line.strip():
            continue
        row = json.loads(line)
        s = item_score(row, metric, pattern)
        if s is None:
            skipped += 1
            continue
        scores[str(row.get("id", i))] = s
    return scores, skipped


def bootstrap_ci(values, n=2000, seed=0):
    rng = random.Random(seed)
    k = len(values)
    means = sorted(sum(rng.choices(values, k=k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+", help="one file, or two files for a paired comparison")
    p.add_argument("--metric", required=True, choices=["exact", "contains", "f1", "regex", "judge"])
    p.add_argument("--pattern", default=r"Answer:\s*(.+)", help="regex with one group (for --metric regex)")
    args = p.parse_args()
    if len(args.files) > 2:
        p.error("give one or two files")

    loaded = [load(f, args.metric, args.pattern) for f in args.files]
    for f, (sc, skipped) in zip(args.files, loaded):
        vals = list(sc.values())
        if not vals:
            print(f"{f}: no scorable items (skipped {skipped})")
            continue
        lo, hi = bootstrap_ci(vals)
        mean = sum(vals) / len(vals)
        print(f"{f}: {args.metric} = {mean:.4f}  95% CI [{lo:.4f}, {hi:.4f}]  n={len(vals)}  skipped={skipped}")

    if len(loaded) == 2:
        a, b = loaded[0][0], loaded[1][0]
        ids = sorted(set(a) & set(b))
        if not ids:
            print("no shared ids between the two files")
            return
        diffs = [b[i] - a[i] for i in ids]
        lo, hi = bootstrap_ci(diffs)
        mean = sum(diffs) / len(diffs)
        verdict = "not distinguishable" if lo <= 0 <= hi else ("second is better" if mean > 0 else "first is better")
        print(f"paired difference (second - first) = {mean:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  n={len(ids)}  -> {verdict}")


if __name__ == "__main__":
    main()
