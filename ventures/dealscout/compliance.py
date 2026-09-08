"""The consent + disclosure gate every automated contact must pass.

Rules encoded (US, 2026):
- TCPA: autodialed / prerecorded / AI-voice calls and texts to mobile numbers
  require prior express consent (written consent for marketing).  Manual dials
  by a human are outside this, so 'human_call' is always allowed after DNC check.
- National Do-Not-Call: scrub every number; keep an internal DNC list too.
- Quiet hours: no calls or texts before 8am or after 9pm in the *recipient's* zone
  (some states are stricter; we use 9am-8pm to be safe).
- AI disclosure: every AI-generated voice or text identifies itself as automated
  and names the human/company behind it.  Required in CA, UT, CO and under the
  FCC's 2024 ruling; good practice everywhere.
- Direct mail has none of these constraints, which is why it's the default channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

CHANNELS = ("mail", "human_call", "sms", "ai_voice")


@dataclass
class ConsentRecord:
    phone: str
    express_written_consent: bool = False   # e.g. owner replied "YES" to an opt-in or signed a form
    internal_dnc: bool = False
    national_dnc: Optional[bool] = None     # None = not yet scrubbed
    source: str = ""


@dataclass
class ConsentLedger:
    records: dict[str, ConsentRecord] = field(default_factory=dict)

    def get(self, phone: str) -> ConsentRecord:
        return self.records.setdefault(phone, ConsentRecord(phone=phone))

    def opt_out(self, phone: str) -> None:
        self.get(phone).internal_dnc = True

    def opt_in(self, phone: str, source: str) -> None:
        r = self.get(phone)
        r.express_written_consent = True
        r.source = source


def in_quiet_hours(local: datetime) -> bool:
    return local.hour < 9 or local.hour >= 20


def can_contact(channel: str, phone: Optional[str], ledger: ConsentLedger, local_now: datetime) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if channel not in CHANNELS:
        return False, f"unknown channel {channel}"
    if channel == "mail":
        return True, "direct mail: no consent requirement"
    if not phone:
        return False, "no phone number on file"
    rec = ledger.get(phone)
    if rec.internal_dnc:
        return False, "owner opted out (internal DNC)"
    if rec.national_dnc is None:
        return False, "number not yet scrubbed against National DNC registry"
    if rec.national_dnc:
        return False, "number is on the National Do-Not-Call registry"
    if in_quiet_hours(local_now):
        return False, "outside 9am-8pm recipient local time"
    if channel in ("sms", "ai_voice") and not rec.express_written_consent:
        return False, f"{channel} requires prior express written consent (TCPA)"
    return True, "ok"


AI_DISCLOSURE = ("Hi, this is an automated assistant calling on behalf of {company}. "
                 "I'm an AI, not a person, and this call may be recorded. "
                 "You can say 'stop' at any time and we won't contact you again.")
