"""Helpers every module can call to notify a user.

    from notifications.services import notify
    notify(user, "Planning mis à jour", "Votre cours de jeudi est annulé.", link="/planning", kind="warning")
"""
from .models import Notification

KINDS = {k for k, _ in Notification.KINDS}


def _clean_link(link):
    # Only internal frontend paths: never let a notification send the user to another site.
    link = (link or "").strip()
    return link[:200] if link.startswith("/") and not link.startswith("//") else ""


def _fields(title, message, link, kind):
    return {
        "title": str(title)[:150],
        "message": str(message or ""),
        "link": _clean_link(link),
        "kind": kind if kind in KINDS else "info",
    }


def notify(user, title, message="", link="", kind="info"):
    return Notification.objects.create(user=user, **_fields(title, message, link, kind))


def notify_many(users, title, message="", link="", kind="info"):
    """One notification per user, in a single query. Returns how many were created."""
    fields = _fields(title, message, link, kind)
    created = Notification.objects.bulk_create([Notification(user=u, **fields) for u in users])
    return len(created)
