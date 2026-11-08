---
name: remote-gpu-jobs
description: Run long jobs on the bharati and kanaada GPU servers from this machine - copy code and data with rsync, launch in a detached tmux session pinned to a GPU with a log file, monitor progress, fetch results, and stop jobs. Use when the user wants to train, fine-tune, run inference, or run any script "on bharati", "on kanaada" or "on the GPU server".
license: Apache-2.0
metadata:
  version: "1"
---

# Running jobs on the GPU servers

Read the `gpu-servers` skill first for hardware, disk and etiquette rules.
All commands below run on **this machine**; they reach the servers over SSH.

## Workflow

1. **Pick a server and GPU.** Run `bash ../gpu-servers/scripts/gpu_status.sh` and choose a GPU marked FREE.
   If none is free, stop and tell the user who is using the GPUs.
2. **Copy code (and small data) to the server** with rsync. Exclude caches and large outputs:

   ```bash
   rsync -az --info=progress2 \
     --exclude '.git' --exclude '__pycache__' --exclude 'outputs/' --exclude '*.ckpt' \
     ./myproject/ bharati:~/projects/myproject/
   ```

   On kanaada put projects and data under `/data/sarbajit/` (its `/home` is almost full).
   Large datasets and models: download them on the server directly (see `aws-data-transfer`),
   do not push them through this machine.
3. **Launch** with the helper (creates a detached tmux session, pins the GPU, logs everything):

   ```bash
   bash scripts/remote_run.sh <host> <session-name> <gpu-ids> <workdir> '<command>'
   # example
   bash scripts/remote_run.sh bharati sft-llama 0 '~/projects/myproject' \
     'source ~/miniconda3/bin/activate myenv && python train.py --config cfg.yaml'
   ```

   It refuses to start if a tmux session with that name already exists, and prints the log path
   (`<workdir>/logs/<session-name>-<timestamp>.log`).
4. **Monitor:**

   ```bash
   ssh bharati 'tail -n 50 ~/projects/myproject/logs/sft-llama-*.log'   # recent output
   ssh bharati 'tmux ls'                                                    # is it still running?
   bash ../gpu-servers/scripts/gpu_status.sh bharati                        # GPU use
   ```

   The log ends with `=== exit code N ===` when the command finishes. Non-zero means it failed:
   read the last 100 lines before retrying.
5. **Fetch results** (only what is needed, not every checkpoint):

   ```bash
   rsync -az bharati:~/projects/myproject/outputs/metrics/ ./outputs/metrics/
   ```

6. **Stop a job you started:** `ssh bharati 'tmux kill-session -t sft-llama'`.
   Only ever kill sessions you created.

## Environment setup on a server

Create a separate conda env per project (never install into base):

```bash
# bharati
ssh bharati 'source ~/miniconda3/bin/activate && conda create -y -n myenv python=3.11'
# kanaada: put envs on /data because /home is full
ssh kanaada 'source ~/anaconda3/bin/activate && conda create -y -p /data/sarbajit/envs/myenv python=3.11'
```

Then `pip install` inside it, using the version pins from the `gpu-servers` skill (the
default latest PyTorch/vLLM do **not** work with the servers' driver), and verify CUDA.
Installing vLLM takes 10-15 minutes, so run it through `remote_run.sh` too.

## Rules

- Long commands go through `remote_run.sh` (tmux). A plain `ssh host 'python train.py'` dies when the connection drops.
- Always set `CUDA_VISIBLE_DEVICES` (the script does this from `<gpu-ids>`).
- Write checkpoints to a disk with room (bharati: home; kanaada: `/data/sarbajit`). Check space first.
- Save checkpoints periodically so a crashed or killed job can resume.
- Quote carefully: the command is passed as one single-quoted string; use double quotes inside it.
