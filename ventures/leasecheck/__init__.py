"""LeaseCheck - plain-English residential lease review for tenants.

New idea, consumer twin of story 1.  Same engine shape (rules + Claude), a
different buyer: renters who get a 20-page lease and 48 hours to sign.  $19 per
lease, sold through renter communities and moving-checklist sites.  Output is a
red-flag list, state-specific notes, and a polite negotiation email.
"""
from .pipeline import review

__all__ = ["review"]
