"""ReviewReply - drafted responses to Google / Yelp reviews for local businesses.

New idea, same pattern as story 3 (find the conversation, draft the reply,
human posts).  Owners of restaurants, clinics, salons and auto shops know that
answering every review lifts ratings and local-search rank but never find the
time.  $19/month per location.  Every reply is drafted, never auto-posted, and
never argues with the customer or discloses private details (HIPAA matters for
clinics: the reply template never confirms someone was a patient).
"""
from .pipeline import run

__all__ = ["run"]
