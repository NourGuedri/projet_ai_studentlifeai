"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AiCard, TaskList } from "@/components/AiResult";
import { Alert, Badge, Button, Card, Loading, PageHeader, Textarea, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { MEETING_STATUS, fmtDay } from "@/lib/labels";

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

  return (
    <>
      <PageHeader title={meeting.title} subtitle={fmtDay(meeting.date)}
        actions={<>
          <Link href="/reunions" className={btnClass("ghost")}>Retour</Link>
          <Button variant="danger" onClick={remove}>Supprimer</Button>
        </>} />
      <div className="-mt-3 mb-5"><Badge tone={tone}>{statusLabel}</Badge></div>

      <div className="space-y-6">
        <Card className="flex flex-wrap items-center gap-2">
          {meeting.audio_file && (
            <Button onClick={() => run("transcribe")} loading={busy === "transcribe"} disabled={!!busy}>Transcrire</Button>
          )}
          <Button variant="success" onClick={() => run("summarize")} loading={busy === "summarize"} disabled={!!busy || !hasTranscript || dirty}>Résumer</Button>
          <Button variant="success" onClick={() => run("extract")} loading={busy === "extract"} disabled={!!busy || !hasTranscript || dirty}>Extraire tâches et décisions</Button>
          {busy === "transcribe" && <span className="text-sm text-slate-500">Transcription en cours, cela peut prendre quelques minutes…</span>}
          {!hasTranscript && !busy && <span className="text-sm text-slate-500">Transcrivez l'audio ou collez le texte ci-dessous pour lancer l'analyse.</span>}
          {dirty && !busy && <span className="text-sm text-slate-500">Enregistrez la transcription avant de lancer l'analyse.</span>}
        </Card>
        <Alert>{error}</Alert>

        {meeting.audio_file && (
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Enregistrement</h2>
            <audio controls src={meeting.audio_file} className="w-full" />
          </Card>
        )}

        <Card>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-display text-lg font-semibold">Transcription</h2>
            {dirty && <Button size="sm" onClick={saveTranscript} loading={busy === "save"} disabled={!!busy && busy !== "save"}>Enregistrer</Button>}
          </div>
          <Textarea rows={8} value={transcript} onChange={(e) => setTranscript(e.target.value)}
            placeholder="Collez ici le texte de la réunion, ou lancez la transcription de l'audio." />
        </Card>

        {meeting.summary && (
          <AiCard title="Résumé">
            <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{meeting.summary}</p>
          </AiCard>
        )}

        {(meeting.decisions.length > 0 || meeting.tasks.length > 0 || extracted) && (
          <div className="grid gap-4 lg:grid-cols-2">
            <AiCard title="Décisions">
              {meeting.decisions.length === 0 ? <p className="text-sm text-slate-500">Aucune décision détectée.</p> : (
                <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-700">
                  {meeting.decisions.map((d, i) => <li key={i}>{d}</li>)}
                </ul>
              )}
            </AiCard>
            <AiCard title="Tâches"><TaskList tasks={meeting.tasks} /></AiCard>
          </div>
        )}
      </div>
    </>
  );
}
