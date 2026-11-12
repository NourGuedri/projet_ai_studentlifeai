"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Alert, Badge, Card, EmptyState, Loading, PageHeader, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { MEETING_STATUS, fmtDateTime, fmtDay } from "@/lib/labels";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/meetings/").then(setMeetings).catch((err) => setError(err.message));
  }, []);

  const newButton = <Link href="/reunions/new" className={btnClass()}>Nouvelle réunion</Link>;

  return (
    <>
      <PageHeader title="Réunions" subtitle="Planifiez vos appels vidéo, transcrivez vos réunions, obtenez un résumé, les décisions prises et les tâches à faire."
        actions={newButton} />
      <Alert>{error}</Alert>
      {!meetings ? (!error && <Loading />) : meetings.length === 0 ? (
        <EmptyState title="Aucune réunion" text="Ajoutez un enregistrement audio, collez le texte d'une réunion ou planifiez un appel vidéo." action={newButton} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {meetings.map((m) => {
            const [statusLabel, tone] = MEETING_STATUS[m.status] ?? [m.status, "slate"];
            return (
              // The whole card links to the meeting; "Rejoindre" sits above that link (no <a> inside <a>).
              <Card key={m.id} className="group relative h-full transition-colors hover:border-brand-500">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-display text-lg font-semibold">
                    <Link href={`/reunions/${m.id}`} className="after:absolute after:inset-0 after:content-['']">{m.title}</Link>
                  </h2>
                  <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                    {!m.is_owner && <Badge tone="amber">Invité</Badge>}
                    {m.is_call && <Badge tone="blue">Appel vidéo</Badge>}
                    <Badge tone={tone}>{statusLabel}</Badge>
                  </div>
                </div>
                <p className="mt-1 text-sm text-slate-500">
                  {m.scheduled_at ? fmtDateTime(m.scheduled_at) : fmtDay(m.date)}
                  {m.audio_file && " · enregistrement audio"}
                  {!m.is_owner && ` · organisé par ${m.owner_name}`}
                </p>
                {m.summary && <p className="mt-2 line-clamp-2 text-sm text-slate-600">{m.summary}</p>}
                {m.tasks.length > 0 && <p className="mt-3 text-sm text-slate-500">{m.tasks.length} tâche{m.tasks.length > 1 && "s"}</p>}
                {m.call_url && (
                  <a href={m.call_url} target="_blank" rel="noopener noreferrer" className={btnClass("success", "sm", "relative z-10 mt-3")}>
                    Rejoindre
                  </a>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
