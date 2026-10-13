// Replaces opencode's built-in system prompt with prompts/local.md for the
// local vLLM providers (baseURL on localhost). Hosted models keep the
// built-in prompt. AGENTS.md / CLAUDE.md instructions, environment info and
// skills that opencode appends after the prompt are left in place.
//
// opencode joins [builtin prompt, ...agent/env/instructions] into system[0].
// The built-in prompt has no separator, so it is located by its fixed first
// and last lines. If a future opencode changes them, nothing is replaced.
import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"

const PROMPT_FILE = new URL("../prompts/local.md", import.meta.url)
const BUILTIN_START = "You are opencode, an interactive CLI tool that helps users with software engineering tasks."
const BUILTIN_END = "src/services/process.ts:712.\n</example>"

const LOCAL_HOSTS = /^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])$/

function isLocalURL(url: unknown): boolean {
  if (typeof url !== "string") return false
  try {
    return LOCAL_HOSTS.test(new URL(url).hostname)
  } catch {
    return false
  }
}

export const LocalPrompt: Plugin = async ({ client }) => {
  let localProviders: Promise<Set<string>> | undefined
  const getLocalProviders = () =>
    (localProviders ??= client.config
      .get()
      .then(({ data }) => {
        const providers = (data?.provider ?? {}) as Record<string, { options?: { baseURL?: string } }>
        return new Set(Object.entries(providers).filter(([, p]) => isLocalURL(p.options?.baseURL)).map(([id]) => id))
      })
      .catch(() => new Set<string>()))

  return {
    "experimental.chat.system.transform": async (input, output) => {
      if (!(await getLocalProviders()).has(input.model.providerID)) return
      const system = output.system[0]
      if (!system?.startsWith(BUILTIN_START)) return
      const end = system.indexOf(BUILTIN_END)
      if (end === -1) return
      // Read on every call so edits to local.md apply without a restart.
      const prompt = (await readFile(PROMPT_FILE, "utf8").catch(() => "")).trim()
      if (!prompt) return
      output.system[0] = prompt + system.slice(end + BUILTIN_END.length)
    },
  }
}
