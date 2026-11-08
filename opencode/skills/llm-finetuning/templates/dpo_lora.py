"""Direct Preference Optimization with LoRA or QLoRA using TRL.

Data: JSONL with {"prompt", "chosen", "rejected"} per line.
With LoRA, the reference model is the base model with the adapter switched off,
so no second copy of the model is loaded.
Resumes automatically from the last checkpoint in --output.

Example:
  CUDA_VISIBLE_DEVICES=0 python dpo_lora.py --model outputs/sft-run1-merged \
      --train data/prefs.jsonl --output outputs/dpo-run1
"""
import argparse

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from transformers.trainer_utils import get_last_checkpoint
from trl import DPOConfig, DPOTrainer


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="HF model id or local path (often a merged SFT model)")
    p.add_argument("--train", required=True)
    p.add_argument("--eval")
    p.add_argument("--output", required=True)
    p.add_argument("--epochs", type=float, default=1)
    p.add_argument("--lr", type=float, default=5e-6)
    p.add_argument("--beta", type=float, default=0.1, help="higher keeps the model closer to the reference")
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=16)
    p.add_argument("--max-length", type=int, default=2048)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--qlora", action="store_true")
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-steps", type=int, default=-1, help="stop after N steps (for a quick trial run)")
    return p.parse_args()


def main():
    args = parse_args()

    quant = None
    if args.qlora:
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, quantization_config=quant
    )

    data_files = {"train": args.train}
    if args.eval:
        data_files["eval"] = args.eval
    ds = load_dataset("json", data_files=data_files)

    config = DPOConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        beta=args.beta,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        bf16=True,
        max_length=args.max_length,
        logging_steps=10,
        save_steps=args.save_steps,
        save_total_limit=2,
        eval_strategy="steps" if args.eval else "no",
        eval_steps=args.save_steps if args.eval else None,
        report_to="none",
        seed=args.seed,
        max_steps=args.max_steps,
    )
    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
    )
    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=config,
        train_dataset=ds["train"],
        eval_dataset=ds.get("eval"),
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.train(resume_from_checkpoint=get_last_checkpoint(args.output))
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"saved LoRA adapter to {args.output}")


if __name__ == "__main__":
    main()
