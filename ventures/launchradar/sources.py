"""Public, unauthenticated search endpoints.  Each returns normalized Thread dicts.
Both are best-effort: network failures return [] so the pipeline still runs on
whatever other sources succeeded (or on fixtures in tests)."""
from __future__ import annotations

import json
import time
from typing import Iterable

UA = "LaunchRadar/0.1 (indie social listening; contact: see product page)"


def _get_json(url: str, timeout: float = 15.0):
    import httpx

    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def hn_search(query: str, per_page: int = 20) -> list[dict]:
    """Algolia HN API: comments + stories from the last 30 days."""
    since = int(time.time()) - 30 * 86400
    url = (f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=(comment,story)"
           f"&numericFilters=created_at_i>{since}&hitsPerPage={per_page}")
    data = _get_json(url)
    if not data:
        return []
    out = []
    for h in data.get("hits", []):
        text = h.get("comment_text") or h.get("story_text") or h.get("title") or ""
        oid = h.get("objectID")
        out.append({
            "source": "hn", "id": f"hn:{oid}", "title": h.get("story_title") or h.get("title") or "",
            "text": _strip_html(text), "url": f"https://news.ycombinator.com/item?id={oid}",
            "author": h.get("author", ""), "created": h.get("created_at_i", 0), "score": h.get("points") or 0,
        })
    return out


def reddit_search(query: str, limit: int = 25, subreddits: Iterable[str] = ()) -> list[dict]:
    """Reddit's public JSON search (no OAuth needed at low volume; be polite: 1 req/2s)."""
    scope = "+".join(subreddits)
    base = f"https://www.reddit.com/r/{scope}/search.json?restrict_sr=1&" if scope else "https://www.reddit.com/search.json?"
    data = _get_json(f"{base}q={query}&sort=new&t=month&limit={limit}")
    if not data:
        return []
    out = []
    for c in data.get("data", {}).get("children", []):
        d = c.get("data", {})
        out.append({
            "source": "reddit", "id": f"reddit:{d.get('id')}", "title": d.get("title", ""),
            "text": d.get("selftext", "") or "", "url": "https://www.reddit.com" + d.get("permalink", ""),
            "author": d.get("author", ""), "created": int(d.get("created_utc", 0)), "score": d.get("score", 0),
            "subreddit": d.get("subreddit", ""),
        })
    return out


def from_fixture(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", s).replace("&#x27;", "'").replace("&quot;", '"').replace("&gt;", ">").replace("&lt;", "<")
