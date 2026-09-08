"""DealScout - distressed-property lead engine for real-estate wholesalers.

Story 2 from the article, minus the part that gets you sued.  The original
bot cold-called owners with an AI voice they could not tell was AI.  In the US
that is an artificial-voice call under the TCPA (FCC ruling, Feb 2024): it
needs prior express consent, DNC scrubbing, and several states now require AI
disclosure.  So DealScout does the valuable part - finding and ranking leads
from public county records and producing owner-ready outreach and buyer-ready
deal reports - and gates every automated contact behind consent + DNC checks,
with an AI disclosure baked into every script.
"""
from .pipeline import run

__all__ = ["run"]
