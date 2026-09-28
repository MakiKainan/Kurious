"""Baseline backend: REST search, then sequential summary + pageviews per candidate. Stdlib only."""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from functools import lru_cache

from wiki_common import USER_AGENT, add_flags

SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/page"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
VIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
API = "https://en.wikipedia.org/w/api.php"


@lru_cache(maxsize=None)
def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def _try(url):
    try:
        return _fetch(url)
    except Exception:
        return None


def _categories(pageids):
    qs = urllib.parse.urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "pageids": "|".join(map(str, pageids)), "prop": "categories|info",
        "clshow": "!hidden", "cllimit": "max",
    })
    pages = (_try(f"{API}?{qs}") or {}).get("query", {}).get("pages", [])
    return {p["pageid"]: ([c["title"] for c in p.get("categories", [])], p.get("length", 0)) for p in pages}


def candidates(words):
    """Returns (candidates, stats). Same shape as wiki.WikiClient.candidates."""
    before = _fetch.cache_info()
    query = " ".join(words)
    qs = urllib.parse.urlencode({"q": query, "limit": 20})
    pages = (_try(f"{SEARCH}?{qs}") or {}).get("pages", [])

    end = date.today() - timedelta(days=1)
    span = f"daily/{(end - timedelta(days=59)):%Y%m%d}/{end:%Y%m%d}"  # 60 days, same window as wiki.py
    results, disambig = [], {}
    for i, p in enumerate(pages):
        key = urllib.parse.quote(p["key"], safe="")
        s = _try(SUMMARY + key) or {}
        v = _try(f"{VIEWS}{key}/{span}") or {}
        disambig[p["id"]] = s.get("type") == "disambiguation"
        results.append({
            "pageid": p["id"], "title": p["title"],
            "extract": s.get("extract", ""),
            "description": p.get("description") or "",
            "thumbnail": (s.get("thumbnail") or {}).get("source"),
            "views": sum(x["views"] for x in v.get("items", [])),
            "categories": [], "rank": i, "matched_by": [query],
        })

    cats = _categories([c["pageid"] for c in results]) if results else {}
    for c in results:
        c["categories"], c["length"] = cats.get(c["pageid"], ([], 0))
        add_flags(c, disambig[c["pageid"]])

    after = _fetch.cache_info()
    stats = {"requests": after.misses - before.misses, "cached": after.hits - before.hits, "stale": False}
    return results, stats
