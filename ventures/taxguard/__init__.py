"""TaxGuard - contract & vendor-compliance review for small businesses.

Story 1 from the article: upload a pack of PDFs (contracts, vendor invoices),
get back flagged clauses, 1099-reporting exposure and a filing checklist.
Sold per document ($49) or per month ($199).

Not legal or tax advice: the deliverable says so and points to a CPA for filing.
"""
from .pipeline import review

__all__ = ["review"]
