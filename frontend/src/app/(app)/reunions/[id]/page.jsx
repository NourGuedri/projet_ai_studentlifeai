"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AiCard, TaskList } from "@/components/AiResult";
import { Alert, Badge, Button, Card, Loading, PageHeader, Spinner, Textarea, btnClass, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { MEETING_STATUS, fmtDateTime, fmtDay } from "@/lib/labels";

const POLL_MS = 3000;
// Steps of the automatic processing (meetings/services.py), in order.
const STEPS = [
  ["transcribing", "Transcription de l'enregistrement"],
  ["analyzing", "Analyse par l'IA : résumé, sujets, points importants, décisions et tâches"],
];

/** The recording, read with the JWT (GET /api/meetings/<id>/audio/): it has no public URL. */
function AudioPlayer({ path }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let url = "";
    let cancelled = false;
    setSrc("");
    setError("");
    api.blob(path)
      .then((data) => {
        if (cancelled) return;
        url = URL.createObjectURL(data);
        setSrc(url);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  if (error) return <Alert>{error}</Alert>;
  if (!src) return <p className="flex items-center gap-2 text-sm text-slate-500"><Spinner className="h-4 w-4" /> Chargement de l'enregistrement…</p>;
  return <audio controls src={src} className="w-full" />;
}

function ProcessingCard({ meeting, isOwner, onRetry, busy }) {
  if (meeting.is_processing) {
    const current = STEPS.findIndex(([key]) => key === meeting.processing_status);
    return (
      <Card>
        <h2 className="mb-3 font-display text-lg font-semibold">Traitement automatique en cours</h2>
        <ol className="space-y-2 text-sm">
          {STEPS.map(([key, label], i) => (
            <li key={key} className={cx("flex items-center gap-2", i > current ? "text-slate-400" : i === current ? "font-medium text-navy-900" : "text-slate-500")}>
              {i === current ? <Spinner className="h-4 w-4" />
                : <span className={cx("inline-block h-4 w-4 rounded-full border-2", i < current ? "border-leaf-600 bg-leaf-600" : "border-slate-300")} aria-hidden="true" />}
              {label}{i < current && " — terminé"}
            </li>
          ))}
        </ol>
        <p className="mt-3 text-sm text-slate-500">Cela peut prendre quelques minutes. La page se met à jour toute seule.</p>
      </Card>
    );
  }
  if (meeting.processing_status === "error") {
    return (
      <Alert>
        <span className="block font-medium">Le traitement automatique a échoué.</span>
        {meeting.processing_error}
        {isOwner && (
          <span className="mt-2 block">
            <Button size="sm" variant="secondary" onClick={onRetry} loading={busy === "process"} disabled={!!busy}>Relancer le traitement</Button>
          </span>
        )}
      </Alert>
    );
  }
  return null;
}

function ItemList({ items, empty }) {
  if (!items?.length) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-700">
      {items.map((item, i) => <li key={i}>{item}</li>)}
    </ul>
  );
}

export default function MeetingDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [meeting, setMeeting] = useState(null);
  const [transcript, setTranscript] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState("");
  const [extracted, setExtracted] = useState(false);

  function show(m) {
    setMeeting(m);
    setTranscript(m.transcript);
  }

  useEffect(() => {
    api.get(`/meetings/${id}/`).then(show).catch((err) => setNotFound(err.message));
  }, [id]);

  // While the server transcribes and analyses, reload the meeting every 3 seconds.
  const processing = !!meeting?.is_processing;
  useEffect(() => {
    if (!processing) return undefined;
    const timer = setInterval(() => {
      api.get(`/meetings/${id}/`).then(show).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [id, processing]);

  async function run(action) {
    setBusy(action);
    setError("");
    try {
      show(await api.post(`/meetings/${id}/${action}/`));
      if (action === "extract") setExtracted(true);
    } catch (err) {
      setError(err.message);
      // The meeting may have switched to FAILED.
      api.get(`/meetings/${id}/`).then((m) => setMeeting((prev) => ({ ...m, transcript: prev.transcript }))).catch(() => {});
    } finally {
      setBusy("");
    }
  }

  async function saveTranscript() {
    setBusy("save");
    setError("");
    try {
      show(await api.patch(`/meetings/${id}/`, { transcript }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function remove() {
    if (!confirm("Supprimer cette réunion et son enregistrement ?")) return;
    await api.del(`/meetings/${id}/`);
    router.replace("/reunions");
  }

  if (notFound) return <Alert>{notFound}</Alert>;
  if (!meeting) return <Loading />;
  const [statusLabel, tone] = MEETING_STATUS[meeting.status] ?? [meeting.status, "slate"];
  const hasTranscript = meeting.transcript.trim().length > 0;
  const dirty = transcript !== meeting.transcript;
  // Invited participants only read: no AI, no deletion, no transcript editing.
  const isOwner = meeting.is_owner;
  const locked = !!busy || processing;
  const when = meeting.scheduled_at ? fmtDateTime(meeting.scheduled_at) : fmtDay(meeting.date);
  const analysed = meeting.summary || meeting.topics.length > 0 || meeting.key_points.length > 0;
  const extractedResults = meeting.decisions.length > 0 || meeting.tasks.length > 0 || extracted;

  return (
    <>
      <PageHeader title={meeting.title} subtitle={`${when} · Organisé par ${isOwner ? "vous" : meeting.owner_name}`}
        actions={<>
          <Link href="/reunions" className={btnClass("ghost")}>Retour</Link>
          {meeting.is_call && (
            <Link href={`/reunions/${meeting.id}/appel`} className={btnClass("success")}>Rejoindre l'appel</Link>
          )}
          {isOwner && <Button variant="danger" onClick={remove} disabled={processing}>Supprimer</Button>}
        </>} />
      <div className="-mt-3 mb-5 flex flex-wrap gap-1.5">
        <Badge tone={tone}>{statusLabel}</Badge>
        {processing && <Badge tone="blue">{meeting.processing_label}</Badge>}
        {meeting.is_call && <Badge tone="blue">Appel vidéo</Badge>}
        {!isOwner && <Badge tone="amber">Invité</Badge>}
      </div>

      <div className="space-y-6">
        {(meeting.is_call || meeting.participants.length > 0) && (
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Participants</h2>
            <ul className="divide-y divide-slate-100 text-sm">
              <li className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="font-medium text-navy-900">{meeting.owner_name}</span>
                <Badge tone="green">Organisateur</Badge>
              </li>
              {meeting.participants.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="font-medium text-navy-900">{p.full_name}</span>
                  {p.full_name !== p.email && <span className="text-slate-500">{p.email}</span>}
                </li>
              ))}
            </ul>
            {meeting.participants.length === 0 && <p className="mt-2 text-sm text-slate-500">Aucun participant invité.</p>}
            {meeting.is_call && (
              <p className="mt-3 text-sm text-slate-500">
                L'appel audio/vidéo se déroule dans StudentLife, sans service externe (4 personnes connectées au maximum).
                L'organisateur peut l'enregistrer si tous les participants connectés l'acceptent.
              </p>
            )}
          </Card>
        )}

        <ProcessingCard meeting={meeting} isOwner={isOwner} onRetry={() => run("process")} busy={busy} />

        {isOwner && <Card className="flex flex-wrap items-center gap-2">
          {(meeting.has_audio || hasTranscript) && (
            <Button onClick={() => run("process")} loading={busy === "process"} disabled={locked || dirty}>Analyser automatiquement</Button>
          )}
          {meeting.has_audio && (
            <Button variant="secondary" onClick={() => run("transcribe")} loading={busy === "transcribe"} disabled={locked}>Transcrire</Button>
          )}
          <Button variant="success" onClick={() => run("summarize")} loading={busy === "summarize"} disabled={locked || !hasTranscript || dirty}>Résumer</Button>
          <Button variant="success" onClick={() => run("extract")} loading={busy === "extract"} disabled={locked || !hasTranscript || dirty}>Extraire tâches et décisions</Button>
          {busy === "transcribe" && <span className="text-sm text-slate-500">Transcription en cours, cela peut prendre quelques minutes…</span>}
          {!hasTranscript && !meeting.has_audio && !busy && <span className="text-sm text-slate-500">Collez le texte de la réunion ci-dessous pour lancer l'analyse.</span>}
          {dirty && !busy && <span className="text-sm text-slate-500">Enregistrez la transcription avant de lancer l'analyse.</span>}
        </Card>}
        <Alert>{error}</Alert>

        {meeting.has_audio && (
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Enregistrement</h2>
            <AudioPlayer path={meeting.audio_url} />
          </Card>
        )}

        {isOwner ? (
          <Card>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-display text-lg font-semibold">Transcription</h2>
              {dirty && <Button size="sm" onClick={saveTranscript} loading={busy === "save"} disabled={locked && busy !== "save"}>Enregistrer</Button>}
            </div>
            <Textarea rows={8} value={transcript} onChange={(e) => setTranscript(e.target.value)} readOnly={processing}
              placeholder={processing ? "La transcription apparaîtra ici dès qu'elle sera prête." : "Collez ici le texte de la réunion, ou lancez la transcription de l'audio."} />
          </Card>
        ) : hasTranscript && (
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Transcription</h2>
            <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{meeting.transcript}</p>
          </Card>
        )}

        {analysed && (
          <>
            <AiCard title="Résumé">
              {meeting.summary
                ? <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{meeting.summary}</p>
                : <p className="text-sm text-slate-500">Aucun résumé.</p>}
            </AiCard>
            <div className="grid gap-4 lg:grid-cols-2">
              <AiCard title="Sujets abordés"><ItemList items={meeting.topics} empty="Aucun sujet détecté." /></AiCard>
              <AiCard title="Points importants"><ItemList items={meeting.key_points} empty="Aucun point important détecté." /></AiCard>
            </div>
          </>
        )}

        {extractedResults && (
          <div className="grid gap-4 lg:grid-cols-2">
            <AiCard title="Décisions"><ItemList items={meeting.decisions} empty="Aucune décision détectée." /></AiCard>
            <AiCard title="Tâches"><TaskList tasks={meeting.tasks} /></AiCard>
          </div>
        )}
      </div>
    </>
  );
}
