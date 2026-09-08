from __future__ import annotations

import time

from ventures.core import Store, render_markdown

from . import engine, llm, sources


def scan(product: str, description: str, threads: list[dict] | None = None, live: bool = False,
         subreddits: tuple[str, ...] = (), store: Store | None = None, now: float | None = None,
         max_drafts: int = 10) -> dict:
    """product -> keywords -> threads (live or supplied) -> ranked -> drafted replies in an approval queue."""
    store = store or Store()
    now = now or time.time()
    jid = store.new_job("launchradar", "scan", {"product": product})
    kws = engine.keywords(description)
    points = llm.selling_points(product, description, kws)
    all_kws = list(dict.fromkeys(kws + [q.lower() for q in points["search_queries"]]))

    if threads is None:
        threads = []
        if live:
            for q in points["search_queries"][:5]:
                threads += sources.hn_search(q)
                threads += sources.reddit_search(q, subreddits=subreddits)
                time.sleep(2)  # politeness
    dedup = {t["id"]: t for t in threads}
    ranked = engine.rank(list(dedup.values()), all_kws, now=now)

    queue = []
    for t in ranked[:max_drafts]:
        d = llm.draft_reply(product, points["one_liner"], t)
        if not d["relevant"]:
            continue
        item = {"thread_id": t["id"], "url": t["url"], "title": t["title"], "source": t["source"],
                "relevance": t["relevance"], "why": d["why"], "reply": d["reply"], "status": "needs_approval"}
        queue.append(item)
        store.log(jid, "draft", item)

    findings = [{"severity": "high" if q["relevance"] >= 70 else "medium" if q["relevance"] >= 50 else "low",
                 "title": f"[{q['source']}] {q['title'][:80]} (relevance {q['relevance']})",
                 "detail": q["why"], "action": f"Review & post by hand: {q['url']}", "evidence": q["reply"][:200]}
                for q in queue]
    report = render_markdown(
        f"LaunchRadar digest — {product}",
        f"{len(dedup)} threads scanned, {len(ranked)} relevant, {len(queue)} replies drafted and waiting for your approval. "
        f"Keywords: {', '.join(all_kws[:10])}.",
        findings, {"Reply drafts (copy, edit, post yourself)": [f"**{q['url']}**\n\n  {q['reply']}" for q in queue]},
        "LaunchRadar never posts on your behalf. Every draft discloses that you built the product.",
    )
    result = {"job_id": jid, "keywords": all_kws, "selling_points": points, "ranked": ranked, "queue": queue, "report_md": report}
    store.finish(jid, {"keywords": all_kws, "queue": queue})
    return result


def approve(store: Store, job_id: str, thread_id: str, edited_reply: str | None = None) -> dict:
    """Human approval: mark a draft approved (and optionally edited).  Posting is still manual."""
    job = store.get(job_id)
    for q in job["result"]["queue"]:
        if q["thread_id"] == thread_id:
            q["status"] = "approved"
            if edited_reply:
                q["reply"] = edited_reply
            store.finish(job_id, job["result"])
            store.log(job_id, "approved", q)
            return q
    raise KeyError(thread_id)
