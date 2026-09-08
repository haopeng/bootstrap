from __future__ import annotations

import re
from collections import Counter

NEG = ("rude", "slow", "cold", "dirty", "overpriced", "wait", "waited", "never again", "worst", "terrible",
       "awful", "disappoint", "refund", "wrong", "ignored", "horrible", "unprofessional")
POS = ("great", "amazing", "friendly", "delicious", "fast", "clean", "love", "best", "excellent", "recommend",
       "helpful", "perfect", "wonderful", "fantastic")
TOPICS = {
    "service": ("staff", "server", "waiter", "employee", "rude", "friendly", "helpful", "attitude"),
    "wait time": ("wait", "waited", "slow", "long", "minutes", "hour"),
    "quality": ("food", "cold", "delicious", "quality", "work", "repair", "haircut", "result"),
    "price": ("price", "expensive", "overpriced", "cheap", "value", "charged"),
    "cleanliness": ("dirty", "clean", "smell", "bathroom"),
}


def analyze(review: dict) -> dict:
    t = review["text"].lower()
    stars = review.get("rating", 3)
    neg = sum(w in t for w in NEG)
    pos = sum(w in t for w in POS)
    sentiment = "negative" if stars <= 2 or neg > pos + 1 else "positive" if stars >= 4 or pos > neg else "mixed"
    topics = [k for k, ws in TOPICS.items() if any(w in t for w in ws)]
    urgent = sentiment == "negative" and (stars <= 1 or any(w in t for w in ("refund", "sick", "injur", "lawyer", "health")))
    return {**review, "sentiment": sentiment, "topics": topics, "urgent": urgent}


def digest(reviews: list[dict]) -> dict:
    c = Counter(r["sentiment"] for r in reviews)
    topics = Counter(t for r in reviews if r["sentiment"] == "negative" for t in r["topics"])
    avg = round(sum(r.get("rating", 0) for r in reviews) / max(len(reviews), 1), 2)
    return {"count": len(reviews), "avg_rating": avg, "sentiment": dict(c), "top_complaints": topics.most_common(3)}


def template_reply(r: dict, business: str, owner: str, contact: str) -> str:
    first = (r.get("author") or "there").split()[0]
    if r["sentiment"] == "positive":
        topic = f" with the {r['topics'][0]}" if r["topics"] else ""
        return (f"Thank you, {first}! We're so glad you had a great experience{topic}. "
                f"We'll pass this along to the team — see you again soon.\n— {owner}, {business}")
    if r["sentiment"] == "negative":
        topic = f"the {r['topics'][0]}" if r["topics"] else "your visit"
        return (f"{first}, thank you for telling us — I'm sorry {topic} fell short of what you should expect from {business}. "
                f"I'd like to make it right; please reach me directly at {contact} so I can hear the details and fix this.\n— {owner}, Owner")
    return (f"Thanks for the honest feedback, {first}. We're glad some of it worked and we're taking the rest seriously. "
            f"If you're open to it, {contact} reaches me directly.\n— {owner}, {business}")


PRIVATE = re.compile(r"\b(patient|diagnos|treatment|appointment on|your (account|order) #?\d+)\b", re.I)
ARGUE = re.compile(r"\b(you('re| are) (wrong|lying)|not true|never happened|false review|fake)\b", re.I)


def safe(reply: str) -> bool:
    return not PRIVATE.search(reply) and not ARGUE.search(reply)
