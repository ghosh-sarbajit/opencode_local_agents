---
name: web-search-and-cite
description: Search the web for current or post-training-cutoff information (versions, releases, docs, news, prices) and answer with mandatory source links. Use for any question whose answer may have changed recently.
---

# Web search with citations

## Searching
- Use the `websearch` tool if opencode exposes one. Otherwise run the bundled script:
  `python3 ~/.config/opencode/skills/deep-research/scripts/search.py "query" -n 8`
  (see the deep-research skill for backend setup).
- **Use the current year.** Check `date +%Y` first. "Latest React docs" means searching
  for the current year's docs, not the year your training data ends in.
- Write queries like a person types them: short, with specific nouns and version numbers.
  Run 2–4 different phrasings rather than one long query.
- Domain filtering: to stick to official sources add `site:docs.example.com`, and to drop a
  noisy site add `-site:example.com`. Choose one approach per query, not both.
- Budget: about 8 searches per question. If that isn't enough, switch to the deep-research skill.

## Picking sources
Rank by authority: official docs, changelogs or release notes, the source repo or maintainer
posts, standards bodies, reputable press, then blogs, then forums. Prefer the newest dated
source when facts conflict, and say that they conflict.

When a snippet isn't enough, open the page with the webfetch-and-summarize skill.

## Answer format (mandatory)
Answer first, then a sources section listing every URL you relied on:

```
<answer>

Sources:
- [Page title](https://...)
- [Page title](https://...)
```

Never skip the Sources section. Never cite a URL you didn't actually see in results or fetch.
