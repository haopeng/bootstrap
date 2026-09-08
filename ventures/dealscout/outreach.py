"""Owner-facing messages.  Mail letter is always produced; SMS / voice scripts are
produced but only *sent* through `send()` if the compliance gate passes."""
from __future__ import annotations

from datetime import datetime

from ventures.core import get_llm

from .compliance import AI_DISCLOSURE, ConsentLedger, can_contact

LETTER = """{date}

{owner}
{mailing}

Dear {owner_first},

I'm a local buyer in {city}. I noticed the property at {address} may have become a burden
{reason_line} and wanted to reach out directly rather than through an agent.

I buy houses as-is, pay closing costs, and can close on your timeline, whether that's two weeks or
three months. There's no obligation and no fee to talk. If you'd like a written cash offer, call or
text me at {phone} or reply to this letter.

If you'd prefer not to hear from me again, just let me know and I'll remove you from my list.

Sincerely,
{sender}
{company}
{phone}
"""

REASON = {
    "probate": "after a loss in the family",
    "pre_foreclosure": "with the lender situation",
    "tax_lien": "with the property-tax balance",
    "code_violation": "with the city's repair notices",
    "vacant": "sitting empty",
    "divorce": "with recent changes at home",
}

SMS = ("{sender} with {company} here — this is an automated text. I buy houses as-is in {city} and "
       "may be interested in {address}. Open to a no-obligation cash offer? Reply YES to talk or STOP to opt out.")

VOICE_SCRIPT = AI_DISCLOSURE + (" I'm reaching out about the property at {address}. {company} buys homes as-is "
                                "for cash and can close on your schedule. Would you be open to hearing an offer? "
                                "You can answer yes, no, or ask me to have {sender} call you personally.")

LETTER_SCHEMA = {
    "type": "object",
    "properties": {"letter": {"type": "string"}},
    "required": ["letter"], "additionalProperties": False,
}


def _greeting(owner: str) -> str:
    if not owner:
        return "Neighbor"
    if "estate" in owner.lower():
        surname = owner.replace("Estate of", "").replace("Estate", "").strip().split()[-1]
        return f"{surname} family"
    if "&" in owner or " and " in owner.lower():
        return owner.replace("&", "and")
    return owner.split()[0]


def draft(lead: dict, sender: str, company: str, phone: str, today: datetime | None = None) -> dict:
    today = today or datetime.now()
    ctx = dict(
        date=today.strftime("%B %d, %Y"), owner=lead["owner"], owner_first=_greeting(lead["owner"]),
        mailing=lead["owner_mailing"], city=lead["city"], address=lead["address"],
        reason_line=REASON.get(lead["signals"][0], ""), phone=phone, sender=sender, company=company,
    )
    letter = LETTER.format(**ctx)
    llm = get_llm()
    if llm.available:
        better = llm.json(LETTER_SCHEMA,
                          "Rewrite this owner letter to sound warm and specific, keep it under 180 words, keep every "
                          "factual detail and the opt-out sentence, do not add promises:\n\n" + letter, effort="low")
        if better and better.get("letter"):
            letter = better["letter"]
    return {"letter": letter, "sms": SMS.format(**ctx), "voice_script": VOICE_SCRIPT.format(**ctx)}


def send(channel: str, lead: dict, packet: dict, ledger: ConsentLedger, local_now: datetime, log) -> dict:
    """Route a message.  Actual transports are stubs: mail -> Lob/PostGrid API,
    sms -> Twilio Messages, ai_voice -> Twilio Voice + ElevenLabs stream."""
    ok, reason = can_contact(channel, lead.get("phone"), ledger, local_now)
    entry = {"channel": channel, "address": lead["address"], "allowed": ok, "reason": reason}
    if ok:
        entry["body"] = {"mail": packet["letter"], "sms": packet["sms"], "ai_voice": packet["voice_script"],
                         "human_call": packet["voice_script"]}[channel]
        entry["transport"] = {"mail": "lob.postcards/letters (stub)", "sms": "twilio.messages (stub)",
                              "ai_voice": "twilio.voice+elevenlabs (stub)", "human_call": "dialer task for human"}[channel]
    log("outreach", entry)
    return entry
