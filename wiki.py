"""Optimized backend: one Action API call per query, kept-alive session, sqlite cache, parallel per-word search."""
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from wiki_common import USER_AGENT, add_flags, merge

API = "https://en.wikipedia.org/w/api.php"
TTL = 24 * 3600


class WikiClient:
    def __init__(self, db_path="cache.db"):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503])
        self.session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
        self.pool = ThreadPoolExecutor(4)
        self.mem = {}
        self.lock = threading.Lock()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, ts REAL, v TEXT)")

    def _get(self, params):
        """Returns (data, source) with source in mem | db | net | stale."""
        key = json.dumps(params, sort_keys=True)
        if key in self.mem:
            return self.mem[key], "mem"
        with self.lock:
            row = self.db.execute("SELECT ts, v FROM cache WHERE k=?", (key,)).fetchone()
        if row and time.time() - row[0] < TTL:
            self.mem[key] = json.loads(row[1])
            return self.mem[key], "db"
        try:
            r = self.session.get(API, params=params, timeout=5)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            if row:  # offline fallback: serve expired cache
                return json.loads(row[1]), "stale"
            raise
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, time.time(), json.dumps(data)))
            self.db.commit()
        self.mem[key] = data
        return data, "net"

    def _search(self, q):
        params = {
            "action": "query", "format": "json", "formatversion": "2",
            "generator": "search", "gsrsearch": q, "gsrlimit": 20,
            "prop": "extracts|pageimages|pageviews|description|categories|pageprops|info",
            "exintro": 1, "explaintext": 1, "exlimit": "max",
            "piprop": "thumbnail", "pithumbsize": 400,
            "clshow": "!hidden", "cllimit": "max", "ppprop": "disambiguation",
        }
        # pageviews/categories are paginated (pvipcontinue etc.); gsroffset means "more results", so don't follow it
        pages, sources, extra = {}, [], {}
        for _ in range(3):
            try:
                data, src = self._get({**params, **extra})
            except requests.RequestException:
                sources.append("error")
                break
            sources.append(src)
            for p in data.get("query", {}).get("pages", []):
                m = pages.setdefault(p["pageid"], {})
                for k, v in p.items():
                    if isinstance(v, list):
                        m.setdefault(k, []).extend(v)
                    elif isinstance(v, dict):
                        m.setdefault(k, {}).update(v)
                    else:
                        m[k] = v
            extra = data.get("continue", {})
            if not extra or "gsroffset" in extra:
                break
        out = []
        for p in pages.values():
            c = {
                "pageid": p["pageid"], "title": p["title"],
                "extract": p.get("extract", ""), "description": p.get("description", ""),
                "thumbnail": (p.get("thumbnail") or {}).get("source"),
                "views": sum(v or 0 for v in (p.get("pageviews") or {}).values()),
                "length": p.get("length", 0),
                "categories": [x["title"] for x in p.get("categories", [])],
                "rank": p.get("index", 99), "matched_by": [q],
            }
            out.append(add_flags(c, "disambiguation" in (p.get("pageprops") or {})))
        return out, sources

    def candidates(self, words):
        """Returns (candidates, stats). Same shape as wiki_lazy.candidates."""
        queries = list(dict.fromkeys([" ".join(words), *words]))
        found = list(self.pool.map(self._search, queries))
        sources = [s for _, srcs in found for s in srcs]
        stats = {
            "requests": sources.count("net"),
            "cached": sum(s in ("mem", "db") for s in sources),
            "stale": "stale" in sources or "error" in sources,
        }
        return merge([c for c, _ in found]), stats


@cache
def _client():
    return WikiClient()


def candidates(words):
    return _client().candidates(words)
