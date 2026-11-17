"""WebRTC signaling for the in-app audio/video calls (US 28).

Audio and video go directly between browsers (WebRTC, mesh of at most MAX_PEERS people). This consumer only
passes the small setup messages between them:

client -> server
    {"type": "offer" | "answer", "to": <peer id>, "sdp": "..."}
    {"type": "ice-candidate", "to": <peer id>, "candidate": {...} | null}
    {"type": "media", "mic": bool, "cam": bool}
    {"type": "leave"}
server -> client
    {"type": "peers", "you": <peer>, "peers": [<peer>, ...]}   sent once, right after the connection
    {"type": "join", "peer": <peer>}
    {"type": "leave", "id": <peer id>}
    {"type": "media", "id": <peer id>, "mic": bool, "cam": bool}
    {"type": "offer" | "answer" | "ice-candidate", "from": <peer id>, "name": "...", ...}
    {"type": "error", "code": "call_full" | "bad_message", "detail": "..."}
where <peer> is {"id", "user_id", "name", "mic", "cam"}. The newcomer sends the offers to the people already
there, so two browsers never offer to each other at the same time.

Connection: ws/meetings/<id>/call/?ticket=...&mic=1&cam=1 (ticket from POST /api/meetings/<id>/call-ticket/).
"""

import json
import secrets
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.db.models import Q

from .calls import read_ticket
from .models import Meeting
from .serializers import display_name

MAX_PEERS = 4
MAX_MESSAGE_CHARS = 64 * 1024
MAX_SDP_CHARS = 32 * 1024
SIGNALS = {"offer", "answer", "ice-candidate"}

# Close codes (4000-4999 are free for applications).
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_FULL = 4409

# Who is in which call: {meeting id: {peer id: peer}}. In memory, like the channel layer: this works for a single
# server process. Several processes would need a shared store (Redis channel layer + Redis for this registry).
# Updates happen without any "await" in between, so concurrent connections cannot exceed MAX_PEERS.
ROOMS = {}


def public(peer):
    return {key: peer[key] for key in ("id", "user_id", "name", "mic", "cam")}


def _flag(params, name):
    return params.get(name, ["1"])[0] not in ("0", "false")


class CallConsumer(AsyncJsonWebsocketConsumer):
    peer = None
    joined_group = False

    @property
    def group(self):
        return f"meeting-call-{self.meeting_id}"

    @property
    def room(self):
        return ROOMS.get(self.meeting_id, {})

    @database_sync_to_async
    def member_name(self, user_id):
        """Display name if the user is active and is the organizer or a participant of this call, else None."""
        is_member = (
            Meeting.objects.filter(pk=self.meeting_id).exclude(call_room="")
            .filter(Q(owner_id=user_id) | Q(participants__id=user_id)).exists()
        )
        if not is_member:
            return None
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        return display_name(user) if user else None

    # ------------------------------------------------------------ connection
    async def connect(self):
        self.meeting_id = self.scope["url_route"]["kwargs"]["meeting_id"]
        params = parse_qs(self.scope.get("query_string", b"").decode("latin-1"))
        user_id = read_ticket(params.get("ticket", [""])[0], self.meeting_id)
        if user_id is None:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        name = await self.member_name(user_id)
        if name is None:
            await self.close(code=CLOSE_FORBIDDEN)
            return

        # Join the group first: no "join" sent by a later newcomer can be missed.
        await self.channel_layer.group_add(self.group, self.channel_name)
        self.joined_group = True

        # Check the limit, take a snapshot of who is there and reserve a place, with no await in between.
        room = ROOMS.setdefault(self.meeting_id, {})
        if len(room) >= MAX_PEERS:
            await self.accept()  # accept first so that the browser can read the reason
            await self.send_json({
                "type": "error", "code": "call_full",
                "detail": f"L'appel est complet ({MAX_PEERS} participants maximum).",
            })
            await self.close(code=CLOSE_FULL)
            return
        already_there = [public(p) for p in room.values()]
        self.peer = {
            "id": secrets.token_hex(8), "user_id": user_id, "name": name,
            "mic": _flag(params, "mic"), "cam": _flag(params, "cam"), "channel": self.channel_name,
        }
        room[self.peer["id"]] = self.peer

        await self.accept()
        await self.send_json({"type": "peers", "you": public(self.peer), "peers": already_there})
        await self.broadcast({"type": "join", "peer": public(self.peer)})

    async def disconnect(self, code):
        await self.leave_call()

    async def leave_call(self):
        """Free the place and tell the others. Safe to call twice ("leave" message, then disconnection)."""
        if self.peer:
            room = ROOMS.get(self.meeting_id)
            if room is not None:
                room.pop(self.peer["id"], None)
                if not room:
                    ROOMS.pop(self.meeting_id, None)
            await self.broadcast({"type": "leave", "id": self.peer["id"]})
            self.peer = None
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
        if kind in SIGNALS:
            await self.relay(kind, content)
        elif kind == "media":
            mic, cam = content.get("mic"), content.get("cam")
            if not isinstance(mic, bool) or not isinstance(cam, bool):
                return await self.reject_message()
            self.peer["mic"], self.peer["cam"] = mic, cam
            await self.broadcast({"type": "media", "id": self.peer["id"], "mic": mic, "cam": cam})
        elif kind == "leave":
            await self.leave_call()
            await self.close()
        else:
            await self.reject_message()

    async def relay(self, kind, content):
        target = self.room.get(content.get("to"))
        if not target or target is self.peer:
            return  # the other person has just left: nothing to do
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

    async def reject_message(self):
        await self.send_json({"type": "error", "code": "bad_message", "detail": "Message de signalisation invalide."})

    # ------------------------------------------------------------ messages from the channel layer
    async def broadcast(self, payload):
        """Send to everybody in the call except this connection."""
        await self.channel_layer.group_send(
            self.group, {"type": "call.message", "payload": payload, "exclude": self.channel_name},
        )

    async def call_message(self, event):
        if event.get("exclude") == self.channel_name:
            return
        await self.send_json(event["payload"])
