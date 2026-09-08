"""BidScout - government bid finder + go/no-go memo for small contractors.

New idea, same pattern as story 2 (public records nobody has time to read).
Federal opportunities are on SAM.gov (free API key), states and cities on their
own portals.  Small contractors (landscaping, IT, janitorial, construction) miss
most set-aside bids because nobody reads the feeds.  BidScout matches feeds to a
contractor profile (NAICS codes, keywords, states, set-asides), writes a one-page
go/no-go memo and emits an .ics deadline calendar.  $79/month.
"""
from .pipeline import run

__all__ = ["run"]
