// Compaction tuned for the local vLLM models (Qwen3.8-27B, Fable-Distill, Gemma-4-31B).
//
// opencode's built-in compaction is left untouched for hosted models. When the
// session runs on a local provider (baseURL on localhost), this plugin:
//   1. slims the history fed to the summarizer: drops reasoning traces, trims
//      long tool outputs and long tool-call arguments (e.g. whole-file writes),
//      so the request stays well inside the 74400-token vLLM window;
//   2. appends local-model rules after opencode's default summary template
//      (the template, prior-summary merging and tail preservation still apply);
//   3. runs the compaction call with thinking off, low temperature and a capped
//      output budget, so a 27-31B model writes the summary instead of rambling.
import type { Plugin } from "@opencode-ai/plugin"

const MAX_SUMMARY_TOKENS = 6000
const TEMPERATURE = 0.3
const TOOL_OUTPUT_HEAD = 700
const TOOL_OUTPUT_TAIL = 500
const TOOL_ARG_MAX = 400

const LOCAL_RULES = `Additional rules (read carefully, they override anything above that conflicts):
- Start your reply directly with "## Objective". No preamble, no thinking out loud, no closing remarks.
- Keep the whole summary under about 1200 words. Prefer dropping finished, irrelevant detail over dropping open work.
- Quote the user's most recent request word for word inside "## Objective" as: Latest request: "<exact text>".
- Only state facts that appear in the conversation or tool results. If something was assumed but never checked, mark it "(unverified)".
- Do not paste code blocks or file contents. Point to them as path:line or path + symbol name instead.
- Keep error messages to one line each, copied exactly.
- Under "## Important Details", list every exact command that was run successfully and is likely to be needed again (build, test, run), plus any command that failed and why.
- Also under "## Important Details", list every correction or preference the user stated during the session ("don't do X", "use Y instead"), word for word.
- Under "## Next Move", write steps a fresh assistant can execute without re-reading the conversation.`

const LOCAL_HOSTS = /^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])$/

function isLocalURL(url: unknown): boolean {
  if (typeof url !== "string") return false
  try {
    return LOCAL_HOSTS.test(new URL(url).hostname)
  } catch {
    return false
  }
}

function clip(text: string, head: number, tail: number): string {
  if (text.length <= head + tail + 80) return text
  const omitted = text.length - head - tail
  return `${text.slice(0, head)}\n[... ${omitted} chars omitted ...]\n${text.slice(-tail)}`
}

function clipArgs(value: unknown): unknown {
  if (typeof value === "string") return value.length > TOOL_ARG_MAX ? clip(value, TOOL_ARG_MAX / 2, TOOL_ARG_MAX / 2) : value
  if (Array.isArray(value)) return value.map(clipArgs)
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, clipArgs(v)]))
  return value
}

export const LocalCompaction: Plugin = async ({ client }) => {
  // sessionID -> whether its latest LLM call went to a local provider
  const sessionLocal = new Map<string, boolean>()
  // sessions whose compaction is in progress and should be handled here
  const compacting = new Set<string>()

  let localProviders: Promise<Set<string>> | undefined
  const getLocalProviders = () =>
    (localProviders ??= client.config
      .get()
      .then(({ data }) => {
        const providers = (data?.provider ?? {}) as Record<string, { options?: { baseURL?: string } }>
        return new Set(Object.entries(providers).filter(([, p]) => isLocalURL(p.options?.baseURL)).map(([id]) => id))
      })
      .catch(() => new Set<string>()))

  // Used when opencode was restarted and no call has been seen for this session yet.
  async function lookupSession(sessionID: string): Promise<boolean> {
    const { data } = await client.session.messages({ path: { id: sessionID } })
    const last = data?.findLast((m) => m.info.role === "user")
    const providerID = last?.info.role === "user" ? last.info.model?.providerID : undefined
    if (!providerID) return false
    return (await getLocalProviders()).has(providerID)
  }

  return {
    "chat.params": async (input, output) => {
      const local = isLocalURL(input.provider.options?.baseURL ?? input.provider.info?.options?.baseURL)
      if (input.agent !== "compaction") {
        sessionLocal.set(input.sessionID, local)
        return
      }
      if (!local) return
      output.temperature = TEMPERATURE
      output.maxOutputTokens = Math.min(output.maxOutputTokens ?? MAX_SUMMARY_TOKENS, MAX_SUMMARY_TOKENS)
      output.options = {
        ...output.options,
        chat_template_kwargs: { ...(output.options?.chat_template_kwargs ?? {}), enable_thinking: false },
      }
    },

    "experimental.session.compacting": async (input, output) => {
      let local = sessionLocal.get(input.sessionID)
      if (local === undefined) local = await lookupSession(input.sessionID).catch(() => false)
      if (!local) return
      compacting.add(input.sessionID)
      output.context.push(LOCAL_RULES)
    },

    // opencode runs this on a clone of the history right after the hook above,
    // before serializing it for the summarizer. Normal turns are not flagged.
    "experimental.chat.messages.transform": async (_input, output) => {
      const sessionID = output.messages[0]?.info.sessionID
      if (!sessionID || !compacting.delete(sessionID)) return
      for (const message of output.messages) {
        message.parts = message.parts.filter((part) => part.type !== "reasoning")
        for (const part of message.parts) {
          if (part.type !== "tool") continue
          part.state.input = clipArgs(part.state.input) as typeof part.state.input
          if (part.state.status === "completed") part.state.output = clip(part.state.output, TOOL_OUTPUT_HEAD, TOOL_OUTPUT_TAIL)
        }
      }
    },
  }
}
