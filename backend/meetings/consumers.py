"""WebRTC signaling for the in-app audio/video calls (US 28), and the recording consent (exigence 8.1).

Audio and video go directly between browsers (WebRTC, mesh of at most settings.MEETING_MAX_PEERS people). This consumer only
passes the small setup messages between them:

client -> server
    {"type": "offer" | "answer", "to": <peer id>, "sdp": "..."}
    {"type": "ice-candidate", "to": <peer id>, "candidate": {...} | null}
    {"type": "media", "mic": bool, "cam": bool}
    {"type": "recording-request"}                    organizer only
    {"type": "recording-consent", "accepted": bool}
    {"type": "recording-stop"}                       organizer only (also cancels a request)
    {"type": "leave"}
server -> client
    {"type": "peers", "you": <peer>, "peers": [<peer>, ...], "recording": <recording>}   once admitted
    {"type": "consent-required", "you": <peer>, "recording": <recording>}   newcomer while a recording runs
    {"type": "join", "peer": <peer>}
    {"type": "leave", "id": <peer id>}
    {"type": "media", "id": <peer id>, "mic": bool, "cam": bool}
    {"type": "offer" | "answer" | "ice-candidate", "from": <peer id>, "name": "...", ...}
    {"type": "recording", ...<recording>}             sent to everybody each time the recording state changes
    {"type": "error", "code": "call_full" | "bad_message" | "forbidden" | "recording_busy" | "consent_refused",
     "detail": "..."}
where <peer> is {"id", "user_id", "name", "mic", "cam", "organizer"} and <recording> is
{"state": "idle" | "pending" | "recording", "session": id | null, "recorder": <peer id> | null,
 "accepted": [user ids], "waiting": [names], "reason": "" | "refused" | "stopped" | "recorder_left", "by": "..."}.
The newcomer sends the offers to the people already there, so two browsers never offer to each other at the
same time.

Recording: the organizer asks; every person connected receives the request and accepts or refuses. Each answer
is saved (RecordingConsent: who, when). The recording starts only when everybody connected has accepted; one
refusal cancels the request. While it runs, a newcomer is not announced to the others and cannot exchange
audio/video until they accept; if they refuse, they are disconnected (CLOSE_CONSENT_REFUSED). The organizer's
browser mixes and records the audio, then sends it to POST /api/meetings/<id>/recording/.

Connection: ws/meetings/<id>/call/?ticket=...&mic=1&cam=1 (ticket from POST /api/meetings/<id>/call-ticket/).
"""

import json
import secrets
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .calls import read_ticket
from .models import Meeting, RecordingConsent, RecordingSession
from .serializers import display_name

MAX_MESSAGE_CHARS = 64 * 1024
MAX_SDP_CHARS = 32 * 1024
SIGNALS = {"offer", "answer", "ice-candidate"}
PENDING, RECORDING, IDLE = "pending", "recording", "idle"

# Close codes (4000-4999 are free for applications).
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_FULL = 4409
CLOSE_CONSENT_REFUSED = 4451

# Who is in which call: {meeting id: {peer id: peer}}, and the recording of each call:
# {meeting id: {"session", "state", "recorder", "accepted": {user ids}}}. In memory, like the channel layer: this
# works for a single server process. Several processes would need a shared store (Redis).
# Every check-then-update on these dicts happens without any "await" in between, so concurrent connections
# cannot exceed settings.MEETING_MAX_PEERS nor start a recording twice.
ROOMS = {}
RECORDINGS = {}


def public(peer):
    return {key: peer[key] for key in ("id", "user_id", "name", "mic", "cam", "organizer")}


def _flag(params, name):
    return params.get(name, ["1"])[0] not in ("0", "false")


# ------------------------------------------------------------------ database
@database_sync_to_async
def create_session(meeting_id, user_id):
    """New recording request; the organizer who asks for it consents at the same time."""
    session = RecordingSession.objects.create(meeting_id=meeting_id, requested_by_id=user_id)
    RecordingConsent.objects.create(session=session, user_id=user_id, accepted=True)
    return session.id


@database_sync_to_async
def save_consent(session_id, user_id, accepted):
    RecordingConsent.objects.update_or_create(
        session_id=session_id, user_id=user_id, defaults={"accepted": accepted, "answered_at": timezone.now()},
    )


@database_sync_to_async
def mark_started(session_id):
    RecordingSession.objects.filter(pk=session_id, status=RecordingSession.PENDING).update(
        status=RecordingSession.RECORDING, started_at=timezone.now(),
    )


@database_sync_to_async
def mark_ended(session_id, status):
    # Only a session still pending or recording changes: an upload may already have marked it "uploaded".
    RecordingSession.objects.filter(
        pk=session_id, status__in=[RecordingSession.PENDING, RecordingSession.RECORDING],
    ).update(status=status, stopped_at=timezone.now())


class CallConsumer(AsyncJsonWebsocketConsumer):
    peer = None
    joined_group = False
    left = False  # after leave_call(): group messages still queued for this connection are dropped

    @property
    def group(self):
        return f"meeting-call-{self.meeting_id}"

    @property
    def room(self):
        return ROOMS.get(self.meeting_id, {})

    @database_sync_to_async
    def member(self, user_id):
        """(display name, is organizer) if the user is active and belongs to this call, else None."""
        meeting = (
            Meeting.objects.filter(pk=self.meeting_id).exclude(call_room="")
            .filter(Q(owner_id=user_id) | Q(participants__id=user_id)).values("owner_id").first()
        )
        if meeting is None:
            return None
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        return (display_name(user), meeting["owner_id"] == user_id) if user else None

    # ------------------------------------------------------------ connection
    async def connect(self):
        self.meeting_id = self.scope["url_route"]["kwargs"]["meeting_id"]
        params = parse_qs(self.scope.get("query_string", b"").decode("latin-1"))
        user_id = read_ticket(params.get("ticket", [""])[0], self.meeting_id)
        if user_id is None:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        member = await self.member(user_id)
        if member is None:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        name, organizer = member

        # Join the group first: no "join" sent by a later newcomer can be missed.
        await self.channel_layer.group_add(self.group, self.channel_name)
        self.joined_group = True

        # Check the limit and reserve a place, with no await in between.
        room = ROOMS.setdefault(self.meeting_id, {})
        max_peers = settings.MEETING_MAX_PEERS
        if len(room) >= max_peers:
            await self.accept()  # accept first so that the browser can read the reason
            await self.send_error("call_full", f"L'appel est complet ({max_peers} participants maximum).")
            await self.close(code=CLOSE_FULL)
            return
        rec = RECORDINGS.get(self.meeting_id)
        self.peer = {
            "id": secrets.token_hex(8), "user_id": user_id, "name": name, "organizer": organizer,
            "mic": _flag(params, "mic"), "cam": _flag(params, "cam"), "channel": self.channel_name,
            # While a recording runs, a newcomer stays apart until they accept it.
            "admitted": not (rec and rec["state"] == RECORDING and user_id not in rec["accepted"]),
        }
        room[self.peer["id"]] = self.peer

        await self.accept()
        if self.peer["admitted"]:
            await self.admit(announce_recording=bool(rec))
        else:
            await self.send_json({"type": "consent-required", "you": public(self.peer), "recording": self.recording_state(rec)})

    async def admit(self, announce_recording=False):
        """Let the peer into the call: list of the people there, and the others learn about them."""
        self.peer["admitted"] = True
        already_there = [public(p) for p in self.room.values() if p["admitted"] and p is not self.peer]
        rec = RECORDINGS.get(self.meeting_id)
        await self.send_json({
            "type": "peers", "you": public(self.peer), "peers": already_there, "recording": self.recording_state(rec),
        })
        await self.broadcast({"type": "join", "peer": public(self.peer)})
        if announce_recording and rec:
            await self.send_recording(rec)  # the others' "waiting" list now includes this peer

    async def disconnect(self, code):
        await self.leave_call()

    async def leave_call(self):
        """Free the place and tell the others. Safe to call twice ("leave" message, then disconnection)."""
        peer = self.peer
        self.left = True
        if peer:
            self.peer = None
            room = ROOMS.get(self.meeting_id)
            if room is not None:
                room.pop(peer["id"], None)
                if not room:
                    ROOMS.pop(self.meeting_id, None)
            if peer["admitted"]:
                await self.broadcast({"type": "leave", "id": peer["id"]})
            rec = RECORDINGS.get(self.meeting_id)
            if rec and rec["recorder"] == peer["id"]:
                await self.end_recording(rec, "recorder_left", peer["name"])
            elif rec and rec["state"] == PENDING:
                await self.update_recording(rec)  # the last person who had not answered may have left
        if self.joined_group:
            await self.channel_layer.group_discard(self.group, self.channel_name)
            self.joined_group = False

    # ------------------------------------------------------------ messages from the browser
    async def receive(self, text_data=None, bytes_data=None):
        if not self.peer:
            return
        if text_data is None or len(text_data) > MAX_MESSAGE_CHARS:
            return await self.reject_message()
        try:
            content = json.loads(text_data)
        except ValueError:
            return await self.reject_message()
        if not isinstance(content, dict):
            return await self.reject_message()
        await self.receive_json(content)

    async def receive_json(self, content, **kwargs):
        kind = content.get("type")
        if kind == "leave":
            await self.leave_call()
            await self.close()
        elif kind == "recording-consent":
            accepted = content.get("accepted")
            if not isinstance(accepted, bool):
                return await self.reject_message()
            await self.answer_recording(accepted)
        elif not self.peer["admitted"]:
            return  # a newcomer who has not accepted the recording yet takes no part in the call
        elif kind in SIGNALS:
            await self.relay(kind, content)
        elif kind == "media":
            mic, cam = content.get("mic"), content.get("cam")
            if not isinstance(mic, bool) or not isinstance(cam, bool):
                return await self.reject_message()
            self.peer["mic"], self.peer["cam"] = mic, cam
            await self.broadcast({"type": "media", "id": self.peer["id"], "mic": mic, "cam": cam})
        elif kind == "recording-request":
            await self.request_recording()
        elif kind == "recording-stop":
            await self.stop_recording()
        else:
            await self.reject_message()

    async def relay(self, kind, content):
        target = self.room.get(content.get("to"))
        if not target or target is self.peer or not target["admitted"]:
            return  # the other person has just left, or has not accepted the recording yet
        payload = {"type": kind, "from": self.peer["id"], "name": self.peer["name"]}
        if kind == "ice-candidate":
            candidate = content.get("candidate")
            if candidate is not None and not isinstance(candidate, dict):
                return await self.reject_message()
            payload["candidate"] = candidate
        else:
            sdp = content.get("sdp")
            if not isinstance(sdp, str) or not sdp or len(sdp) > MAX_SDP_CHARS:
                return await self.reject_message()
            payload["sdp"] = sdp
        # Sent to the recipient's channel only, never to the whole group.
        await self.channel_layer.send(target["channel"], {"type": "call.message", "payload": payload})

    async def send_error(self, code, detail):
        await self.send_json({"type": "error", "code": code, "detail": detail})

    async def reject_message(self):
        await self.send_error("bad_message", "Message de signalisation invalide.")

    # ------------------------------------------------------------ recording consent
    def recording_state(self, rec, reason="", by=""):
        if not rec:
            return {"state": IDLE, "session": None, "recorder": None, "accepted": [], "waiting": [], "reason": reason, "by": by}
        admitted = [p for p in self.room.values() if p["admitted"]]
        waiting = sorted({p["name"] for p in admitted if p["user_id"] not in rec["accepted"]})
        return {
            "state": rec["state"], "session": rec["session"], "recorder": rec["recorder"],
            "accepted": sorted(rec["accepted"]), "waiting": waiting, "reason": reason, "by": by,
        }

    async def send_recording(self, rec, reason="", by=""):
        await self.send_all({"type": "recording", **self.recording_state(rec, reason, by)})

    async def request_recording(self):
        if not self.peer["organizer"]:
            return await self.send_error("forbidden", "Seul l'organisateur peut demander l'enregistrement.")
        if self.meeting_id in RECORDINGS:
            return await self.send_error("recording_busy", "Un enregistrement est déjà demandé ou en cours.")
        rec = {"session": None, "state": PENDING, "recorder": self.peer["id"], "accepted": {self.peer["user_id"]}}
        RECORDINGS[self.meeting_id] = rec  # reserved before the await: a second request is refused
        session = await create_session(self.meeting_id, self.peer["user_id"])
        rec["session"] = session
        if RECORDINGS.get(self.meeting_id) is not rec:  # the organizer left meanwhile
            await mark_ended(session, RecordingSession.CANCELLED)
            return
        await self.update_recording(rec)

    async def update_recording(self, rec):
        """Start the recording if everybody connected has accepted, and tell everybody the state."""
        if rec["session"] is None or RECORDINGS.get(self.meeting_id) is not rec:
            return
        admitted = [p for p in self.room.values() if p["admitted"]]
        if rec["state"] == PENDING and all(p["user_id"] in rec["accepted"] for p in admitted):
            rec["state"] = RECORDING  # no await since the check: it starts once
            await mark_started(rec["session"])
        await self.send_recording(rec)

    async def answer_recording(self, accepted):
        rec = RECORDINGS.get(self.meeting_id)
        if not rec or rec["session"] is None:
            if not self.peer["admitted"]:  # the recording ended while the newcomer was deciding
                await self.admit()
            return
        session = rec["session"]
        await save_consent(session, self.peer["user_id"], accepted)
        if not self.peer:  # disconnected meanwhile
            return
        rec = RECORDINGS.get(self.meeting_id)
        if not rec or rec["session"] != session:
            if not self.peer["admitted"]:
                await self.admit()
            return

        if accepted:
            rec["accepted"].add(self.peer["user_id"])
            if not self.peer["admitted"]:
                await self.admit()
            await self.update_recording(rec)
        elif not self.peer["admitted"]:
            # A newcomer who refuses a running recording cannot stay in the call.
            await self.send_error("consent_refused", "Vous avez refusé l'enregistrement en cours : vous ne pouvez pas rejoindre l'appel pour le moment.")
            await self.leave_call()
            await self.close(code=CLOSE_CONSENT_REFUSED)
        elif rec["state"] == PENDING:
            await self.end_recording(rec, "refused", self.peer["name"])
        # A refusal after the start changes nothing: whoever no longer agrees leaves the call.

    async def stop_recording(self):
        rec = RECORDINGS.get(self.meeting_id)
        if not rec:
            return
        if not self.peer["organizer"]:
            return await self.send_error("forbidden", "Seul l'organisateur peut arrêter l'enregistrement.")
        await self.end_recording(rec, "stopped", self.peer["name"])

    async def end_recording(self, rec, reason, by=""):
        if RECORDINGS.get(self.meeting_id) is not rec:
            return
        RECORDINGS.pop(self.meeting_id)
        waiting_newcomers = [p for p in self.room.values() if not p["admitted"]]
        if rec["session"] is not None:
            status = (
                RecordingSession.STOPPED if rec["state"] == RECORDING
                else RecordingSession.REFUSED if reason == "refused" else RecordingSession.CANCELLED
            )
            await mark_ended(rec["session"], status)
        await self.send_recording(None, reason, by)
        for peer in waiting_newcomers:  # nothing to accept any more: they join the call
            await self.channel_layer.send(peer["channel"], {"type": "call.admit"})

    # ------------------------------------------------------------ messages from the channel layer
    async def broadcast(self, payload):
        """Send to everybody in the call except this connection."""
        await self.channel_layer.group_send(
            self.group, {"type": "call.message", "payload": payload, "exclude": self.channel_name},
        )

    async def send_all(self, payload):
        """Send to everybody in the call, this connection included."""
        await self.channel_layer.group_send(self.group, {"type": "call.message", "payload": payload})

    async def call_message(self, event):
        if self.left or event.get("exclude") == self.channel_name:
            return
        await self.send_json(event["payload"])

    async def call_admit(self, event):
        if self.peer and not self.peer["admitted"]:
            await self.admit()
