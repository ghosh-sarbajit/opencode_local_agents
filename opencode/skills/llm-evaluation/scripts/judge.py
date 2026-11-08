"""LLM-as-judge: score each generated answer 1-10 with a judge model behind an
OpenAI-compatible API (for example a vLLM server; see the vllm-serving skill).

Input: JSONL from generate.py (needs "prompt" and "output"; "reference" is used if present).
Output: the same rows plus "judge_score" (1-10, or null if unparseable) and "judge_reason".

Example:
  python judge.py gen.jsonl --base-url http://localhost:8000/v1 --model Qwen/Qwen2.5-32B-Instruct \
      --criteria "Is the answer correct and complete?" --out judged.jsonl
Standard library only.
"""
import argparse
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TEMPLATE = """You are a strict evaluator. Grade the RESPONSE to the QUESTION.

Criteria: {criteria}

QUESTION:
{question}
{reference_block}
RESPONSE:
{response}

Give a score from 1 (very poor) to 10 (excellent). Reply with only a JSON object:
{{"reason": "<one or two sentences>", "score": <integer 1-10>}}"""


def as_text(prompt):
    if isinstance(prompt, list):
        return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in prompt)
    return str(prompt)


def call(base_url, model, api_key, content, max_tokens, timeout):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def parse(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            score = int(obj["score"])
            if 1 <= score <= 10:
                return score, str(obj.get("reason", ""))
        except (ValueError, KeyError, TypeError):
            pass
    m = re.search(r'"?score"?\s*[:=]\s*(\d+)', text, flags=re.I)
    if m and 1 <= int(m.group(1)) <= 10:
        return int(m.group(1)), text.strip()[:300]
    return None, text.strip()[:300]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--out", required=True)
    p.add_argument("--base-url", default="http://localhost:8000/v1")
    p.add_argument("--model", required=True, help="judge model name as served")
    p.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    p.add_argument("--criteria", default="Is the response correct, complete, relevant and clearly written?")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--timeout", type=int, default=300)
    args = p.parse_args()

    rows = [json.loads(l) for l in open(args.input, encoding="utf-8") if l.strip()]

    def grade(row):
        ref = row.get("reference")
        content = TEMPLATE.format(
            criteria=args.criteria,
            question=as_text(row.get("prompt", "")),
            reference_block=f"\nREFERENCE ANSWER (for guidance):\n{ref}\n" if ref else "",
            response=row.get("output", ""),
        )
        try:
            score, reason = parse(call(args.base_url, args.model, args.api_key, content, args.max_tokens, args.timeout))
        except Exception as e:  # keep going; record the failure on the row
            score, reason = None, f"judge call failed: {e}"
        return dict(row, judge_score=score, judge_reason=reason, judge_model=args.model)

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(grade, rows))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    bad = sum(r["judge_score"] is None for r in results)
    print(f"judged {len(results)} items -> {args.out} ({bad} unparseable or failed)")


if __name__ == "__main__":
    main()
