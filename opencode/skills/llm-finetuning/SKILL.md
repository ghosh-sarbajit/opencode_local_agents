---
name: llm-finetuning
description: Plan and run LLM fine-tuning (SFT, DPO, LoRA/QLoRA) with Hugging Face TRL on the bharati (2x L40S 48 GB) and kanaada (2x A100 40 GB) GPU servers - choose the technique, validate the JSONL dataset, check the model fits in GPU memory, launch with the provided templates, and resume from checkpoints. Use when the user wants to fine-tune, instruction-tune, align or adapt a model, or asks whether their training data is ready.
license: Apache-2.0
metadata:
  version: "1"
  derived-from: aws/agent-toolkit-for-aws skills/core-skills/aws-ai-ml (Apache-2.0), adapted from SageMaker to on-prem GPUs
---

# LLM fine-tuning on the GPU servers

Adapted from the `aws-ai-ml` skill of aws/agent-toolkit-for-aws (Apache-2.0). The planning,
technique-choice and dataset-validation workflow comes from there; the SageMaker parts are
replaced with TRL + PEFT on bharati/kanaada. See `NOTICE` at the repo root of opencode_local_agents.

Read `gpu-servers` (hardware, disk) and `remote-gpu-jobs` (how to launch) first.

## Workflow

Work through these steps in order. Skip a step only when the answer is already known.

### 1. Pin down the task

Ask (or infer from context): what should the model do better, what does success look like,
and how will it be measured? Write the answer into `PLAN.md` in the project folder. An
evaluation set and metric must exist before training starts (see `llm-evaluation`).

### 2. Choose the technique

Read `references/technique-guide.md`. Short version:

| Data you have | Technique | Template |
|---|---|---|
| One correct output per input | SFT | `templates/sft_lora.py` |
| Pairs of better/worse outputs | DPO | `templates/dpo_lora.py` |
| Outputs checkable by code (math answer, unit tests) | RLVR (TRL `GRPOTrainer`) | no template; see guide |

Start with SFT unless there is a clear reason not to. DPO usually runs after SFT, on the SFT model.

### 3. Validate the dataset

Data must be **JSONL** (one JSON object per line). Formats are in `references/data-formats.md`.

```bash
python scripts/format_detector.py path/to/train.jsonl
```

- `open_weights_sft` (prompt/completion) or `gpt_oss_sft` (messages): ready for SFT.
- `open_weights_dpo` (prompt/chosen/rejected): ready for DPO.
- `unknown`: **not ready**, even though the script prints "Valid". Convert the data first.
- Parquet, CSV and other files are never ready as-is: convert them to JSONL.

Also check: no empty prompts or completions, no duplicates between train and eval, and for DPO
that `chosen` is not systematically longer than `rejected` (length bias).

### 4. Check it fits in memory

Rough GPU memory needed per GPU (bf16, gradient checkpointing on, sequence length 2048, batch 1):

| Model size | LoRA (bf16) | QLoRA (4-bit) | Full fine-tune |
|---|---|---|---|
| 1-3B | 8-14 GB | 5-8 GB | 25-50 GB |
| 7-9B | 20-28 GB | 10-14 GB | ~130 GB: not on one GPU here; needs DeepSpeed ZeRO-3 + CPU offload (bharati only) |
| 12-14B | 32-40 GB (bharati) | 14-20 GB | no |
| 27-34B | no | 24-36 GB (bharati, or kanaada if under 38 GB) | no |
| 70B | no | ~45 GB: bharati single GPU only, very tight | no |

DPO with LoRA needs about 1.5x the SFT figure (it runs two forward passes per pair).
If it does not fit: lower `--max-length`, switch to QLoRA (`--qlora`), or use a smaller model.
Prefer one GPU per run (the GPUs are not NVLinked; see `gpu-servers`).

### 5. Launch

Copy the template into the project, adjust it if needed, sync it to the server and launch it with
`remote-gpu-jobs`:

```bash
bash ../remote-gpu-jobs/scripts/remote_run.sh bharati sft-run1 0 '~/projects/myproj' \
  'source ~/miniconda3/bin/activate myenv && python sft_lora.py \
     --model Qwen/Qwen2.5-7B-Instruct --train data/train.jsonl --eval data/eval.jsonl \
     --output outputs/sft-run1 --epochs 2 --lr 2e-4 --max-length 2048'
```

Required packages in the env: `torch transformers trl peft datasets accelerate` (+ `bitsandbytes`
for QLoRA). Use the pinned install from `gpu-servers` (`vllm==0.18.1 trl peft ...`); the latest
PyTorch does not run on these servers' driver. Templates tested with TRL 1.17 / PEFT 0.21 /
transformers 4.57.

### 6. Watch it and resume if needed

- Loss should fall in the first few hundred steps. Flat or `nan` loss: lower the learning rate.
- Eval loss rising while train loss falls: overfitting; stop early or use fewer epochs.
- CUDA out of memory: lower `--max-length` or `--batch-size`, or switch to `--qlora`.
- The templates save a checkpoint every `--save-steps` and resume automatically from the last
  checkpoint in `--output`. Rerun the same command after a crash.

### 7. Hand off

The output folder holds a LoRA adapter, not full weights. To serve it with vLLM, either pass it
with `--enable-lora` (see `vllm-serving`) or merge it:

```bash
python templates/merge_lora.py --base <base-model> --adapter outputs/sft-run1 --output outputs/sft-run1-merged
```

Then evaluate against the base model with `llm-evaluation`. Record the model, data version,
hyperparameters and scores in `PLAN.md`.
