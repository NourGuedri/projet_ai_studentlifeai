"use client";
// In-app audio/video call (WebRTC). Audio and video go directly between the browsers; the backend
// WebSocket (meetings/consumers.py) only passes the setup messages. At most 4 people (mesh).
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Loading, PageHeader, btnClass, cx } from "@/components/ui";
import { api, wsUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const MAX_PEERS = 4;
const AUDIO = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
const VIDEO = { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" };
const KINDS = ["audio", "video"];

// ------------------------------------------------------------------ camera and microphone
function mediaErrorMessage(err) {
  switch (err?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "L'accès à la caméra ou au micro a été refusé. Autorisez-le dans le navigateur (icône à gauche de l'adresse), puis réessayez.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "Aucun micro ni aucune caméra n'a été détecté sur cet appareil.";
    case "NotReadableError":
    case "AbortError":
      return "La caméra ou le micro est déjà utilisé par une autre application. Fermez-la, puis réessayez.";
    case "Insecure":
      return "Le navigateur n'autorise la caméra et le micro que sur une page sécurisée (https:// ou localhost).";
    default:
      return "Impossible d'accéder à la caméra ou au micro.";
  }
}

function getMedia(audio, video) {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return Promise.reject({ name: "Insecure" });
  }
  return navigator.mediaDevices.getUserMedia({ audio: audio && AUDIO, video: video && VIDEO });
}

/** Microphone (+ camera if wanted). Falls back to what is available, with a notice. */
async function openDevices(wantVideo) {
  try {
    return { stream: await getMedia(true, wantVideo), notice: "" };
  } catch (err) {
    if (!wantVideo || ["NotAllowedError", "SecurityError", "Insecure"].includes(err?.name)) throw err;
    try {
      return { stream: await getMedia(true, false), notice: `Caméra indisponible : ${mediaErrorMessage(err)} Vous rejoindrez en audio seulement.` };
    } catch {
      return { stream: await getMedia(false, true), notice: "Aucun micro détecté : les autres ne vous entendront pas." };
    }
  }
}

const initials = (name = "") => name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

// ------------------------------------------------------------------ small UI pieces
const PATHS = {
  mic: ["M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z", "M19 11a7 7 0 0 1-14 0M12 18v3"],
  micOff: ["M15 9.3V6a3 3 0 0 0-5.7-1.3", "M9 9v3a3 3 0 0 0 5.1 2.1", "M19 11a7 7 0 0 1-1.2 3.9M16.9 16.9A7 7 0 0 1 5 11", "M12 18v3M3 3l18 18"],
  cam: ["M3 7a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z", "M16 10l5-3v10l-5-3"],
  camOff: ["M8 5h6a2 2 0 0 1 2 2v3l5-3v10l-2-1.2", "M16 16v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2", "M3 3l18 18"],
  phone: ["M3 13.5c4.9-4.4 13.1-4.4 18 0l-2 3-3.5-1.2v-2.6a10 10 0 0 0-7 0v2.6L5 16.5l-2-3z"],
};
function CallIcon({ name, className = "h-5 w-5" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {PATHS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

function ControlButton({ label, icon, active = true, danger = false, disabled = false, onClick }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
      className={cx(
        "flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition-colors sm:h-14 sm:w-14",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:cursor-not-allowed disabled:opacity-50",
        danger ? "bg-red-600 text-white hover:bg-red-700"
          : active ? "bg-white/15 text-white hover:bg-white/25" : "bg-white text-navy-900 hover:bg-slate-200",
      )}>
      <CallIcon name={icon} className="h-6 w-6" />
    </button>
  );
}

function Tile({ stream, name, mic, cam, self = false, status, className }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && ref.current.srcObject !== stream) ref.current.srcObject = stream ?? null;
  }, [stream]);
  const showVideo = cam && (stream?.getVideoTracks().length ?? 0) > 0;
  return (
    <div className={cx("relative overflow-hidden rounded-xl bg-navy-900", className)}>
      {/* Kept in the page even when the camera is off: it also plays the sound of remote people. */}
      <video ref={ref} autoPlay playsInline muted={self}
        className={cx("h-full w-full object-cover", self && "-scale-x-100", !showVideo && "invisible")} />
      {!showVideo && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-xl font-semibold text-white sm:h-20 sm:w-20 sm:text-2xl">
            {initials(name)}
          </span>
        </div>
      )}
      {status && <div className="absolute inset-x-0 top-0 bg-black/55 px-3 py-1.5 text-center text-xs text-white">{status}</div>}
      <div className="absolute bottom-2 left-2 flex max-w-[calc(100%-1rem)] items-center gap-1.5 rounded-md bg-black/60 px-2 py-1 text-xs font-medium text-white">
        {!mic && <span title="Micro coupé" className="text-red-300"><CallIcon name="micOff" className="h-4 w-4" /><span className="sr-only">Micro coupé</span></span>}
        {!cam && <span title="Caméra coupée" className="text-slate-300"><CallIcon name="camOff" className="h-4 w-4" /><span className="sr-only">Caméra coupée</span></span>}
        <span className="truncate">{name}{self && " (vous)"}</span>
      </div>
    </div>
  );
}

const CONNECTION_STATUS = {
  new: "Connexion…",
  connecting: "Connexion…",
  disconnected: "Connexion instable…",
  failed: "Connexion directe impossible avec ce participant (réseau).",
};

// ------------------------------------------------------------------ page
export default function MeetingCallPage() {
  const { id } = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const [meeting, setMeeting] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [phase, setPhase] = useState("lobby"); // lobby | joining | call
  const [localStream, setLocalStream] = useState(null);
  const [micOn, setMicOn] = useState(false);
  const [camOn, setCamOn] = useState(false);
  const [audioOnly, setAudioOnly] = useState(false);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [previewReady, setPreviewReady] = useState(false);
  const [mediaError, setMediaError] = useState("");
  const [notice, setNotice] = useState("");
  const [callError, setCallError] = useState("");
  const [offline, setOffline] = useState(false);
  const [me, setMe] = useState(null);
  const [peers, setPeers] = useState({}); // id -> {id, name, mic, cam, stream, conn}

  const localRef = useRef(null); // MediaStream sent to the others
  const wsRef = useRef(null);
  const pcsRef = useRef(new Map()); // peer id -> {pc, remote: MediaStream, pending: [candidates]}
  const earlyCandidatesRef = useRef(new Map()); // candidates received before the offer
  const iceRef = useRef([]);
  const queueRef = useRef(Promise.resolve()); // signaling messages are handled one at a time
  const leavingRef = useRef(false);
  const unmountedRef = useRef(false);
  const previewTokenRef = useRef(0);

  // ---------------------------------------------------------------- local media
  const localTrack = (kind) => localRef.current?.getTracks().find((t) => t.kind === kind && t.readyState === "live");

  function stopLocal() {
    localRef.current?.getTracks().forEach((t) => t.stop());
    localRef.current = null;
  }

  function showLocal() {
    const stream = localRef.current;
    setLocalStream(stream ? new MediaStream(stream.getTracks()) : null);
    const mic = !!localTrack("audio")?.enabled;
    const cam = !!localTrack("video");
    setMicOn(mic);
    setCamOn(cam);
    send({ type: "media", mic, cam });
  }

  const senderFor = (pc, kind) => pc.getTransceivers().find((t) => t.receiver.track?.kind === kind)?.sender;

  function replaceEverywhere(kind, track) {
    return Promise.all([...pcsRef.current.values()].map(({ pc }) => senderFor(pc, kind)?.replaceTrack(track).catch(() => {})));
  }

  async function startPreview(wantVideo) {
    const token = ++previewTokenRef.current;
    stopLocal();
    setMediaError("");
    setNotice("");
    try {
      const { stream, notice: text } = await openDevices(wantVideo);
      if (token !== previewTokenRef.current || unmountedRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      localRef.current = stream;
      setNotice(text);
    } catch (err) {
      if (token !== previewTokenRef.current) return;
      setMediaError(mediaErrorMessage(err));
    }
    showLocal();
    setPreviewReady(true);
  }

  async function addLocalTrack(kind) {
    try {
      const stream = await getMedia(kind === "audio", kind === "video");
      const track = stream.getTracks()[0];
      if (unmountedRef.current) { track.stop(); return false; }
      localRef.current ??= new MediaStream();
      localRef.current.addTrack(track);
      await replaceEverywhere(kind, track);
      setMediaError("");
      setNotice("");
      return true;
    } catch (err) {
      setMediaError(mediaErrorMessage(err));
      return false;
    }
  }

  async function removeLocalTrack(kind) {
    const track = localTrack(kind);
    if (!track) return;
    track.stop(); // turns the camera light off, unlike track.enabled = false
    localRef.current.removeTrack(track);
    await replaceEverywhere(kind, null);
  }

  async function toggleMic() {
    setDeviceBusy(true);
    const track = localTrack("audio");
    if (track) track.enabled = !track.enabled;
    else await addLocalTrack("audio");
    showLocal();
    setDeviceBusy(false);
  }

  async function toggleCam() {
    setDeviceBusy(true);
    if (localTrack("video")) await removeLocalTrack("video");
    else if (await addLocalTrack("video")) setAudioOnly(false);
    showLocal();
    setDeviceBusy(false);
  }

  async function chooseAudioOnly(value) {
    setAudioOnly(value);
    setDeviceBusy(true);
    if (value) await removeLocalTrack("video");
    else await addLocalTrack("video");
    showLocal();
    setDeviceBusy(false);
  }

  // ---------------------------------------------------------------- signaling
  function send(message) {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
  }

  const patchPeer = (peerId, patch) =>
    setPeers((prev) => (prev[peerId] ? { ...prev, [peerId]: { ...prev[peerId], ...patch } } : prev));

  const addPeer = (peer) =>
    setPeers((prev) => (prev[peer.id] ? prev : { ...prev, [peer.id]: { mic: true, cam: true, conn: "new", ...peer } }));

  function closePeer(peerId) {
    pcsRef.current.get(peerId)?.pc.close();
    pcsRef.current.delete(peerId);
    earlyCandidatesRef.current.delete(peerId);
    setPeers((prev) => {
      const { [peerId]: _gone, ...rest } = prev;
      return rest;
    });
  }

  function closeAllPeers() {
    pcsRef.current.forEach(({ pc }) => pc.close());
    pcsRef.current.clear();
    earlyCandidatesRef.current.clear();
    setPeers({});
  }

  function createPeerConnection(peerId, offerer) {
    pcsRef.current.get(peerId)?.pc.close();
    const pc = new RTCPeerConnection({ iceServers: iceRef.current });
    const entry = { pc, remote: new MediaStream(), pending: earlyCandidatesRef.current.get(peerId) ?? [] };
    earlyCandidatesRef.current.delete(peerId);
    pcsRef.current.set(peerId, entry);
    pc.onicecandidate = (e) => send({ type: "ice-candidate", to: peerId, candidate: e.candidate ? e.candidate.toJSON() : null });
    pc.ontrack = (e) => {
      entry.remote.addTrack(e.track);
      patchPeer(peerId, { stream: new MediaStream(entry.remote.getTracks()) });
    };
    pc.onconnectionstatechange = () => patchPeer(peerId, { conn: pc.connectionState });
    if (offerer) {
      // One audio and one video slot, even without a camera: it can be switched on later with replaceTrack.
      for (const kind of KINDS) pc.addTransceiver(localTrack(kind) ?? kind, { direction: "sendrecv" });
    }
    return entry;
  }

  async function addCandidate(pc, candidate) {
    try {
      await pc.addIceCandidate(candidate ?? undefined);
    } catch {
      // A late or duplicate candidate: harmless.
    }
  }

  async function flushCandidates(entry) {
    const pending = entry.pending.splice(0);
    for (const candidate of pending) await addCandidate(entry.pc, candidate);
  }

  async function callPeer(peerId) {
    const { pc } = createPeerConnection(peerId, true);
    await pc.setLocalDescription(await pc.createOffer());
    send({ type: "offer", to: peerId, sdp: pc.localDescription.sdp });
  }

  async function handle(msg) {
    switch (msg.type) {
      case "peers":
        setMe(msg.you);
        setPeers(Object.fromEntries(msg.peers.map((p) => [p.id, { ...p, conn: "new" }])));
        setPhase("call");
        // The newcomer calls the people already there.
        for (const peer of msg.peers) await callPeer(peer.id);
        break;
      case "join":
        addPeer(msg.peer);
        break;
      case "leave":
        closePeer(msg.id);
        break;
      case "media":
        patchPeer(msg.id, { mic: msg.mic, cam: msg.cam });
        break;
      case "offer": {
        addPeer({ id: msg.from, name: msg.name });
        const entry = createPeerConnection(msg.from, false);
        const { pc } = entry;
        await pc.setRemoteDescription({ type: "offer", sdp: msg.sdp });
        for (const transceiver of pc.getTransceivers()) {
          transceiver.direction = "sendrecv";
          await transceiver.sender.replaceTrack(localTrack(transceiver.receiver.track.kind) ?? null);
        }
        await pc.setLocalDescription(await pc.createAnswer());
        send({ type: "answer", to: msg.from, sdp: pc.localDescription.sdp });
        await flushCandidates(entry);
        break;
      }
      case "answer": {
        const entry = pcsRef.current.get(msg.from);
        if (!entry) return;
        await entry.pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
        await flushCandidates(entry);
        break;
      }
      case "ice-candidate": {
        const entry = pcsRef.current.get(msg.from);
        if (!entry) {
          const early = earlyCandidatesRef.current.get(msg.from) ?? [];
          earlyCandidatesRef.current.set(msg.from, [...early, msg.candidate]);
        } else if (entry.pc.remoteDescription) {
          await addCandidate(entry.pc, msg.candidate);
        } else {
          entry.pending.push(msg.candidate);
        }
        break;
      }
      case "error":
        if (msg.code !== "call_full") console.warn("Appel :", msg.detail);
        break;
      default:
    }
  }

  async function join() {
    setCallError("");
    setPhase("joining");
    leavingRef.current = false;
    let ticket;
    try {
      const data = await api.post(`/meetings/${id}/call-ticket/`);
      ticket = data.ticket;
      iceRef.current = data.ice_servers ?? [];
    } catch (err) {
      setCallError(err.message);
      setPhase("lobby");
      return;
    }
    if (unmountedRef.current) return;

    const mic = !!localTrack("audio")?.enabled;
    const cam = !!localTrack("video");
    const ws = new WebSocket(wsUrl(`/ws/meetings/${id}/call/?ticket=${encodeURIComponent(ticket)}&mic=${mic ? 1 : 0}&cam=${cam ? 1 : 0}`));
    wsRef.current = ws;
    let opened = false;
    let refusal = "";
    ws.onopen = () => { opened = true; };
    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.type === "error" && msg.code === "call_full") refusal = msg.detail;
      queueRef.current = queueRef.current.then(() => handle(msg)).catch((err) => console.error("Appel :", err));
    };
    ws.onclose = (event) => {
      if (wsRef.current !== ws) return; // closed on purpose
      wsRef.current = null;
      closeAllPeers();
      setMe(null);
      if (leavingRef.current) return;
      setPhase("lobby");
      if (refusal || event.code === 4409) {
        setCallError(refusal || `L'appel est complet (${MAX_PEERS} participants maximum). Réessayez quand quelqu'un sera parti.`);
      } else if (!navigator.onLine) {
        setCallError("Vous êtes hors ligne : l'appel a été interrompu. Vérifiez votre connexion, puis rejoignez à nouveau l'appel.");
      } else if (!opened) {
        setCallError("Impossible de joindre le serveur d'appel (serveur arrêté ou accès refusé). Réessayez dans un instant.");
      } else {
        setCallError("La connexion au serveur d'appel a été perdue. Rejoignez à nouveau l'appel.");
      }
    };
  }

  /** Leave the call and free camera and microphone. Safe to call several times. */
  function teardown() {
    previewTokenRef.current += 1;
    leavingRef.current = true;
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "leave" }));
      ws.close(1000);
    }
    closeAllPeers();
    stopLocal();
  }

  function hangUp() {
    teardown();
    router.push(`/reunions/${id}`);
  }

  // ---------------------------------------------------------------- lifecycle
  useEffect(() => {
    unmountedRef.current = false;
    const goOffline = () => setOffline(true);
    const goOnline = () => setOffline(false);
    setOffline(!navigator.onLine);
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    window.addEventListener("pagehide", teardown);
    return () => {
      unmountedRef.current = true;
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
      window.removeEventListener("pagehide", teardown);
      teardown();
    };
  }, []);

  useEffect(() => {
    api.get(`/meetings/${id}/`).then(setMeeting).catch((err) => setLoadError(err.message));
  }, [id]);

  useEffect(() => {
    if (meeting?.is_call) startPreview(true);
  }, [meeting?.id, meeting?.is_call]);

  // ---------------------------------------------------------------- render
  const back = <Link href={`/reunions/${id}`} className={btnClass("ghost")}>Retour à la réunion</Link>;
  if (loadError) return <><Alert>{loadError}</Alert><div className="mt-4">{back}</div></>;
  if (!meeting) return <Loading />;
  if (!meeting.is_call) {
    return <><Alert>Cette réunion n'est pas un appel audio/vidéo.</Alert><div className="mt-4">{back}</div></>;
  }

  const myName = me?.name ?? ([user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email || "Vous");
  const controls = (
    <>
      <ControlButton label={micOn ? "Couper le micro" : "Activer le micro"} icon={micOn ? "mic" : "micOff"}
        active={micOn} disabled={deviceBusy} onClick={toggleMic} />
      <ControlButton label={camOn ? "Couper la caméra" : "Activer la caméra"} icon={camOn ? "cam" : "camOff"}
        active={camOn} disabled={deviceBusy} onClick={toggleCam} />
    </>
  );

  if (phase !== "call") {
    const hasMedia = !!localStream && localStream.getTracks().length > 0;
    return (
      <>
        <PageHeader title={meeting.title} subtitle="Vérifiez votre caméra et votre micro avant de rejoindre l'appel." actions={back} />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="relative">
            <Tile stream={localStream} name={myName} mic={micOn} cam={camOn} self className="aspect-[4/3] sm:aspect-video" />
            <div className="absolute inset-x-0 bottom-3 flex justify-center gap-3">{controls}</div>
          </div>
          <Card className="space-y-4">
            <label className="flex cursor-pointer items-start gap-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand-600" checked={audioOnly}
                disabled={deviceBusy} onChange={(e) => chooseAudioOnly(e.target.checked)} />
              <span>
                <span className="font-medium text-navy-900">Audio seulement</span>
                <span className="block text-slate-500">Votre caméra reste éteinte. Vous pourrez l'allumer pendant l'appel.</span>
              </span>
            </label>
            <Alert>{mediaError}</Alert>
            <Alert tone="info">{notice}</Alert>
            <Alert>{callError}</Alert>
            {offline && <Alert>Vous êtes hors ligne. Vérifiez votre connexion internet.</Alert>}
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="success" onClick={join} loading={phase === "joining"} disabled={!previewReady || offline}>
                {hasMedia ? "Rejoindre l'appel" : "Rejoindre sans micro ni caméra"}
              </Button>
              {mediaError && <Button variant="secondary" onClick={() => startPreview(!audioOnly)}>Réessayer</Button>}
            </div>
            <p className="text-xs text-slate-500">
              Appel privé réservé à l'organisateur et aux invités ({MAX_PEERS} personnes maximum). Le son et l'image
              passent directement entre les participants et ne sont pas enregistrés.
            </p>
          </Card>
        </div>
      </>
    );
  }

  const others = Object.values(peers);
  const count = others.length + 1;
  const grid = count === 1 ? "grid-cols-1" : count === 2 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-2";
  return (
    <div className="flex min-h-[calc(100dvh-10rem)] flex-col gap-3 rounded-2xl bg-navy-950 p-2 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-white">
        <h1 className="truncate font-display text-base font-semibold sm:text-lg">{meeting.title}</h1>
        <span className="text-xs text-slate-300 sm:text-sm">{count} / {MAX_PEERS} participants</span>
      </div>
      {offline && <Alert>Vous êtes hors ligne : l'image et le son des autres peuvent être coupés.</Alert>}
      <Alert>{mediaError}</Alert>
      <div className={cx("grid flex-1 content-center gap-2 sm:gap-3", grid)}>
        <Tile stream={localStream} name={myName} mic={micOn} cam={camOn} self
          className={cx(count === 1 ? "mx-auto aspect-[4/3] w-full max-w-3xl sm:aspect-video" : "aspect-[4/3] sm:aspect-video")} />
        {others.map((p) => (
          <Tile key={p.id} stream={p.stream} name={p.name} mic={p.mic} cam={p.cam}
            status={CONNECTION_STATUS[p.conn]} className="aspect-[4/3] sm:aspect-video" />
        ))}
      </div>
      {count === 1 && <p className="text-center text-sm text-slate-300">En attente des autres participants…</p>}
      <div className="flex justify-center gap-3 pb-1 pt-1 sm:gap-4">
        {controls}
        <ControlButton label="Raccrocher" icon="phone" danger onClick={hangUp} />
      </div>
    </div>
  );
}
