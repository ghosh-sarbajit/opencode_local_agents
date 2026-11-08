---
name: llm-evaluation
description: Evaluate and compare LLMs (base vs fine-tuned, model A vs model B) on the bharati/kanaada GPU servers - generate answers with vLLM, score them with code (exact match, F1, regex) or with an LLM judge, and report scores with confidence intervals. Use when the user asks to evaluate, benchmark accuracy, compare models, check whether fine-tuning helped, or build an LLM-as-judge.
license: Apache-2.0
metadata:
  version: "1"
  derived-from: aws/agent-toolkit-for-aws skills/core-skills/aws-ai-ml/references/model-evaluation (Apache-2.0), adapted from SageMaker/Bedrock to local vLLM
---

# LLM evaluation on the GPU servers

The choice between code-based scoring and LLM-as-judge, and the step order, are adapted from the
`model-evaluation` reference of aws-ai-ml in aws/agent-toolkit-for-aws (Apache-2.0). The scripts
here run locally with vLLM instead of SageMaker/Bedrock. See `NOTICE` at the repo root of opencode_local_agents.

## 1. Pick the evaluation type

| Goal | Type | Script |
|---|---|---|
| Answers can be checked by code (labels, numbers, exact strings, regex, unit tests) | **Code scorer** (cheaper, deterministic) | `scripts/score.py` |
| Subjective quality (helpfulness, faithfulness, tone, fluency) | **LLM-as-judge** | `scripts/judge.py` |

Prefer the code scorer whenever it gives a meaningful signal. Use a judge only for qualities code
cannot measure, and spot-check 20-30 judge verdicts by hand before trusting them. The judge must be
stronger than the models it grades.

## 2. Get an evaluation set

JSONL, one item per line, never overlapping with training data:

```json
{"id": "q1", "prompt": "What is 17 * 23?", "reference": "391"}
```

`prompt` may also be a list of chat messages. `reference` is needed for code scoring and optional
for the judge. No evaluation set means no evaluation: ask the user for one rather than inventing it.
Size: about 200 items detects a ~10-point accuracy difference; about 1000 detects ~4 points.

## 3. Generate answers (on a server, inside tmux)

```bash
python scripts/generate.py --model Qwen/Qwen2.5-7B-Instruct --data eval.jsonl --out gen_base.jsonl
python scripts/generate.py --model Qwen/Qwen2.5-7B-Instruct --lora outputs/sft-run1 --data eval.jsonl --out gen_sft.jsonl
```

Use the **same** prompts, sampling settings (`--temperature 0` by default) and max tokens for every
model you compare. Launch through `remote-gpu-jobs` and pin one GPU. Needs `vllm` in the env.

## 4. Score

Code scorer:

```bash
python scripts/score.py gen_base.jsonl --metric exact          # also: contains, f1, regex
python scripts/score.py gen_base.jsonl --metric regex --pattern 'Answer:\s*(\S+)'
python scripts/score.py gen_base.jsonl gen_sft.jsonl --metric exact   # paired comparison
```

LLM judge (needs an OpenAI-compatible server for the judge model; see `vllm-serving`):

```bash
python scripts/judge.py gen_sft.jsonl --base-url http://localhost:8000/v1 --model <judge-model> \
  --criteria "Is the answer correct, complete and faithful to the question?" --out judged_sft.jsonl
python scripts/score.py judged_sft.jsonl --metric judge
```

The judge returns a 1-10 score per item; `score.py --metric judge` averages them with a 95% CI.

## 5. Report

Report for each model: metric, mean, 95% bootstrap confidence interval and the number of items.
For two models on the same items, report the paired difference and its interval: if the interval
includes 0, the models are not distinguishable on this set. Show 3-5 example items where they
disagree. Save the command lines, model versions and data version alongside the scores.
