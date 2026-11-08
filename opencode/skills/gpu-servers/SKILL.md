---
name: gpu-servers
description: Inventory, status and etiquette for the two shared GPU servers bharati (2x L40S 48 GB) and kanaada (2x A100 40 GB), reached over SSH from this machine. Use when the user mentions bharati, kanaada/kannada, "the GPU servers", wants to know which GPUs are free, needs to pick a server for a job, or asks about disk space, conda environments or CUDA on those machines.
license: Apache-2.0
metadata:
  version: "1"
---

# GPU servers: bharati and kanaada

Both servers are shared with other people. Treat every GPU, process and disk you did
not start as someone else's.

## Hosts

| | bharati | kanaada |
|---|---|---|
| SSH alias | `bharati` | `kanaada` (also `kannada`) |
| IP | 172.27.21.35 | 172.27.21.120 |
| GPUs | 2x NVIDIA L40S, 48 GB each (Ada, sm_89, FP8 capable) | 2x NVIDIA A100-PCIE, 40 GB each (Ampere, sm_80, no FP8 compute) |
| GPU link | No NVLink; GPU0 and GPU1 on different CPU sockets (`SYS`) | Same: no NVLink, `SYS` |
| CPU / RAM | 96 cores, ~1 TB RAM | 32 cores, ~125 GB RAM |
| OS | Ubuntu 24.04 | CentOS 8 |
| Driver / CUDA | 535.x / CUDA 12.2 | 535.x / CUDA 12.2 |
| Python | `~/miniconda3` (activate it first) | `~/anaconda3` (default) |
| Disk for big files | `/` (home is here), ~160 GB free, 91% full | `/data/sarbajit` (~275 GB free, 95% full); `/home` is 97% full: avoid it |
| HF cache | `~/.cache/huggingface` | `/data/sarbajit/huggingface_cache` |
| Docker | Not usable (no docker group) | Not usable |

Login is key-based (`~/.ssh/anviksha_to_all`); `ssh bharati` and `ssh kanaada` need no password.
Numbers above were measured on 2026-11-07. Disk usage changes fast: re-check before large downloads.

## Check what is free (always do this before starting GPU work)

```bash
bash scripts/gpu_status.sh            # both servers
bash scripts/gpu_status.sh bharati    # one server
```

It prints per-GPU utilization, memory, the owner of every GPU process, free disk and load.
A GPU counts as free when memory used is under 1 GB and utilization is under 5%.
Never assume a GPU is free because it was free earlier in the conversation.

## Choosing a server

- Model or batch needs more than 40 GB on one GPU: **bharati** (48 GB per GPU).
- FP8 inference or FP8 KV cache: **bharati** (L40S supports FP8; A100 does not).
- Strong FP64/TF32 training, or bharati is busy: **kanaada**.
- Large CPU-side work (DeepSpeed CPU offload, big tokenization, datasets in RAM): **bharati** (1 TB RAM).
- Prefer one GPU per job. The two GPUs on each server talk over the CPU interconnect (no NVLink),
  so tensor parallelism across both is slow. Use 2 GPUs only when the model does not fit on one;
  for throughput, run two independent single-GPU jobs instead.

## Rules on shared machines

1. Pin jobs to specific GPUs: `CUDA_VISIBLE_DEVICES=0` (or `1`). Never let a job grab both by default.
2. Never kill, renice or signal a process you did not start. If a GPU you need is busy, tell the user who owns it.
3. Run anything longer than a few minutes inside `tmux` (see the `remote-gpu-jobs` skill), never in a bare SSH session.
4. Check free disk before downloading models or writing checkpoints; keep at least 20 GB free for other users.
5. Do not `sudo`, install system packages, or change anything outside `/home/sarbajit` and `/data/sarbajit`.
6. Install Python packages into a conda env (`conda create -p <path>`), never into the base or system Python.
7. Clean up: stop your servers and tmux sessions when done, and delete scratch checkpoints you no longer need.

## CUDA and PyTorch

Driver 535 supports CUDA 12.2. CUDA **12.x** PyTorch builds run through CUDA minor-version
compatibility; CUDA **13** builds do not.

**Important:** PyTorch 2.11 and newer on PyPI are CUDA 13 builds and fail on these servers with
`The NVIDIA driver on your system is too old (found version 12020)`. vLLM 0.21+ pulls them in.
Use this tested set (verified on bharati, 2026-11-07):

```bash
pip install "vllm==0.18.1" trl peft datasets accelerate bitsandbytes
# gives torch 2.10.0+cu128, transformers 4.57, trl 1.17, peft 0.21
```

Without vLLM: `pip install "torch<2.11"`. Verify after every install:

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

The CUDA version printed must start with 12. If it starts with 13, or `is_available()` is False,
reinstall with the pins above.

## Related skills

- `remote-gpu-jobs`: copy code, launch, monitor and collect results.
- `vllm-serving`: serve or benchmark a model on these GPUs.
- `llm-finetuning`, `llm-evaluation`: training and evaluation workflows sized for these GPUs.
- `aws-data-transfer`: move data and models between AWS and these servers.
