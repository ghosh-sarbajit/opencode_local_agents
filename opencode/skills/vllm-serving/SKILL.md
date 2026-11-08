---
name: vllm-serving
description: Serve an LLM with vLLM on the bharati or kanaada GPU servers, reach it from this machine through an SSH tunnel, check it fits in GPU memory, benchmark latency and throughput, and connect it to opencode as a local model provider. Use when the user wants to host, serve, deploy or benchmark a model on the GPU servers, needs an OpenAI-compatible endpoint for a judge or an agent, or wants opencode to use a model running on bharati/kanaada.
license: Apache-2.0
metadata:
  version: "1"
  derived-from: aws/agent-toolkit-for-aws skills/core-skills/aws-ai-ml/references/model-deployment (benchmark workflow, Apache-2.0), adapted from SageMaker endpoints to vLLM
---

# Serving models with vLLM on the GPU servers

The benchmarking procedure (load-safety check, workload defaults, request counts for percentiles,
comparability rules) is adapted from the model-deployment/optimization references of aws-ai-ml in
aws/agent-toolkit-for-aws (Apache-2.0). Serving itself uses vLLM instead of SageMaker. See `NOTICE` at the repo root of opencode_local_agents.

Read `gpu-servers` and `remote-gpu-jobs` first. Install **`vllm==0.18.1`** (newest release whose
PyPI wheels use CUDA 12; later ones need a newer driver than the servers have). Commands below
are tested with that version.

## 1. Will it fit?

Weights need about **2 GB per billion parameters in bf16**, 1 GB in FP8/INT8, ~0.55 GB in 4-bit
(AWQ/GPTQ). Leave 20-30% of the GPU for the KV cache.

| Model | bharati (L40S 48 GB) | kanaada (A100 40 GB) |
|---|---|---|
| up to 8B, bf16 | 1 GPU | 1 GPU |
| 12-14B, bf16 | 1 GPU | 1 GPU (short context) |
| 27-32B | 1 GPU with `--quantization fp8`, or AWQ/GPTQ 4-bit; bf16 needs `--tensor-parallel-size 2` | AWQ/GPTQ 4-bit on 1 GPU; bf16 needs 2 GPUs and is tight |
| 70B | AWQ/GPTQ 4-bit with 2 GPUs | AWQ/GPTQ 4-bit with 2 GPUs, short context |

FP8 compute is only on bharati (L40S). The two GPUs on each server are not NVLinked, so
`--tensor-parallel-size 2` works but is slower than one GPU. For more throughput on a model that
fits one GPU, run two servers (one per GPU, different ports) instead.

## 2. Start the server (inside tmux, bound to localhost)

Check the GPU is free (`gpu_status.sh`) and the port is unused (`ssh bharati 'ss -ltn | grep :8000'`).

```bash
bash ../remote-gpu-jobs/scripts/remote_run.sh bharati vllm-qwen 0 '~/serving' \
  'source ~/miniconda3/bin/activate myenv && vllm serve Qwen/Qwen2.5-7B-Instruct \
     --host 127.0.0.1 --port 8000 --served-model-name qwen7b \
     --max-model-len 16384 --gpu-memory-utilization 0.90'
```

Always use `--host 127.0.0.1` on these shared servers so other users cannot reach your server;
reach it through the tunnel below. Useful extra flags:

- LoRA adapter: `--enable-lora --lora-modules myadapter=/path/to/adapter` (request `"model": "myadapter"`).
- Tool calling (needed for opencode or other agents): `--enable-auto-tool-choice --tool-call-parser <parser>`.
  Use `hermes` for Qwen2.5/Qwen3, `qwen3_coder` for Qwen3-Coder, `llama3_json` for Llama 3.x,
  `mistral` for Mistral, `openai` for gpt-oss. The parsers in your install are the
  `*_tool_parser.py` files under `vllm/tool_parsers/`.
- Reasoning models: `--reasoning-parser <name>` (e.g. `qwen3`, `deepseek_r1`) to split out the thinking text.
- Two GPUs: `--tensor-parallel-size 2` with `<gpu-ids>` set to `0,1`. If it hangs at startup, add
  `NCCL_P2P_DISABLE=1` before `vllm serve`.

Startup takes 1-5 minutes. Wait until the log shows `Application startup complete`.

## 3. Reach it from this machine

```bash
ssh -f -N -L 8000:127.0.0.1:8000 bharati          # background tunnel
curl -s http://localhost:8000/v1/models             # health check
curl -s http://localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen7b","messages":[{"role":"user","content":"Say hi"}],"max_tokens":20}'
```

Close the tunnel later with `pkill -f 'ssh -f -N -L 8000:127.0.0.1:8000 bharati'`. If local
port 8000 is taken, use another local port (`-L 8001:127.0.0.1:8000`).

## 4. Use it from opencode

Add a provider to `~/.config/opencode/opencode.json` (merge with what is already there):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "bharati": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "vLLM on bharati",
      "options": { "baseURL": "http://localhost:8000/v1" },
      "models": { "qwen7b": { "name": "Qwen2.5 7B (bharati)" } }
    }
  }
}
```

The model key must equal `--served-model-name`. Start the server with tool calling enabled
(step 2), otherwise the agent cannot use tools. Keep the SSH tunnel open while opencode runs.

## 5. Benchmark (only your own server)

Benchmarking sends heavy load. Only benchmark a server you started; never one someone else is using.

```bash
ssh bharati 'source ~/miniconda3/bin/activate myenv && vllm bench serve \
  --backend openai-chat --base-url http://127.0.0.1:8000 --endpoint /v1/chat/completions \
  --model qwen7b --tokenizer Qwen/Qwen2.5-7B-Instruct \
  --dataset-name random --random-input-len 512 --random-output-len 256 \
  --num-prompts 200 --max-concurrency 8'
```

- Defaults if the use case is unknown: input 512 tokens, output 256, concurrency 1, 100 requests.
  Chat: short input; summarization: long input; load test: raise `--max-concurrency` step by step.
- p50 needs ~100 requests; p99 needs at least ~1000 requests to be meaningful.
- Compare runs only when model, flags, GPU, input/output lengths and concurrency are identical.
- Report: request throughput, output tokens/s, TTFT and inter-token latency (p50/p99).

## 6. Stop

`ssh bharati 'tmux kill-session -t vllm-qwen'` and close the tunnel. Do not leave idle servers
holding GPUs on shared machines.
