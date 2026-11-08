"""Generate model answers for an evaluation set with vLLM (offline batch mode).

Input JSONL: {"id": ..., "prompt": "<text>" or [chat messages], "reference": ... (optional)}
Output JSONL: the input fields plus "output" and "model".

Example:
  CUDA_VISIBLE_DEVICES=0 python generate.py --model Qwen/Qwen2.5-7B-Instruct \
      --data eval.jsonl --out gen_base.jsonl
"""
import argparse
import json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--lora", help="path to a LoRA adapter to apply on top of --model")
    p.add_argument("--system", help="optional system prompt added to every item")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--max-model-len", type=int, default=8192)
    p.add_argument("--tp", type=int, default=1, help="tensor parallel size (GPUs)")
    p.add_argument("--gpu-mem", type=float, default=0.90)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    from vllm import LLM, SamplingParams

    items = [json.loads(line) for line in open(args.data, encoding="utf-8") if line.strip()]
    convs = []
    for it in items:
        msgs = it["prompt"] if isinstance(it["prompt"], list) else [{"role": "user", "content": it["prompt"]}]
        if args.system and msgs[0].get("role") != "system":
            msgs = [{"role": "system", "content": args.system}] + msgs
        convs.append(msgs)

    llm = LLM(
        model=args.model,
        tensor_parallel_size=args.tp,
        gpu_memory_utilization=args.gpu_mem,
        max_model_len=args.max_model_len,
        enable_lora=bool(args.lora),
        seed=args.seed,
    )
    params = SamplingParams(
        temperature=args.temperature, top_p=args.top_p, max_tokens=args.max_tokens, seed=args.seed
    )
    lora_req = None
    if args.lora:
        from vllm.lora.request import LoRARequest

        lora_req = LoRARequest("adapter", 1, args.lora)

    outputs = llm.chat(convs, params, lora_request=lora_req)
    name = args.model + (f"+{args.lora}" if args.lora else "")
    with open(args.out, "w", encoding="utf-8") as f:
        for it, out in zip(items, outputs):
            row = dict(it, output=out.outputs[0].text, model=name)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(items)} answers to {args.out}")


if __name__ == "__main__":
    main()
