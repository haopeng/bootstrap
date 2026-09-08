"""Keyword extraction from a product description and relevance scoring of threads."""
from __future__ import annotations

import re
import time
from collections import Counter

STOP = set("""a an the and or of to in for on with is are be by as at it this that from your you we our
i my me they them their its into over under about can will just not no yes do does how what which who
tool tools app apps software service product products use using used make makes made get gets like""".split())

# Phrases that signal an unmet need rather than a general discussion.
NEED_SIGNALS = [
    r"is there (a|any) (tool|app|way|service)", r"why (is there no|isn't there|doesn't)", r"looking for (a|an|some)",
    r"recommend(ation)?s?\b", r"alternative(s)? to", r"frustrat", r"anyone know", r"how do (you|i) (handle|deal|manage)",
    r"wish (there was|i could)", r"tired of", r"struggl", r"pain(ful)?\b", r"manual(ly)?", r"spreadsheet",
]


def keywords(description: str, n: int = 12) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9\-]{2,}", description.lower())
    uni = Counter(w for w in words if w not in STOP)
    bi = Counter(f"{a} {b}" for a, b in zip(words, words[1:]) if a not in STOP and b not in STOP)
    picked = [w for w, c in bi.most_common(n // 2) if c >= 2 or uni[w.split()[0]] >= 2] + [w for w, _ in uni.most_common(n)]
    seen, out = set(), []
    for k in picked:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out[:n]


def score_thread(thread: dict, kws: list[str], now: float | None = None) -> dict:
    now = now or time.time()
    body = f"{thread.get('title', '')} {thread.get('text', '')}".lower()
    hits = [k for k in kws if k in body]
    kw_score = min(len(hits) / max(3, len(kws) / 3), 1.0)
    need = sum(1 for p in NEED_SIGNALS if re.search(p, body))
    need_score = min(need / 2, 1.0)
    age_days = max((now - thread.get("created", now)) / 86400, 0)
    recency = 1.0 if age_days <= 2 else 0.8 if age_days <= 7 else 0.5 if age_days <= 30 else 0.2
    engagement = min((thread.get("score") or 0) / 20, 1.0)
    total = 100 * (0.45 * kw_score + 0.35 * need_score + 0.15 * recency + 0.05 * engagement)
    return {**thread, "matched_keywords": hits, "need_signals": need, "age_days": round(age_days, 1),
            "relevance": round(total, 1)}


def rank(threads: list[dict], kws: list[str], min_relevance: float = 35.0, now: float | None = None) -> list[dict]:
    scored = [score_thread(t, kws, now) for t in threads]
    return sorted((t for t in scored if t["relevance"] >= min_relevance), key=lambda t: -t["relevance"])
