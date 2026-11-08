"""Merge a LoRA adapter into its base model and save full bf16 weights.

Example:
  python merge_lora.py --base Qwen/Qwen2.5-7B-Instruct --adapter outputs/sft-run1 \
      --output outputs/sft-run1-merged
Needs CPU RAM (or one GPU) for the full model in bf16: about 2 GB per billion parameters.
"""
import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    base = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16)
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()
    merged.save_pretrained(args.output, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.adapter).save_pretrained(args.output)
    print(f"merged model saved to {args.output}")


if __name__ == "__main__":
    main()
