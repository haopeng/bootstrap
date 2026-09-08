"""Dunning - polite, automatic invoice follow-up for small businesses.

Story 4 from the article ("AI debt collector").  Third-party debt collection in
the US is regulated by the FDCPA / Regulation F (call-frequency caps, validation
notices, licensing in many states) and is a bad fit for a solo product.  What is
both legal and lucrative is *first-party* accounts-receivable follow-up: a
business reminding its own customers about its own invoices.  Dunning runs a
4-step sequence, in the customer's business hours, stops the moment a customer
disputes or asks it to, never threatens, and only mentions late fees that the
contract actually allows.  Priced at $39/mo or 2% of what it recovers.
"""
from .pipeline import run_day, handle_reply

__all__ = ["run_day", "handle_reply"]
