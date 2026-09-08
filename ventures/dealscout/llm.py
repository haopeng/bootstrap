"""Claude layer: classify owner replies and write the buyer-facing deal memo."""
from __future__ import annotations

from ventures.core import get_llm

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["interested", "not_now", "not_interested", "stop", "wrong_person", "question"]},
        "asking_price": {"type": ["number", "null"]},
        "timeline": {"type": "string"},
        "next_step": {"type": "string"},
    },
    "required": ["intent", "asking_price", "timeline", "next_step"], "additionalProperties": False,
}

STOP_WORDS = ("stop", "remove", "unsubscribe", "don't contact", "do not contact", "leave me alone")
YES_WORDS = ("yes", "interested", "how much", "what would you offer", "make an offer", "call me")


def classify_reply(text: str) -> dict:
    t = text.lower()
    if any(w in t for w in STOP_WORDS):
        rules = {"intent": "stop", "asking_price": None, "timeline": "", "next_step": "Add to internal DNC; no further contact."}
    elif any(w in t for w in YES_WORDS):
        rules = {"intent": "interested", "asking_price": None, "timeline": "", "next_step": "Human calls within 1 business hour; pull comps."}
    elif "wrong" in t or "not the owner" in t:
        rules = {"intent": "wrong_person", "asking_price": None, "timeline": "", "next_step": "Mark bad contact; re-skip-trace."}
    else:
        rules = {"intent": "question", "asking_price": None, "timeline": "", "next_step": "Human reviews and replies."}
    llm = get_llm()
    if not llm.available:
        return rules
    out = llm.json(REPLY_SCHEMA, "Classify this property-owner reply to a cash-offer letter:\n\n" + text, effort="low")
    if out and out["intent"] == "stop" or rules["intent"] == "stop":
        return {**(out or rules), "intent": "stop"}  # never let the model un-stop
    return out or rules


MEMO_SCHEMA = {
    "type": "object",
    "properties": {"memo": {"type": "string"}, "risks": {"type": "array", "items": {"type": "string"}}},
    "required": ["memo", "risks"], "additionalProperties": False,
}


def deal_memo(lead: dict, math: dict) -> dict:
    fallback = {
        "memo": (f"{lead['address']}, {lead['city']} {lead['state']}. Signals: {', '.join(lead['signals'])}. "
                 f"Assessed ${lead['assessed_value']:,.0f}; ARV est. ${math['arv_estimate']:,.0f}; "
                 f"max offer ${math['max_offer']:,.0f}; investor price ${math['investor_price']:,.0f} "
                 f"(est. gross margin ${math['investor_gross_margin']:,.0f} after ${math['repairs_estimate']:,.0f} repairs)."),
        "risks": ["ARV is a placeholder until comps are pulled", "Title search needed for liens beyond public record",
                  "Repair estimate assumes average condition; walk the property"],
    }
    llm = get_llm()
    if not llm.available:
        return fallback
    return llm.json(MEMO_SCHEMA, "Write a 120-word investor deal memo and list 3-5 risks from this data:\n"
                    + str({**lead, **math}), effort="low") or fallback
