# Fine-tuning technique guide

Adapted from `skills/core-skills/aws-ai-ml/references/finetuning-technique/references/finetune_technique_selection_guide.md`
in aws/agent-toolkit-for-aws (Apache-2.0, Copyright Amazon.com, Inc. or its affiliates).
Modified: removed the SageMaker recipe check, mapped each technique to a TRL trainer, and
dropped RLAIF (no validated local workflow here).

## SFT (Supervised Fine-Tuning) - TRL `SFTTrainer`

Use when:

- The task has clear right/wrong answers.
- There is a single good output per input.
- The outputs in the data are examples of what the model should produce.
- Classification, extraction, structured generation, instruction following, domain adaptation.

## DPO (Direct Preference Optimization) - TRL `DPOTrainer`

Use when:

- Several outputs are valid but some are better than others.
- Quality is subjective (tone, style, helpfulness, refusing correctly).
- You have, or can build, pairs of a preferred and a dispreferred response to the same prompt.

Usually run on top of an SFT model. Watch for length bias: if `chosen` is almost always longer
than `rejected`, the model learns "longer is better" instead of the quality you want.

## RLVR (RL from Verifiable Rewards) - TRL `GRPOTrainer`

Use when:

- Outputs can be checked by code: math with a known answer, code with unit tests,
  answers that must match a format or constraint.
- You want the model to discover answers rather than imitate given ones.

Key difference from SFT: SFT imitates gold responses; RLVR maximizes a reward. It needs a reward
function, more compute (several generations per prompt) and careful monitoring. On these servers
use a model of 3B or smaller unless you are prepared for long runs. With TRL, extra dataset
columns (for example `ground_truth`) are passed to the reward function as keyword arguments.

## When not to fine-tune

- Prompting or few-shot examples already reach the target: do not train.
- The model lacks facts that change often: use retrieval (RAG), not fine-tuning.
- There are fewer than a few hundred good examples: improve the data first.
