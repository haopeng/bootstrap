"""Dunning - polite, automatic invoice follow-up for small businesses.

Story 4 from the article ("AI debt collector").  Third-party debt collection in
the US is regulated by the FDCPA / Regulation F (call-frequency caps, validation
notices, licensing in many states) and is a bad fit for a solo product.  What is
both legal and lucrative is *first-party* accounts-receivable follow-up: a
business reminding its own customers about its own invoices.  Dunning runs a
4-step sequence, in the customer's business hours, stops the moment a customer
disputes or asks it to, never threatens, and only mentions late fees that the
contract actually allows.  It reads open invoices and payment history straight
from QuickBooks, tunes tone and cadence to each customer's record, places a
disclosed AI call on the firm/final steps, and turns "we'll pay next week" into
a dated promise.  No monthly fee: 10% of attributed recoveries.
"""
from .pipeline import run_day, handle_reply

__all__ = ["run_day", "handle_reply"]
