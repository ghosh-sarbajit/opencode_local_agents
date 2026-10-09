---
name: paper_citation_download
description: Builds a .bib file from a list of paper titles, in Google Scholar's BibTeX style plus two extra fields — howpublished = "\url{DOI | official proceedings page | arXiv link}" and comment = {short note}. Use when the user gives paper titles (or a file of them) and asks to download, fetch, collect or generate citations, BibTeX or a bibliography / references .bib file.
---

# Paper citation download

Turn a list of paper titles into one `.bib` file. Each entry is what Google
Scholar's "Cite → BibTeX" gives, with two fields appended:

```bibtex
@inproceedings{biderman2023pythia,
    title={Pythia: A suite for analyzing large language models across training and scaling},
    author={Biderman, Stella and Schoelkopf, Hailey and Anthony, Quentin Gregory and Bradley, Herbie and O’Brien, Kyle and Hallahan, Eric and Khan, Mohammad Aflah and Purohit, Shivanshu and Prashanth, USVSN Sai and Raff, Edward and others},
    booktitle={International conference on machine learning},
    pages={2397--2430},
    year={2023},
    organization={PMLR},
    howpublished = "\url{https://proceedings.mlr.press/v202/biderman23a.html}",
    comment = {Pythia model base paper}
}
```

Format rules (the script follows them; keep them when you edit by hand):
- Indent fields by 4 spaces. Scholar fields are written `name={value},` with no spaces around `=`.
- `howpublished = "\url{...}",` and `comment = {...}` are the last two fields, in that order, with spaces around `=`. There is no comma after `comment`.
- **howpublished link priority:** if the paper was published, use its DOI as
  `https://doi.org/<doi>`. If there is no DOI, use the official proceedings page
  (PMLR, papers.nips.cc, OpenReview forum for ICLR/TMLR/COLM, ACL Anthology,
  usenix.org, ...). Use `https://arxiv.org/abs/<id>` only when the paper is a
  preprint, or when no published version exists.
- **comment:** a short note of 3 to 8 words saying what the paper is or why it is cited, e.g.
  `Pythia model base paper`, `Exposure metric for memorization`,
  `IndicTrans2 translation model paper`. Don't end it with a period.
- Scholar keys are `<first author's last name><year><first title word that isn't a stopword>`, all lowercase (for example `vaswani2017attention`).

## Steps

### 1. Write the title list

Put the user's papers into a text file with one title per line, e.g.
`papers.txt` next to where the `.bib` should go. If the user gave a comment
for a paper, add it after `||`:

```
Pythia: A suite for analyzing large language models across training and scaling || Pythia model base paper
The secret sharer: Evaluating and testing unintended memorization in neural networks
```

Lines starting with `#`, blank lines, and leading `1.` or `-` bullets are
ignored. If the user gave only a paper's nickname ("the Pythia paper"), work
out its full title first.

### 2. Run the fetcher

```bash
python3 ~/.config/opencode/skills/paper_citation_download/scripts/fetch_bib.py papers.txt -o references.bib
```

- Use the output name the user asked for, otherwise `references.bib`.
- It **appends** to an existing `.bib` and skips titles that are already in it,
  so it is safe to re-run with a longer list.
- Each paper takes 5 to 30 s because of rate limits, so expect several minutes for long lists. Use
  a generous timeout (for example 600000 ms for 20 papers), or split long lists into chunks.
- Next to the `.bib` it writes `references.report.json`, with one record per paper:
  `key`, `status` (`OK` / `REVIEW` / `NOT FOUND` / `SKIPPED`), `matched_title`,
  `venue`, `year`, `howpublished`, `sources`, `flags`, `abstract`.

The script tries Google Scholar first and copies its BibTeX exactly. Scholar
usually blocks scripts with a 403, so the script falls back to DBLP, OpenReview,
Crossref, Semantic Scholar, arXiv, OpenAlex and the PMLR / NeurIPS indexes,
and rebuilds the entry in Scholar's style.
"sources unavailable" at the end of the run is normal. It is a problem only
when every source failed.

### 3. Resolve every flag in the report

Read `references.report.json`. For each paper whose `status` is not `OK`,
fix the matching entry in the `.bib` with the edit tool:

| flag | what to do |
|---|---|
| `comment is empty` | Write a 3 to 8 word comment from `matched_title`, `venue` and `abstract`. If the user said why the paper is cited, use that. |
| `published at '<venue>' but only an arXiv link was found` | Find the official link with `webfetch`. Recipes are below. Replace the arXiv URL with it. If none exists, keep the arXiv link. |
| `only a preprint record was found` | Many papers in the database are only on arXiv. Check whether this one was published: open `https://arxiv.org/abs/<id>` (look at "Comments" and "Journal reference"), and search `https://api2.openreview.net/notes/search?term=<title>&source=forum`. If it was published, change it to the Scholar-style venue entry (e.g. NeurIPS → `@article`, `journal={Advances in neural information processing systems}`, `volume={<year-1987>}`), and fix the year, the key and the link. If it wasn't, leave it as is. |
| `venue taken from the arXiv comment` | Check the venue and year, then find the official link with the recipes below. |
| `year ... may be the arXiv year` | Check the year the venue published it (e.g. USENIX Security '19 → `2019`). Fix `year`, the ordinal in `booktitle`, and the year in the key. |
| `venue ... not confirmed` / `no venue found` | Find the published venue with `webfetch`. Write `booktitle` / `journal` the way Scholar does, e.g. `Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)`. |
| `author first names are abbreviated` | Fetch the arXiv or official page and write the full first names. |
| `NOT FOUND` | Check the title for typos, then search with `webfetch` (`https://arxiv.org/a/...`, `https://api.crossref.org/works?query.bibliographic=<title>`, `https://openreview.net/search?term=<title>`). If it still can't be found, write the entry by hand in the same format and tell the user. |

Official-link recipes:
- **ICML / AISTATS / COLT (PMLR):** open `https://proceedings.mlr.press/v<vol>/`, find the title, and use its `...html` abs link.
- **NeurIPS:** open `https://papers.nips.cc/paper_files/paper/<year>`, find the title, and use its `...-Abstract*.html` link.
- **ICLR / TMLR / COLM:** use `https://openreview.net/forum?id=<id>`.
- **ACL / EMNLP / NAACL / EACL / COLING / TACL:** use the DOI `10.18653/v1/...` if the anthology page lists one, otherwise `https://aclanthology.org/<id>/`.
- **USENIX:** use the paper's page on `https://www.usenix.org/conference/usenixsecurity<yy>/presentation/<author>`.
- **IEEE / ACM / Springer / Elsevier / journals:** always use the DOI.

Do not make up a DOI, URL, page range or venue. If you cannot verify one,
leave the value the script found and mention it in your summary.

### 4. Check the result

```bash
python3 - <<'EOF'
import re
t = open("references.bib", encoding="utf-8").read()
entries = re.findall(r"^@\w+\{[^@]*?^\}", t, re.M | re.S)
keys = re.findall(r"^@\w+\{([^,]+),", t, re.M)
print(len(entries), "entries;", "duplicate keys:", {k for k in keys if keys.count(k) > 1} or "none")
for e in entries:
    k = re.match(r"@\w+\{([^,]+),", e).group(1)
    if not re.search(r'howpublished = "\\url\{https?://[^}]+\}",', e): print("bad howpublished:", k)
    if re.search(r"comment = \{\s*\}", e): print("empty comment:", k)
    if e.count("{") != e.count("}"): print("unbalanced braces:", k)
EOF
```

Every entry must have a non-empty `howpublished` URL and a non-empty `comment`.

### 5. Report back

Tell the user:
- the path to the `.bib` and how many entries it has
- which entries you changed by hand and why (for example "replaced the arXiv link with the PMLR page")
- anything still uncertain, such as a paper that wasn't found or a venue you couldn't confirm.

Don't paste the whole `.bib` into chat unless they ask for it.

## Notes

- Optional env vars: `S2_API_KEY` (a Semantic Scholar API key, which avoids 429s) and
  `CROSSREF_MAILTO=<email>` (puts requests in Crossref's faster pool).
- `--no-scholar` skips the Google Scholar attempt. Use it if Scholar is known to be blocked.
- If the user pastes Scholar BibTeX themselves, don't fetch anything for that
  paper. Re-indent it to 4 spaces and add `howpublished` and `comment`.
