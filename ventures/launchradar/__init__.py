"""LaunchRadar - social listening for indie developers, with a human in the loop.

Story 3 from the article: an AI that finds people complaining about a problem
your product solves and replies with an "undetectable" plug.  That's astroturfing;
it breaks Reddit's and HN's rules, the FTC's endorsement guides, and it gets
accounts banned.  The *valuable* half is finding the conversations and drafting a
good reply fast.  LaunchRadar does that: it monitors HN and Reddit for threads
that match your product's pain points, scores them, drafts a reply that openly
says "I built this", and puts it in an approval queue.  A human posts it.
Nothing is ever posted automatically.
"""
from .pipeline import approve, scan

__all__ = ["scan", "approve"]
