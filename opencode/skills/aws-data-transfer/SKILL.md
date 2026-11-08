---
name: aws-data-transfer
description: Move datasets, checkpoints and models between AWS (S3, the SageMaker HyperPod cluster bgen-cluster-c) and the on-prem GPU servers bharati and kanaada, and between the two servers, without leaving long-lived AWS keys on shared machines. Also covers downloading Hugging Face models straight onto a server. Use when the user wants to copy, sync, upload or download data or models to or from S3, the AWS cluster, bharati or kanaada.
license: Apache-2.0
metadata:
  version: "1"
  derived-from: aws/agent-toolkit-for-aws skills/core-skills/signing-in-to-aws and aws-storage (Apache-2.0)
---

# Moving data between AWS and the GPU servers

Credential handling follows the `signing-in-to-aws` skill of aws/agent-toolkit-for-aws
(Apache-2.0): prefer short-term credentials from `aws login`. See `NOTICE` at the repo root of opencode_local_agents.

## Where things are

- **This machine** has AWS CLI v2 (`aws`) and the SSH aliases `bharati`, `kanaada` and
  `bgen-cluster-c` (the HyperPod login node, reached through AWS SSM).
- **bharati / kanaada** have no AWS CLI and no direct route to `bgen-cluster-c`. They have
  internet access, `rsync`, and `huggingface-cli`.
- Free space is tight (see `gpu-servers`): check `df -h` on the target before every large copy.
  On kanaada write to `/data/sarbajit/`, never `/home`.

## Credentials

1. Check on this machine: `aws sts get-caller-identity`.
2. If it fails or has expired, the fix is `aws login` (needs AWS CLI 2.32+; ask the user before
   running it; on a machine without a browser use `aws login --remote`). If the user already uses
   `aws sso login`, keep using that.
3. **Never** copy `~/.aws/credentials` or any access key into a file on bharati or kanaada: other
   people use those machines. Pass credentials through stdin for a single command (pattern B).

## Pattern A: small or medium data (up to a few GB) - stage on this machine

```bash
aws s3 sync s3://my-bucket/dataset/ ./staging/dataset/
rsync -az --info=progress2 ./staging/dataset/ bharati:~/data/dataset/
```

Reverse direction (results to S3): `rsync` from the server to `./staging/`, then `aws s3 sync` up.

## Pattern B: large data - run the AWS CLI on the server

One-time install of AWS CLI v2 into your home on the server (no sudo):

```bash
ssh bharati 'cd /tmp && curl -sSLo awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip \
  && unzip -q -o awscliv2.zip && ./aws/install -i ~/.local/aws-cli -b ~/.local/bin && rm -rf aws awscliv2.zip \
  && ~/.local/bin/aws --version'
```

Then send the credentials through stdin so they never touch disk or the process list:

```bash
aws configure export-credentials --format env | \
  ssh bharati 'source /dev/stdin && ~/.local/bin/aws s3 sync s3://my-bucket/dataset/ ~/data/dataset/'
```

Short-term credentials expire (often within an hour). `aws s3 sync` is incremental, so if a long
sync stops with an expired-token error, just run the same command again.

## Pattern C: HyperPod cluster <-> GPU servers - stream through this machine

There is no direct route, so stream a tar archive through this machine (nothing is stored locally):

```bash
ssh bgen-cluster-c 'tar -C /path/on/cluster -cf - results_dir' | ssh bharati 'tar -C ~/data -xf -'
```

The same works server to server: `ssh bharati 'tar -C ~/data -cf - ds' | ssh kanaada 'tar -C /data/sarbajit -xf -'`.
Add `z` to both tar commands only for compressible text data; model weights do not compress.
Verify afterwards: compare `du -sb` (or `sha256sum` of a few files) on both ends.

## Hugging Face models: download on the server directly

```bash
ssh bharati 'huggingface-cli download Qwen/Qwen2.5-7B-Instruct'
ssh kanaada 'HF_HOME=/data/sarbajit/huggingface_cache huggingface-cli download Qwen/Qwen2.5-7B-Instruct'
```

For gated models, pass the token through stdin, the same way as AWS credentials:
`printf 'HF_TOKEN=%s\n' "$HF_TOKEN" | ssh bharati 'set -a; source /dev/stdin; huggingface-cli download meta-llama/Llama-3.1-8B-Instruct'`.
Run long downloads through `remote-gpu-jobs` (tmux) so they survive a dropped connection.

## Rules

- Check free space before copying. A full disk on a shared server breaks other people's jobs.
- Prefer `aws s3 sync` and `rsync` (resumable) over `cp` for anything large.
- Do not delete or overwrite data on S3 or the servers without asking (`aws s3 sync --delete`,
  `rsync --delete` included).
- Copy only what is needed: final checkpoints and metrics, not every intermediate checkpoint.
