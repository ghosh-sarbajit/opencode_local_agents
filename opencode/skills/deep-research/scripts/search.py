#!/usr/bin/env python3
"""Web search for agents. Prints results as numbered title / url / snippet.

Backend is picked from the environment: SEARXNG_URL, BRAVE_API_KEY,
TAVILY_API_KEY. With none set it exits with code 2.

usage: search.py "query" [-n 8] [--json]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) research-skill/1.0"


def _get(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def searxng(q, n):
    base = os.environ["SEARXNG_URL"].rstrip("/")
    d = json.loads(_get(f"{base}/search?" + urllib.parse.urlencode({"q": q, "format": "json"})))
    return [(r.get("title", ""), r.get("url", ""), r.get("content", "")) for r in d.get("results", [])[:n]]


def brave(q, n):
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "count": n})
    d = json.loads(_get(url, {"Accept": "application/json", "X-Subscription-Token": os.environ["BRAVE_API_KEY"]}))
    return [(r.get("title", ""), r.get("url", ""), r.get("description", "")) for r in d.get("web", {}).get("results", [])[:n]]


def tavily(q, n):
    body = json.dumps({"api_key": os.environ["TAVILY_API_KEY"], "query": q, "max_results": n}).encode()
    d = json.loads(_get("https://api.tavily.com/search", {"Content-Type": "application/json"}, body))
    return [(r.get("title", ""), r.get("url", ""), r.get("content", "")) for r in d.get("results", [])[:n]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if os.environ.get("SEARXNG_URL"):
        fn = searxng
    elif os.environ.get("BRAVE_API_KEY"):
        fn = brave
    elif os.environ.get("TAVILY_API_KEY"):
        fn = tavily
    else:
        print("no search backend: set SEARXNG_URL, BRAVE_API_KEY or TAVILY_API_KEY "
              "(or use opencode's built-in websearch tool)", file=sys.stderr)
        sys.exit(2)
    try:
        results = fn(a.query, a.n)
    except Exception as e:
        print(f"search failed ({fn.__name__}): {e}", file=sys.stderr)
        sys.exit(1)

    if a.json:
        print(json.dumps([{"title": t, "url": u, "snippet": s} for t, u, s in results], indent=1))
        return
    if not results:
        print("No results.")
    for i, (t, u, s) in enumerate(results, 1):
        print(f"[{i}] {t}\n    {u}\n    {s[:300]}\n")


if __name__ == "__main__":
    main()
