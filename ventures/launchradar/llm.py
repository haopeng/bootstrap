"""Claude layer: sharper selling points, a relevance second opinion, and the reply draft.
The draft template enforces disclosure whether or not the model is available."""
from __future__ import annotations

from ventures.core import get_llm

POINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string"},
        "pain_points": {"type": "array", "items": {"type": "string"}, "description": "problems users have, in their words"},
        "search_queries": {"type": "array", "items": {"type": "string"}, "description": "6-10 short queries people would type when they have the problem"},
    },
    "required": ["one_liner", "pain_points", "search_queries"], "additionalProperties": False,
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "why": {"type": "string"},
        "reply": {"type": "string", "description": "Helpful first, mention product once, includes 'I built'/'I work on' disclosure, no hype, <=120 words"},
    },
    "required": ["relevant", "why", "reply"], "additionalProperties": False,
}

SYSTEM = """You help an indie developer take part in online discussions honestly.
Rules: answer the person's actual question first; mention the product at most once and only if it
genuinely fits; always disclose the relationship ('I built X' / 'disclosure: I work on X');
never invent features; never disparage competitors; match the forum's tone (HN: terse, technical)."""


def selling_points(name: str, description: str, kws: list[str]) -> dict:
    fallback = {"one_liner": description.strip().split(".")[0][:120],
                "pain_points": kws[:5], "search_queries": kws[:8]}
    llm = get_llm()
    if not llm.available:
        return fallback
    return llm.json(POINTS_SCHEMA, f"Product: {name}\n\n{description}", system=SYSTEM, effort="low") or fallback


def draft_reply(product: str, one_liner: str, thread: dict) -> dict:
    disclosure = f"(Disclosure: I built {product}.)"
    fallback_reply = (
        f"A few things that helped me with this: write down the exact steps you repeat each week, then automate the "
        f"one that hurts most first. {disclosure} It does {one_liner[:1].lower() + one_liner[1:].rstrip('.')} — happy to answer questions, "
        f"and no worries if it's not a fit."
    )
    llm = get_llm()
    if not llm.available:
        return {"relevant": True, "why": "keyword + need-signal match", "reply": fallback_reply}
    prompt = (f"Product: {product} — {one_liner}\n\nThread on {thread['source']}: {thread.get('title')}\n"
              f"<post>\n{thread.get('text', '')[:4000]}\n</post>\n\nIs this a genuinely good place to reply? Draft the reply.")
    out = llm.json(REPLY_SCHEMA, prompt, system=SYSTEM, effort="medium")
    if not out:
        return {"relevant": True, "why": "model unavailable; rules match", "reply": fallback_reply}
    if product.lower() in out["reply"].lower() and "built" not in out["reply"].lower() and "work on" not in out["reply"].lower():
        out["reply"] = out["reply"].rstrip() + f"\n\n{disclosure}"  # belt and braces
    return out
