"""Pricing and a Stripe-ready checkout stub.

Every product charges either per-deliverable or per-month.  The numbers here are
the launch prices; margins are checked in tests against the LLM cost estimate so
a price change can never make a product unprofitable by accident.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    product: str
    name: str
    price_usd: float
    unit: str           # "per review", "per month", "per closed deal", ...
    included: str
    est_llm_cost_usd: float  # expected model spend per unit at list price


PRICING: dict[str, list[Plan]] = {
    "taxguard": [
        Plan("taxguard", "Single review", 49, "per document", "1 contract or invoice pack, findings + filing checklist", 0.60),
        Plan("taxguard", "Bookkeeper", 199, "per month", "40 documents / month, 1099 tracker, priority queue", 20.0),
    ],
    "dealscout": [
        Plan("dealscout", "Leads", 149, "per month", "1 county, daily scan, owner letters, buyer reports", 6.0),
        Plan("dealscout", "Success fee", 2500, "per closed deal", "assignment-fee share, invoiced on close", 0.0),
    ],
    "launchradar": [
        Plan("launchradar", "Indie", 29, "per month", "3 products, daily digest, 100 drafted replies", 4.0),
        Plan("launchradar", "Studio", 99, "per month", "15 products, hourly scan, Slack/Discord digest", 15.0),
    ],
    "dunning": [
        Plan("dunning", "Recovered", 0, "10% of recovered", "no monthly fee; QuickBooks sync, email + disclosed AI calls, billed only on attributed recoveries", 3.0),
        Plan("dunning", "Flat", 39, "per month", "same product for businesses that prefer a fixed fee; up to 100 open invoices", 3.0),
    ],
    "reviewreply": [
        Plan("reviewreply", "Local", 19, "per month", "1 location, unlimited drafted replies, weekly sentiment digest", 1.5),
    ],
    "bidscout": [
        Plan("bidscout", "Contractor", 79, "per month", "daily matched bids, go/no-go summaries, deadline calendar", 6.0),
    ],
    "leasecheck": [
        Plan("leasecheck", "Single lease", 19, "per lease", "plain-English red flags, negotiation letter", 0.40),
    ],
}


def quote(product: str) -> list[Plan]:
    return PRICING[product]


def checkout_url(plan: Plan, customer_email: str = "") -> str:
    """Return a Stripe Checkout link.

    Real integration = one `stripe.checkout.Session.create(...)` call with a
    Price ID per plan.  Until STRIPE_SECRET_KEY is set we return a deterministic
    placeholder so the UI and tests can link somewhere.
    """
    if os.environ.get("STRIPE_SECRET_KEY"):
        try:
            import stripe  # type: ignore

            stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
            session = stripe.checkout.Session.create(
                mode="subscription" if plan.unit == "per month" else "payment",
                customer_email=customer_email or None,
                line_items=[{"price_data": {
                    "currency": "usd",
                    "unit_amount": int(plan.price_usd * 100),
                    "product_data": {"name": f"{plan.product}: {plan.name}"},
                    **({"recurring": {"interval": "month"}} if plan.unit == "per month" else {}),
                }, "quantity": 1}],
                success_url=os.environ.get("VENTURES_URL", "http://localhost:8000") + "/thanks",
                cancel_url=os.environ.get("VENTURES_URL", "http://localhost:8000") + f"/{plan.product}",
            )
            return session.url
        except Exception:  # pragma: no cover - network / missing lib
            pass
    slug = plan.name.lower().replace(" ", "-")
    return f"/checkout/{plan.product}/{slug}"
