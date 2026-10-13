# opencode_local_agents

Local vLLM servers and opencode wiring so opencode runs entirely on this
box's H100s — no API key; model traffic never leaves the machine (only
web searches do, see section 6). Three agents:

| Agent | Weights | Port | Shortcut | Launcher |
|---|---|---|---|---|
| **Qwen3.8-27B** | bf16 / fp8 / mxfp4 | 42069 | `sqwen <16\|8\|4>` | `bin/start-qwen38` |
| **Qwen3.8-27B-Fable-Distill** | bf16 / fp8 / mxfp4 | 42071 | `sqwend <16\|8\|4>` | `bin/start-qwen38-distill` |
| **Gemma-4-31B-it** | bf16+fp8-KV / fp8 | 42070 | `sgemma <16\|8>` | `bin/start-gemma4` |

Both are drafted with multi-token prediction where available (Gemma uses its
MTP `...-assistant` checkpoint, `SPECS=6`), serve OpenAI-compatible
`/v1` with `--api-key EMPTY` on `127.0.0.1` only, and expose tool calling +
reasoning parsers.

## Layout — which file goes where

```
opencode_local_agents/
├── bin/start-qwen38      ->  ~/.local/bin/start-qwen38    (chmod +x)
├── bin/start-qwen38-distill -> ~/.local/bin/start-qwen38-distill (chmod +x)
├── bin/start-gemma4      ->  ~/.local/bin/start-gemma4    (chmod +x)
├── shell/aliases.sh      ->  append to ~/.bashrc          (sqwen/sqwend/sgemma,
│                                                          OPENCODE_ENABLE_EXA)
├── opencode/config.jsonc ->  merge into ~/.config/opencode/opencode.jsonc
├── opencode/skills/      ->  copy into ~/.config/opencode/skills/
├── opencode/plugin/      ->  copy into ~/.config/opencode/plugin/
├── opencode/prompts/     ->  copy into ~/.config/opencode/prompts/
└── README.md             ->  this file
```

### 1. `bin/start-qwen38`, `bin/start-qwen38-distill`, `bin/start-gemma4` — launchers

Each is a self-contained bash script: mode select, free-memory preflight
(refuses to launch unless `util × total` MiB are free), `setsid nohup` vLLM,
20-minute readiness poll, `stop`/`status` via pidfile, `DRYRUN=1` prints the
exact vLLM argv. State lives in `~/.local/state/{qwen38,qwen38-distill,gemma4}/`.

```bash
install -m 755 bin/start-qwen38 bin/start-qwen38-distill bin/start-gemma4 ~/.local/bin/
```

Env overrides (all): `GPU= <n>` `PORT= <n>` `MAXLEN= <n>` `MAXSEQ= <n>`
`FORCE=1` `WAIT=1` (poll until the card frees) `DRYRUN=1`.
Gemma also: `SPECS=<n>` (MTP draft depth, default 6) `THINK=0|1`.
Qwen (both) also: `EFFORT=xhigh|medium|low`.

`start-qwen38-distill` is `start-qwen38` with a different model path, port
(42071), state dir and served names (`qwen3.8-27b-distill-*`). The distill
has the same `qwen3_5` architecture and tensor layout as the base, so the
same quantization targets, util values and parsers apply. It runs on its own
port, so it can be up at the same time as `start-qwen38` on another GPU.

Paths hardcoded at the top of each script — adjust if the models or the
vLLM conda env move:

| | value |
|---|---|
| Qwen weights | `/opt/dlami/nvme/sarbajit/local_models/Qwen3.8-27B` |
| Qwen distill weights | `/opt/dlami/nvme/sarbajit/local_models/Qwen3.8-27B-Fable-Distill` |
| Gemma weights | `/opt/dlami/nvme/sarbajit/local_models/gemma4/gemma-4-31B-it` |
| Gemma MTP drafter | `.../gemma-4-31B-it-assistant` |
| vLLM | `/opt/dlami/nvme/sarbajit/miniconda3/bin/vllm` (v0.30.0) |

### 2. `shell/aliases.sh` — bashrc shortcuts

`sqwen` / `sqwend` / `sgemma` are thin wrappers that forward `<mode> [gpu]` and the
env passthrough to the launchers. Append to `~/.bashrc`, then
`source ~/.bashrc`. They're functions, so they only exist in interactive
shells that have read bashrc — scripts should call `start-qwen38` /
`start-qwen38-distill` / `start-gemma4` directly.

```bash
cat shell/aliases.sh >> ~/.bashrc
```

### 3. `opencode/config.jsonc` — provider + compaction

Merge (don't blind-copy unless this is a fresh config) into
`~/.config/opencode/opencode.jsonc`. It adds:

- `compaction`: `{ "auto": true, "prune": true }` — `prune` differs from the
  opencode default (`false`); it keeps compaction from ballooning.
- `provider.qwen-local` — 3 models on `127.0.0.1:42069`
- `provider.qwen-distill-local` — 3 models on `127.0.0.1:42071`
- `provider.gemma-local` — 2 models on `127.0.0.1:42070`

Each model's `limit.context` is its launcher's `MAXLEN - 8192` (output
stays 32768). opencode's send wall sits at `MAXLEN - 32000` prompt tokens,
compaction fires at `context - 32000`, and the compaction call itself
(`context`) fits under `MAXLEN`. Changing one side means changing the other.

| Mode | `MAXLEN` | `limit.context` | Compacts at | Why this `MAXLEN` |
|---|---|---|---|---|
| qwen / qwen-distill 16 | 262144 | 253952 | 221952 | native max (no YaRN); KV pool is 313,069 tokens at util 0.94 |
| qwen / qwen-distill 4 | 98304 | 90112 | 58112 | KV pool is 103,865 tokens at util 0.35 |
| gemma 16 | 90112 | 81920 | 49920 | KV pool is 92,401 tokens (fp8 KV, util 0.94) |
| all 8 (fp8) | 74400 | 65536 | 33536 | not measured yet; old budget |

The pools are the "GPU KV cache size" lines from each server's boot log.

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

### 5. `opencode/plugin/local-compaction.ts` — compaction for local models

opencode loads every `.ts` in `~/.config/opencode/plugin/` at startup. This
one leaves the built-in compaction alone for hosted models and, when the
session's provider is on localhost, makes it fit a 27-31B model:

- drops reasoning traces and trims long tool outputs/arguments in the
  history sent to the summarizer;
- appends local-model rules after opencode's default summary template;
- runs the summary call with thinking off, temperature 0.3 and at most
  6000 output tokens (constants at the top of the file).

```bash
mkdir -p ~/.config/opencode/plugin
cp opencode/plugin/local-compaction.ts ~/.config/opencode/plugin/
```

### 6. `opencode/prompts/local.md` + `opencode/plugin/local-prompt.ts` — system prompt for local models

For any model whose provider is on localhost, `local-prompt.ts` swaps
opencode's built-in system prompt (the generic one every non-GPT/Claude/
Gemini model gets, ~2k tokens) for `prompts/local.md`. Hosted models are
untouched, and everything opencode appends after the prompt (environment,
AGENTS.md / `~/.claude/CLAUDE.md`, skills) stays. `local.md` is re-read on
every request, so edits apply without a restart.

`local.md` covers: look before acting, minimal idiomatic edits, verifying
with the project's own tests/linters, CSV (pandas) and PDF (pypdf) reading
with the sarbajit conda python, web research (search, then fetch and cite
primary sources at the right version), and git rules (commit only when
asked, push only when asked, the user's identity, no AI attribution, no
destructive commands). It drops the built-in "under 4 lines / one-word
answers" rule, which cut code explanations short.

The built-in prompt is located by its fixed first and last lines; if an
opencode update changes them, the plugin does nothing and the built-in
prompt is used.

**Web search.** opencode only registers its `websearch` tool for the
opencode-hosted provider unless `OPENCODE_ENABLE_EXA=1` is set, so
`shell/aliases.sh` exports it. Searches go to Exa (no API key needed;
`EXA_API_KEY` raises limits) — this is the one path where queries leave
the machine. `webfetch` works without it.

```bash
mkdir -p ~/.config/opencode/plugin ~/.config/opencode/prompts
cp opencode/plugin/local-prompt.ts ~/.config/opencode/plugin/
cp opencode/prompts/local.md ~/.config/opencode/prompts/
```

## Usage

```bash
sqwen 16            # qwen bf16   on GPU0
sqwend 8 2          # qwen fable-distill fp8 on GPU2
sgemma 16           # gemma bf16 + fp8 KV + TRITON_ATTN + MTP on GPU0
sgemma status
sgemma stop

# one-shot / scripted:
opencode run -m gemma-local/gemma-4-31b-bf16 "hello"
opencode run -m qwen-local/qwen3.8-27b-bf16  "hello"
opencode run -m qwen-distill-local/qwen3.8-27b-distill-bf16 "hello"
```

Mode-16 for any model wants the whole card (~77 GiB free) — they can't
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
