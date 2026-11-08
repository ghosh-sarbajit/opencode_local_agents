# Training data formats

Adapted from `skills/core-skills/aws-ai-ml/references/dataset-evaluation/references/strategy_data_requirements.md`
in aws/agent-toolkit-for-aws (Apache-2.0, Copyright Amazon.com, Inc. or its affiliates).
Modified: kept the open-weights formats, matched them to the formats TRL reads, removed the
Nova and SageMaker-specific sections.

**File format: JSONL only** (one JSON object per line). Convert Parquet, CSV, etc. first.

## SFT, prompt/completion (`format_detector`: `open_weights_sft`)

```json
{"prompt": "Translate to Hindi: Good morning", "completion": "सुप्रभात"}
```

TRL computes the loss on the completion only.

## SFT, conversational (`format_detector`: `gpt_oss_sft`)

```json
{"messages": [{"role": "system", "content": "You are concise."},
              {"role": "user", "content": "Capital of France?"},
              {"role": "assistant", "content": "Paris."}]}
```

The tokenizer's chat template is applied automatically. Use this when the model will be used
as a chat model.

## DPO (`format_detector`: `open_weights_dpo`)

```json
{"prompt": "Explain overfitting in one sentence.",
 "chosen": "Overfitting is when a model memorizes training data and fails on new data.",
 "rejected": "Overfitting is good because the training loss is low."}
```

Needs: two plausible responses to the same prompt, a clear preference, no systematic length difference.

## RLVR (TRL `GRPOTrainer`)

```json
{"prompt": [{"role": "user", "content": "What is 17 * 23?"}], "ground_truth": "391"}
```

`prompt` is required; every other column is passed to your reward function by name.

## Quick checks

```bash
python scripts/format_detector.py data/train.jsonl          # format
wc -l data/train.jsonl data/eval.jsonl                      # size
python -c "import json,sys; [json.loads(l) for l in open(sys.argv[1])]; print('all lines parse')" data/train.jsonl
```
