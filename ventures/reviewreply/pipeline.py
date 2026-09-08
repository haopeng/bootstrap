from __future__ import annotations

from ventures.core import Store, get_llm, render_markdown

from . import engine

SCHEMA = {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"], "additionalProperties": False}
SYSTEM = """You draft public replies to online reviews for a small local business owner.
Rules: thank, acknowledge the specific point, never argue or call the reviewer wrong, never reveal
private details (never confirm someone is a patient/client), move unresolved issues offline with the
contact given, 40-80 words, sign with the owner's first name."""


def run(reviews: list[dict], business: str, owner: str, contact: str, store: Store | None = None) -> dict:
    store = store or Store()
    jid = store.new_job("reviewreply", "batch", {"business": business, "n": len(reviews)})
    llm = get_llm()
    drafts = []
    for raw in reviews:
        r = engine.analyze(raw)
        reply = engine.template_reply(r, business, owner, contact)
        if llm.available:
            out = llm.json(SCHEMA, f"Business: {business}. Owner: {owner}. Contact: {contact}.\n"
                           f"Review ({r.get('rating')}/5 by {r.get('author')}): {r['text']}", system=SYSTEM, effort="low")
            if out and engine.safe(out["reply"]):
                reply = out["reply"]
        assert engine.safe(reply)
        drafts.append({**r, "reply": reply, "status": "needs_approval"})
        store.log(jid, "draft", {"review_id": r.get("id"), "sentiment": r["sentiment"], "urgent": r["urgent"]})
    d = engine.digest(drafts)
    findings = [{"severity": "high" if x["urgent"] else "medium" if x["sentiment"] == "negative" else "info",
                 "title": f"{x.get('rating')}★ by {x.get('author')} — {x['sentiment']}" + (" (URGENT)" if x["urgent"] else ""),
                 "detail": x["text"][:160], "action": "Draft reply:\n\n    " + x["reply"].replace("\n", "\n    ")}
                for x in drafts]
    report = render_markdown(
        f"ReviewReply — {business}",
        f"{d['count']} new reviews, avg {d['avg_rating']}★. Sentiment: {d['sentiment']}. "
        f"Top complaints: {', '.join(f'{t} ({n})' for t, n in d['top_complaints']) or 'none'}.",
        findings, {}, "Replies are drafts for you to post. Nothing is posted automatically.")
    store.finish(jid, {"digest": d, "drafts": drafts})
    return {"job_id": jid, "digest": d, "drafts": drafts, "report_md": report}
