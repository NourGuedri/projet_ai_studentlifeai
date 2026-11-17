"""Tickets that let a browser open the call WebSocket of one meeting.

The JWT never travels in the WebSocket URL (URLs end up in logs and browser history): the client asks
POST /api/meetings/<id>/call-ticket/ with its JWT and gets a signed ticket valid for TICKET_MAX_AGE seconds,
bound to that user and that meeting.
"""

from django.core import signing

TICKET_SALT = "meetings.call-ticket"
TICKET_MAX_AGE = 60  # seconds


def make_ticket(user, meeting):
    return signing.dumps({"u": user.id, "m": meeting.id}, salt=TICKET_SALT, compress=True)


def read_ticket(ticket, meeting_id):
    """User id carried by a valid, unexpired ticket for this meeting, else None."""
    if not ticket:
        return None
    try:
        data = signing.loads(ticket, salt=TICKET_SALT, max_age=TICKET_MAX_AGE)
    except signing.BadSignature:  # also covers SignatureExpired
        return None
    if not isinstance(data, dict) or data.get("m") != meeting_id or not isinstance(data.get("u"), int):
        return None
    return data["u"]
