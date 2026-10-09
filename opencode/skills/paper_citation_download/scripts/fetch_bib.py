#!/usr/bin/env python3
"""Turn a list of paper titles into a Google-Scholar-style .bib file.

Every entry gets two extra fields appended after the Scholar fields:

    howpublished = "\\url{<DOI | official proceedings page | arXiv abs>}",
    comment = {<short note>}

Google Scholar's own "Cite -> BibTeX" is used verbatim when Scholar answers
(it usually 403s scripted clients). Otherwise the entry is rebuilt in
Scholar's style from: DBLP, OpenReview (also mirrors DBLP records), Crossref,
Semantic Scholar, arXiv, OpenAlex, and the PMLR / NeurIPS proceedings indexes.
A source that is down or refusing is skipped for the rest of the run.

Usage:
  fetch_bib.py papers.txt -o refs.bib            # one title per line
  fetch_bib.py -t "Attention is all you need" -o refs.bib
  papers.txt lines may carry a comment:  <title> || <comment>
  Lines starting with '#' and blank lines are ignored.

Writes <out>.bib (appending; titles already in it are skipped) and
<out>.report.json with, per paper: key, status, sources used, matched title,
venue, the chosen link, an abstract snippet, and `flags` the agent must
resolve. Exit status is 0 even when some papers fail.

Optional env: S2_API_KEY (Semantic Scholar key, avoids 429s),
CROSSREF_MAILTO (puts you in Crossref's polite pool).
"""

import argparse
import difflib
import html
import json
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET

import requests

TIMEOUT = 25
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
UA_TOOL = "paper-citation-download/1.0" + (
    f" (mailto:{os.environ['CROSSREF_MAILTO']})" if os.environ.get("CROSSREF_MAILTO") else "")
MATCH_OK = 0.90  # normalized-title similarity needed to accept a hit

SESSION = requests.Session()
DISABLED = set()   # sources that refused us; skipped for the rest of the run
FAILS = {}         # consecutive network failures per source
CACHE = {}         # url -> text, for proceedings index pages


# --------------------------------------------------------------------------- utils

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def norm_title(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[{}\\$]", "", t.lower())
    return " ".join(re.findall(r"[a-z0-9]+", t))


def sim(a, b):
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def get(url, source, *, params=None, headers=None, retries=3, timeout=TIMEOUT):
    """GET with backoff on 429/5xx. 401/403, or 2 papers in a row of network
    failures, disable the source for the rest of the run."""
    if source in DISABLED:
        return None
    hdrs = {"User-Agent": UA_TOOL}
    hdrs.update(headers or {})
    delay = 3
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, headers=hdrs, timeout=timeout)
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            FAILS[source] = FAILS.get(source, 0) + 1
            log(f"  [{source}] network error: {type(e).__name__}")
            if FAILS[source] >= 2:
                DISABLED.add(source)
                log(f"  [{source}] unreachable; disabled for this run")
            return None
        FAILS[source] = 0
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            ra = r.headers.get("Retry-After", "")
            time.sleep(min(int(ra) if ra.isdigit() else delay, 30))
            delay *= 2
            continue
        if r.status_code in (401, 403):
            DISABLED.add(source)
            log(f"  [{source}] HTTP {r.status_code}; disabled for this run")
        else:
            log(f"  [{source}] HTTP {r.status_code}")
        return None
    return None


def split_name(full):
    """'USVSN Sai Prashanth' -> ('USVSN Sai', 'Prashanth'); keeps particles."""
    full = re.sub(r"\s+\d{4}$", "", (full or "").strip())  # DBLP homonym suffix
    if "," in full:
        last, first = [p.strip() for p in full.split(",", 1)]
        return first, last
    parts = full.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    particles = {"van", "von", "der", "den", "de", "del", "della", "di", "da",
                 "dos", "du", "la", "le", "ter", "ten"}
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in particles:
        i -= 1
    return " ".join(parts[:i]), " ".join(parts[i:])


def abbreviated(authors):
    """True when names look like 'N. Parmar' (S2 style) rather than full."""
    return any(re.fullmatch(r"([A-Z]\.\s*)+", f.strip()) for f, _ in authors)


def tex_escape(s):
    s = re.sub(r"(?<!\\)&", r"\\&", s)
    s = re.sub(r"(?<!\\)%", r"\\%", s)
    s = re.sub(r"(?<!\\)#", r"\\#", s)
    return re.sub(r"\s+", " ", s).strip()


def year_in(s):
    m = re.search(r"\b(19|20)\d{2}\b", s or "")
    return m.group(0) if m else None


ORDINALS = ["", "First", "Second", "Third", "Fourth", "Fifth", "Sixth",
            "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth",
            "Thirteenth", "Fourteenth", "Fifteenth", "Sixteenth",
            "Seventeenth", "Eighteenth", "Nineteenth", "Twentieth"]


def nth(n):
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


# ------------------------------------------------------------------ Google Scholar

def from_scholar(title):
    """Return Scholar's verbatim BibTeX string, or None."""
    h = {"User-Agent": UA_BROWSER, "Accept-Language": "en-US,en;q=0.9"}
    r = get("https://scholar.google.com/scholar", "scholar",
            params={"q": title, "hl": "en"}, headers=h, retries=1)
    if r is None or "gs_captcha" in r.text or "unusual traffic" in r.text:
        DISABLED.add("scholar")
        return None
    m = re.search(r'data-cid="([^"]+)"', r.text)
    if not m:
        return None
    r = get("https://scholar.google.com/scholar", "scholar",
            params={"q": f"info:{m.group(1)}:scholar.google.com/",
                    "output": "cite", "scirp": "0", "hl": "en"},
            headers=h, retries=1)
    m = re.search(r'href="([^"]*scholar\.bib[^"]*)"', r.text) if r else None
    if not m:
        return None
    url = html.unescape(m.group(1))
    if url.startswith("/"):
        url = "https://scholar.google.com" + url
    time.sleep(2)
    r = get(url, "scholar", headers=h, retries=1)
    if r is None or not r.text.lstrip().startswith("@"):
        return None
    bib = r.text.strip()
    t = re.search(r"title\s*=\s*\{(.*?)\},?\s*\n", bib)
    if not t or sim(t.group(1), title) < MATCH_OK:
        return None
    return bib


# ----------------------------------------------------------------- bibliographic DBs

def from_dblp(title):
    r = get("https://dblp.org/search/publ/api", "dblp",
            params={"q": title, "format": "json", "h": 10}, retries=2)
    if r is None:
        return []
    out = []
    for h in r.json().get("result", {}).get("hits", {}).get("hit", []) or []:
        info = h.get("info", {})
        if sim(info.get("title", ""), title) < MATCH_OK:
            continue
        authors = info.get("authors", {}).get("author", [])
        authors = [authors] if isinstance(authors, dict) else authors
        venue = info.get("venue", "")
        venue = " ".join(venue) if isinstance(venue, list) else venue
        ee = info.get("ee", [])
        out.append({
            "src": "dblp", "title": info.get("title", "").rstrip("."),
            "authors": [split_name(a.get("text", "")) for a in authors],
            "year": info.get("year"), "venue": venue,
            "volume": info.get("volume"), "number": info.get("number"),
            "pages": info.get("pages"),
            "conf": "Conference" in info.get("type", ""),
            "preprint": venue == "CoRR" or "Informal" in info.get("type", ""),
            "doi": info.get("doi"),
            "urls": ee if isinstance(ee, list) else [ee],
        })
    return out


def from_openreview(title):
    """OpenReview search: native ICLR/ICML/NeurIPS/TMLR notes plus DBLP mirrors."""
    r = get("https://api2.openreview.net/notes/search", "openreview",
            params={"term": title, "type": "terms", "content": "all",
                    "source": "forum", "limit": 10})
    if r is None:
        return []
    out = []
    for n in r.json().get("notes", []):
        c = n.get("content", {})
        g = lambda k: (c.get(k) or {}).get("value") if isinstance(c.get(k), dict) else c.get(k)
        t = g("title") or ""
        if sim(t, title) < MATCH_OK:
            continue
        venue, vid = g("venue") or "", g("venueid") or ""
        if re.search(r"submission|workshop|/ARR/|withdrawn|rejected", f"{venue} {vid}", re.I) \
                or not venue:
            continue
        bib = g("_bibtex") or ""
        pages = re.search(r"pages\s*=\s*\{([^}]*)\}", bib)
        native = not vid.startswith("dblp.org") and vid != "OpenReview.net/Archive"
        urls = [u for u in (g("html"),) if u]
        if native:
            urls.append(f"https://openreview.net/forum?id={n['forum']}")
        out.append({
            "src": "openreview", "title": t, "venue": venue, "venueid": vid,
            "authors": [split_name(a) for a in (g("authors") or [])],
            "year": year_in(vid) or year_in(venue),
            "pages": pages.group(1) if pages else None,
            "preprint": "CORR" in vid.upper() or venue.startswith("CoRR"),
            "native": native, "urls": urls, "abstract": g("abstract"),
        })
    return out


def from_crossref(title):
    r = get("https://api.crossref.org/works", "crossref",
            params={"query.bibliographic": title, "rows": 5,
                    "select": "DOI,title,author,container-title,page,volume,"
                              "issue,publisher,type,issued"})
    if r is None:
        return []
    out = []
    for it in r.json().get("message", {}).get("items", []):
        t = (it.get("title") or [""])[0]
        if sim(t, title) < MATCH_OK:
            continue
        date = (it.get("issued") or {}).get("date-parts", [[None]])
        out.append({
            "src": "crossref", "title": t,
            "authors": [(a.get("given", ""), a.get("family", a.get("name", "")))
                        for a in it.get("author", [])],
            "year": str(date[0][0]) if date and date[0] and date[0][0] else None,
            "container": (it.get("container-title") or [""])[0],
            "pages": it.get("page"), "volume": it.get("volume"),
            "number": it.get("issue"), "publisher": it.get("publisher"),
            "conf": it.get("type") == "proceedings-article",
            "preprint": it.get("type") not in ("proceedings-article", "journal-article",
                                               "book-chapter")
                        or (it.get("DOI") or "").startswith("10.48550"),
            "doi": it.get("DOI"),
        })
    return out


def from_s2(title):
    h = {"x-api-key": os.environ["S2_API_KEY"]} if os.environ.get("S2_API_KEY") else {}
    r = get("https://api.semanticscholar.org/graph/v1/paper/search/match", "s2",
            params={"query": title,
                    "fields": "title,year,venue,externalIds,authors,abstract"},
            headers=h, retries=4)
    if r is None:
        return None
    data = (r.json().get("data") or [None])[0]
    if not data or sim(data.get("title", ""), title) < MATCH_OK:
        return None
    return {
        "src": "s2", "title": data["title"],
        "authors": [split_name(a["name"]) for a in data.get("authors", [])],
        "year": str(data["year"]) if data.get("year") else None,
        "venue": data.get("venue") or "",
        "ext": data.get("externalIds") or {},
        "abstract": data.get("abstract"),
    }


def from_arxiv(title):
    q = re.sub(r"[^\w\s]", " ", title)
    r = get("https://export.arxiv.org/api/query", "arxiv",
            params={"search_query": f'ti:"{" ".join(q.split())}"', "max_results": 5},
            retries=3, timeout=40)
    if r is None:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    best, best_s = None, 0
    try:
        entries = ET.fromstring(r.content).findall("a:entry", ns)
    except ET.ParseError:
        return None
    for e in entries:
        t = " ".join(e.findtext("a:title", "", ns).split())
        s = sim(t, title)
        if s >= MATCH_OK and s > best_s:
            aid = e.findtext("a:id", "", ns).rsplit("/abs/", 1)[-1]
            best_s, best = s, {
                "src": "arxiv", "title": t, "id": re.sub(r"v\d+$", "", aid),
                "authors": [split_name(a.findtext("a:name", "", ns))
                            for a in e.findall("a:author", ns)],
                "year": e.findtext("a:published", "", ns)[:4],
                "abstract": " ".join(e.findtext("a:summary", "", ns).split()),
                # e.g. "Accepted at NeurIPS 2017" / journal ref: venue hint
                "note": " ".join(f"{e.findtext('x:journal_ref', '', ns)} "
                                 f"{e.findtext('x:comment', '', ns)}".split()),
            }
    return best


def from_openalex(title):
    """Used for full author names and arXiv ids when arXiv itself is slow."""
    r = get("https://api.openalex.org/works", "openalex",
            params={"search": title, "per_page": 5,
                    "select": "title,doi,publication_year,authorships,locations"})
    if r is None:
        return None
    for w in r.json().get("results", []):
        if sim(w.get("title") or "", title) < MATCH_OK:
            continue
        aid = None
        for loc in w.get("locations") or []:
            m = re.search(r"arxiv\.org/abs/([\w.\-/]+?)(v\d+)?$", loc.get("landing_page_url") or "")
            if m:
                aid = m.group(1)
                break
        return {"src": "openalex", "title": w["title"], "arxiv": aid,
                "authors": [split_name(a["author"]["display_name"])
                            for a in w.get("authorships") or []]}
    return None


# ------------------------------------------------------------- proceedings indexes

# PMLR volume numbers (proceedings.mlr.press/v<N>/)
PMLR_VOL = {
    "icml": {2013: 28, 2014: 32, 2015: 37, 2016: 48, 2017: 70, 2018: 80, 2019: 97,
             2020: 119, 2021: 139, 2022: 162, 2023: 202, 2024: 235, 2025: 267},
    "aistats": {2017: 54, 2018: 84, 2019: 89, 2020: 108, 2021: 130, 2022: 151,
                2023: 206, 2024: 238, 2025: 258},
}


def index_page(url, source):
    if url not in CACHE:
        r = get(url, source, headers={"User-Agent": UA_BROWSER}, timeout=60)
        CACHE[url] = r.text if r else ""
    return CACHE[url]


def from_pmlr(title, conf, year):
    vol = PMLR_VOL.get(conf, {}).get(int(year)) if year else None
    if not vol:
        return None
    txt = index_page(f"https://proceedings.mlr.press/v{vol}/", "pmlr")
    for block in re.split(r'<div class="paper">', txt)[1:]:
        t = re.search(r'<p class="title">(.*?)</p>', block, re.S)
        if not t or sim(html.unescape(t.group(1)), title) < MATCH_OK:
            continue
        a = re.search(r'<span class="authors">(.*?)</span>', block, re.S)
        p = re.search(r"PMLR \d+:([\d\-]+)", block)
        u = re.search(r'href="(https://proceedings\.mlr\.press/v\d+/[^"]+\.html)"', block)
        return {
            "src": "pmlr", "url": u.group(1) if u else None,
            "pages": p.group(1) if p else None,
            "authors": [split_name(html.unescape(x))
                        for x in re.split(r",\s*", (a.group(1) if a else "").replace("&nbsp;", " "))
                        if x.strip()],
        }
    return None


def from_neurips(title, year):
    if not year:
        return None
    txt = index_page(f"https://papers.nips.cc/paper_files/paper/{year}", "neurips")
    for href, t in re.findall(r'<a title="paper title" href="([^"]+)">(.*?)</a>', txt):
        if sim(html.unescape(t), title) >= MATCH_OK:
            return {"src": "neurips", "url": "https://papers.nips.cc" + href}
    return None


# ------------------------------------------------------------------ Scholar styling

KEY_STOP = {"a", "an", "the", "on", "of", "in", "for", "to", "and", "or", "is",
            "are", "what", "how", "why", "when", "where", "which", "who",
            "with", "from", "by", "at", "as", "into", "via"}


def scholar_key(authors, year, title):
    last = authors[0][1] if authors else ""
    last = unicodedata.normalize("NFKD", last).encode("ascii", "ignore").decode()
    last = re.sub(r"[^a-z]", "", last.split()[0].lower()) if last.split() else ""
    words = [w for w in norm_title(title).split() if w not in KEY_STOP]
    return f"{last or 'anon'}{year or ''}{words[0] if words else ''}"


def venue_family(v):
    v = (v or "").lower()
    for fam, pat in (
            ("icml", r"\bicml\b|international conference on machine learning"),
            ("neurips", r"neurips|\bnips\b|neural information processing systems"),
            ("iclr", r"\biclr\b|international conference on learning representations"),
            ("aistats", r"\baistats\b|artificial intelligence and statistics"),
            ("usenix", r"usenix security|\buss\b"),
            ("tmlr", r"\btmlr\b|transactions on machine learning research"),
            ("colm", r"\bcolm\b|conference on language modeling"),
            ("acl", r"\b(acl|emnlp|naacl|eacl|aacl|coling|tacl|findings)\b|"
                    r"computational linguistics")):
        if re.search(pat, v):
            return fam
    return None


def scholar_venue(fam, year):
    """Scholar's wording for well-known venues -> (entry_type, fields)."""
    y = int(year) if year and str(year).isdigit() else None
    if fam == "icml":
        return "inproceedings", {"booktitle": "International conference on machine learning",
                                 "organization": "PMLR"}
    if fam == "neurips":
        return "article", {"journal": "Advances in neural information processing systems",
                           **({"volume": str(y - 1987)} if y else {})}
    if fam == "iclr":
        n = (y - 2012) if y else 0
        return "inproceedings", {"booktitle": (
            f"The {ORDINALS[n]} International Conference on Learning Representations"
            if 0 < n < len(ORDINALS) else "International Conference on Learning Representations")}
    if fam == "aistats":
        return "inproceedings", {"booktitle": "International Conference on Artificial "
                                              "Intelligence and Statistics",
                                 "organization": "PMLR"}
    if fam == "usenix":
        return "inproceedings", {"booktitle": (
            f"{nth(y - 1991)} USENIX security symposium (USENIX Security {str(y)[2:]})"
            if y else "USENIX security symposium")}
    if fam == "tmlr":
        return "article", {"journal": "Transactions on Machine Learning Research"}
    if fam == "colm":
        return "inproceedings", {"booktitle": "First Conference on Language Modeling"
                                 if y == 2024 else "Conference on Language Modeling"}
    return None, {}


def first(*vals):
    return next((v for v in vals if v), None)


def build(title, dblp, orv, cr, s2, ax, oa):
    """Merge source records into a Scholar-style entry description."""
    flags = []
    dblp_pub = next((d for d in dblp if not d["preprint"]), None)
    orv_pub = next((o for o in orv if not o["preprint"]), None)
    cr_pub = next((c for c in cr if not c["preprint"]), None)
    s2_venue = s2["venue"] if s2 and s2["venue"] and "arxiv" not in s2["venue"].lower() else ""

    # arXiv's journal-ref / comment ("Accepted at NeurIPS 2017") as a last resort
    ax_note = (ax or {}).get("note", "")
    ax_venue = ax_note if venue_family(ax_note) and not re.search(
        r"workshop|under review|submitted", ax_note, re.I) else ""
    venue = first((dblp_pub or {}).get("venue"), (orv_pub or {}).get("venue"),
                  (cr_pub or {}).get("container"), s2_venue, ax_venue) or ""
    fam = venue_family(venue) or venue_family((cr_pub or {}).get("container"))
    published = bool(dblp_pub or orv_pub or cr_pub or s2_venue or ax_venue)
    year = first((dblp_pub or {}).get("year"), (orv_pub or {}).get("year"),
                 (cr_pub or {}).get("year"), year_in(ax_venue) if not s2_venue else None)
    if not year:
        year = first((s2 or {}).get("year"), (ax or {}).get("year"))
        if s2_venue:
            flags.append(f"year {year} comes from Semantic Scholar and may be the arXiv year; "
                         f"check the {s2_venue} year")

    pmlr = from_pmlr(title, fam, year) if fam in PMLR_VOL else None
    nips = from_neurips(title, year) if fam == "neurips" else None
    if venue == ax_venue and ax_venue and not (pmlr or nips):
        flags.append(f"venue taken from the arXiv comment '{ax_note}'; confirm venue, year, "
                     f"and find the official link")

    # authors: prefer full names
    authors = []
    for r in (ax, pmlr, oa, cr_pub, dblp_pub, orv_pub, s2):
        if r and r.get("authors") and not abbreviated(r["authors"]):
            authors = r["authors"]
            break
    if not authors and s2 and s2["authors"]:
        authors = s2["authors"]
        flags.append("author first names are abbreviated (only Semantic Scholar had them)")

    # entry type and venue fields
    etype, fields = scholar_venue(fam, year)
    arxiv_id = first((ax or {}).get("id"), (s2 or {}).get("ext", {}).get("ArXiv"),
                     (oa or {}).get("arxiv"))
    if etype is None:
        if published and (cr_pub or dblp_pub):
            src = cr_pub or dblp_pub
            name = (cr_pub or {}).get("container") or venue
            if src.get("conf") or (dblp_pub or {}).get("conf"):
                etype, fields = "inproceedings", {"booktitle": name}
                if re.search(r"\bIEEE\b", (cr_pub or {}).get("publisher") or ""):
                    fields["organization"] = "IEEE"
            else:
                etype, fields = "article", {"journal": name}
                for k in ("volume", "number"):
                    if src.get(k):
                        fields[k] = src[k]
                if (cr_pub or {}).get("publisher"):
                    fields["publisher"] = cr_pub["publisher"]
        elif published:
            etype, fields = "inproceedings", {"booktitle": venue}
            flags.append(f"venue '{venue}' not confirmed by Crossref/DBLP; check the booktitle")
        elif arxiv_id:
            etype, fields = "article", {"journal": f"arXiv preprint arXiv:{arxiv_id}"}
            flags.append("only a preprint record was found: check whether a published "
                         "version exists; if so, update the venue, year, key and link")
        else:
            etype, fields = "misc", {}
            flags.append("no venue found: entry is @misc; fill the venue by hand")

    pages = first((pmlr or {}).get("pages"), (dblp_pub or {}).get("pages"),
                  (cr_pub or {}).get("pages"), (orv_pub or {}).get("pages"))
    journal = fields.get("journal", "")
    if pages and (etype == "inproceedings" or (journal and "arXiv" not in journal
                                               and fam != "neurips")):
        fields["pages"] = re.sub(r"\s*[-–]+\s*", "--", pages)

    # howpublished: DOI > official proceedings page > arXiv abs
    doi = first((cr_pub or {}).get("doi"), (dblp_pub or {}).get("doi"),
                (s2 or {}).get("ext", {}).get("DOI") if published else None)
    if doi and doi.lower().startswith("10.48550"):
        doi = None
    official = first((pmlr or {}).get("url"), (nips or {}).get("url"))
    if not official:
        for u in (dblp_pub or {}).get("urls", []) + (orv_pub or {}).get("urls", []):
            if "arxiv.org" in u:
                continue
            m = re.match(r"https?://(dx\.)?doi\.org/(.+)", u)
            if m:
                doi = doi or (None if m.group(2).startswith("10.48550") else m.group(2))
                continue
            official = re.sub(r"(aclanthology\.org/[^/]+)\.pdf$", r"\1/", u)
            break
    if not official and s2 and s2["ext"].get("ACL"):
        official = f"https://aclanthology.org/{s2['ext']['ACL']}/"
    if doi:
        url = f"https://doi.org/{doi}"
    elif official:
        url = official
    elif arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
        if published:
            flags.append(f"published at '{venue}' but only an arXiv link was found; "
                         f"find the DOI or official proceedings page")
    else:
        url = ""
        flags.append("no link found; fill howpublished by hand")

    if not authors:
        flags.append("no authors found")
    if not year:
        flags.append("no year found")
    best_title = first((dblp_pub or {}).get("title"), (orv_pub or {}).get("title"),
                       (cr_pub or {}).get("title"), (s2 or {}).get("title"),
                       (ax or {}).get("title"), (oa or {}).get("title")) or title
    return {"etype": etype, "title": best_title, "authors": authors, "year": year,
            "fields": fields, "url": url, "venue": venue if published else "arXiv",
            "flags": flags,
            "used": [r["src"] for r in (dblp_pub, orv_pub, cr_pub, s2, ax, oa, pmlr, nips) if r]}


def format_authors(authors):
    names = [f"{last}, {first}".strip(", ") for first, last in authors]
    if len(names) > 10:  # Scholar keeps 10 then "and others"
        names = names[:10] + ["others"]
    return " and ".join(names)


def render(e, key, comment):
    f = e["fields"]
    lines = [f"    title={{{tex_escape(e['title'])}}},",
             f"    author={{{format_authors(e['authors'])}}},"]
    for k in ("booktitle", "journal", "volume", "number", "pages"):
        if f.get(k):
            lines.append(f"    {k}={{{tex_escape(str(f[k]))}}},")
    if e["year"]:
        lines.append(f"    year={{{e['year']}}},")
    for k in ("organization", "publisher"):
        if f.get(k):
            lines.append(f"    {k}={{{tex_escape(f[k])}}},")
    lines.append(f'    howpublished = "\\url{{{e["url"]}}}",')
    lines.append(f"    comment = {{{comment}}}")
    return f"@{e['etype']}{{{key},\n" + "\n".join(lines) + "\n}"


def augment_scholar(bib, url, comment):
    """Re-indent Scholar's BibTeX to 4 spaces and append the two extra fields."""
    head, *body = bib.strip().splitlines()
    body = [b.strip() for b in body if b.strip()]
    if body and body[-1] == "}":
        body = body[:-1]
    if body and not body[-1].endswith(","):
        body[-1] += ","
    body = ["    " + b for b in body]
    body += [f'    howpublished = "\\url{{{url}}}",', f"    comment = {{{comment}}}"]
    return head + "\n" + "\n".join(body) + "\n}"


# -------------------------------------------------------------------------- driver

def existing(path):
    if not os.path.exists(path):
        return set(), set()
    txt = open(path, encoding="utf-8").read()
    titles = {norm_title(t) for t in re.findall(r"^\s*title\s*=\s*\{(.*)\},\s*$", txt, re.M)}
    keys = set(re.findall(r"^@\w+\{([^,]+),", txt, re.M))
    return titles, keys


def process(title, comment, use_scholar, used_keys):
    log(f"* {title}")
    sch = from_scholar(title) if use_scholar else None
    dblp, orv, cr = from_dblp(title), from_openreview(title), from_crossref(title)
    s2, ax = from_s2(title), from_arxiv(title)
    oa = None
    if not ax or not (dblp or orv or cr or s2):
        oa = from_openalex(title)
    if not (sch or dblp or orv or cr or s2 or ax or oa):
        return None, {"query": title, "status": "NOT FOUND",
                      "flags": ["no source matched this title: check the spelling, "
                                "or add the entry by hand"]}

    e = build(title, dblp, orv, cr, s2, ax, oa)
    if sch:
        key = re.match(r"@\w+\{([^,]+),", sch).group(1)
        e["used"].insert(0, "scholar")
    else:
        key = scholar_key(e["authors"], e["year"], e["title"])
    base, n = key, 0
    while key in used_keys:
        key = base + "abcdefghijklmnopqrstuvwxyz"[n]
        n += 1
    if sch and key != base:
        sch = sch.replace(base, key, 1)
    used_keys.add(key)

    flags = [] if sch else e["flags"]
    if sch and not e["url"]:
        flags.append("no link found; fill howpublished by hand")
    if not comment:
        flags.append("comment is empty: write a short note (3-8 words)")
    entry = augment_scholar(sch, e["url"], comment) if sch else render(e, key, comment)

    abstract = first((s2 or {}).get("abstract"), (ax or {}).get("abstract"),
                     next((o.get("abstract") for o in orv if o.get("abstract")), None)) or ""
    return entry, {
        "query": title, "key": key,
        "status": "OK" if not flags else "REVIEW",
        "matched_title": e["title"], "venue": e["venue"], "year": e["year"],
        "howpublished": e["url"], "sources": e["used"], "flags": flags,
        "abstract": abstract[:600],
    }


def read_inputs(args):
    items = [(t.strip(), "") for t in args.title or []]
    if args.papers:
        for line in open(args.papers, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            t, _, c = line.partition("||")
            t = re.sub(r"^\s*(\d+[.)]|[-*])\s+", "", t).strip()  # list bullets
            items.append((t, c.strip()))
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("papers", nargs="?", help="text file, one title per line")
    ap.add_argument("-t", "--title", action="append", help="a paper title (repeatable)")
    ap.add_argument("-o", "--out", required=True, help="output .bib (appended to)")
    ap.add_argument("--no-scholar", action="store_true", help="skip Google Scholar")
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between papers")
    args = ap.parse_args()

    items = read_inputs(args)
    if not items:
        ap.error("no titles given")

    have_titles, used_keys = existing(args.out)
    report_path = re.sub(r"\.bib$", "", args.out) + ".report.json"
    reports, new_entries = [], []
    for i, (title, comment) in enumerate(items):
        if norm_title(title) in have_titles:
            log(f"* {title}\n  already in {args.out}; skipped")
            reports.append({"query": title, "status": "SKIPPED (already in bib)", "flags": []})
            continue
        entry, rep = process(title, comment, not args.no_scholar, used_keys)
        reports.append(rep)
        if entry:
            new_entries.append(entry)
            have_titles.add(norm_title(title))
            log(f"  -> {rep['key']}  [{', '.join(rep['sources'])}]  {rep['howpublished']}")
        for f in rep["flags"]:
            log(f"  ! {f}")
        if i < len(items) - 1:
            time.sleep(args.sleep)

    if new_entries:
        sep = "\n" if os.path.exists(args.out) and os.path.getsize(args.out) > 0 else ""
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(sep + "\n\n".join(new_entries) + "\n")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, indent=2, ensure_ascii=False)

    review = [r for r in reports if r["status"] in ("REVIEW", "NOT FOUND")]
    log(f"\nwrote {len(new_entries)} new entr{'y' if len(new_entries) == 1 else 'ies'} "
        f"to {args.out}; report: {report_path}; {len(review)} need review")
    if DISABLED:
        log(f"sources unavailable this run: {', '.join(sorted(DISABLED))}")


if __name__ == "__main__":
    main()
