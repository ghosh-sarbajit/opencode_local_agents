# opencode_local_agents

Local vLLM servers and opencode wiring so opencode runs entirely on this
box's H100s — no API key, no traffic leaving the machine. Two agents:

| Agent | Weights | Port | Shortcut | Launcher |
|---|---|---|---|---|
| **Qwen3.8-27B** | bf16 / fp8 / mxfp4 | 42069 | `sqwen <16\|8\|4>` | `bin/start-qwen38` |
| **Gemma-4-31B-it** | bf16+fp8-KV / fp8 | 42070 | `sgemma <16\|8>` | `bin/start-gemma4` |

Both are drafted with multi-token prediction where available (Gemma uses its
MTP `...-assistant` checkpoint, `SPECS=6`), serve OpenAI-compatible
`/v1` with `--api-key EMPTY` on `127.0.0.1` only, and expose tool calling +
reasoning parsers.

## Layout — which file goes where

```
opencode_local_agents/
├── bin/start-qwen38      ->  ~/.local/bin/start-qwen38    (chmod +x)
├── bin/start-gemma4      ->  ~/.local/bin/start-gemma4    (chmod +x)
├── shell/aliases.sh      ->  append to ~/.bashrc          (sqwen/sgemma)
├── opencode/config.jsonc ->  merge into ~/.config/opencode/opencode.jsonc
├── opencode/skills/      ->  copy into ~/.config/opencode/skills/
└── README.md             ->  this file
```

### 1. `bin/start-qwen38`, `bin/start-gemma4` — launchers

Each is a self-contained bash script: mode select, free-memory preflight
(refuses to launch unless `util × total` MiB are free), `setsid nohup` vLLM,
20-minute readiness poll, `stop`/`status` via pidfile, `DRYRUN=1` prints the
exact vLLM argv. State lives in `~/.local/state/{qwen38,gemma4}/`.

```bash
install -m 755 bin/start-qwen38 bin/start-gemma4 ~/.local/bin/
```

Env overrides (both): `GPU= <n>` `PORT= <n>` `MAXLEN= <n>` `MAXSEQ= <n>`
`FORCE=1` `WAIT=1` (poll until the card frees) `DRYRUN=1`.
Gemma also: `SPECS=<n>` (MTP draft depth, default 6) `THINK=0|1`.
Qwen also: `EFFORT=xhigh|medium|low`.

Paths hardcoded at the top of each script — adjust if the models or the
vLLM conda env move:

| | value |
|---|---|
| Qwen weights | `/opt/dlami/nvme/sarbajit/local_models/Qwen3.8-27B` |
| Gemma weights | `/opt/dlami/nvme/sarbajit/local_models/gemma4/gemma-4-31B-it` |
| Gemma MTP drafter | `.../gemma-4-31B-it-assistant` |
| vLLM | `/opt/dlami/nvme/sarbajit/miniconda3/bin/vllm` (v0.30.0) |

### 2. `shell/aliases.sh` — bashrc shortcuts

`sqwen` / `sgemma` are thin wrappers that forward `<mode> [gpu]` and the
env passthrough to the launchers. Append to `~/.bashrc`, then
`source ~/.bashrc`. They're functions, so they only exist in interactive
shells that have read bashrc — scripts should call `start-qwen38` /
`start-gemma4` directly.

```bash
cat shell/aliases.sh >> ~/.bashrc
```

### 3. `opencode/config.jsonc` — provider + compaction

Merge (don't blind-copy unless this is a fresh config) into
`~/.config/opencode/opencode.jsonc`. It adds:

- `compaction`: `{ "auto": true, "prune": true }` — `prune` differs from the
  opencode default (`false`); it keeps compaction from ballooning.
- `provider.qwen-local` — 3 models on `127.0.0.1:42069`
- `provider.gemma-local` — 2 models on `127.0.0.1:42070`

Both declare `limit: { context: 65536, output: 32768 }`. That pairs with
the launchers' `MAXLEN=74400`: opencode's send wall sits at
`MAXLEN - 32000 = 42400` prompt tokens, compaction fires at
`65536 - 32000 = 33536`, and the compaction call itself
(`33536 + 32000 = 65536`) fits — 8864 tokens of slack. Changing one side
means changing the other.

**opencode reads config at startup only.** After any edit: restart the TUI
(or `opencode run -m <provider>/<model>` for one-shots).

### 4. `opencode/skills/` — agent skills

| Skill | What it does |
|---|---|
| `paper_citation_download` | Turns a list of paper titles into a `.bib` in Google Scholar's BibTeX style, with `howpublished = "\url{DOI \| official page \| arXiv}"` and a short `comment` added to each entry. `scripts/fetch_bib.py` does the lookups: Scholar when it answers, otherwise DBLP, OpenReview, Crossref, Semantic Scholar, arXiv, OpenAlex, and the PMLR/NeurIPS indexes. It writes a review report, and the agent then resolves the flagged entries and fills in the comments. |

```bash
mkdir -p ~/.config/opencode/skills
cp -r opencode/skills/* ~/.config/opencode/skills/
```

Then restart opencode and ask, e.g. *"make references.bib for the papers in
papers.txt"*. Optional env: `S2_API_KEY` (avoids Semantic Scholar 429s),
`CROSSREF_MAILTO`.

## Usage

```bash
sqwen 16            # qwen bf16   on GPU0
sgemma 16           # gemma bf16 + fp8 KV + TRITON_ATTN + MTP on GPU0
sgemma status
sgemma stop

# one-shot / scripted:
opencode run -m gemma-local/gemma-4-31b-bf16 "hello"
opencode run -m qwen-local/qwen3.8-27b-bf16  "hello"
```

Mode-16 for either model wants the whole card (~77 GiB free) — they can't
share a GPU with each other. Mode 8/4 are the co-resident options.

## Gotchas worth knowing

- **Gemma 16-bit needs fp8 KV.** 62.9 GiB weights/activations + 19.0 GiB
  bf16 KV at 74400 = 83.6 GiB > 79.65 GiB physical, so `--kv-cache-dtype
  fp8` is mandatory, and with it only `TRITON_ATTN` validates (FlashInfer's
  fa2 JIT asserts on fp8 KV; `FLASH_ATTN` wants FA3/FA4). The full
  backend-failure history is in the mode table of `start-gemma4`.
- **`start-gemma4 8` and `start-gemma4 16` share port 42070** — stop one
  before starting the other (`PORT=` to override).
- **Preflight is the guard, not a formality.** `util=0.94` on an 80 GB card
  means ~75 GiB must be free *before* launch; `FORCE=1` skips the check and
  will happily OOM whatever else is on the card.
