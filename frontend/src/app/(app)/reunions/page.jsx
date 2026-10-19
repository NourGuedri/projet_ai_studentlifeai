"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Alert, Badge, Card, EmptyState, Loading, PageHeader, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { MEETING_STATUS, fmtDay } from "@/lib/labels";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/meetings/").then(setMeetings).catch((err) => setError(err.message));
  }, []);

  const newButton = <Link href="/reunions/new" className={btnClass()}>Nouvelle réunion</Link>;

  return (
    <>
      <PageHeader title="Réunions" subtitle="Transcrivez vos réunions, obtenez un résumé, les décisions prises et les tâches à faire."
        actions={newButton} />
      <Alert>{error}</Alert>
      {!meetings ? (!error && <Loading />) : meetings.length === 0 ? (
        <EmptyState title="Aucune réunion" text="Ajoutez un enregistrement audio ou collez le texte d'une réunion." action={newButton} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {meetings.map((m) => {
            const [statusLabel, tone] = MEETING_STATUS[m.status] ?? [m.status, "slate"];
            return (
              <Link key={m.id} href={`/reunions/${m.id}`} className="group">
                <Card className="h-full transition-colors group-hover:border-brand-500">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="font-display text-lg font-semibold">{m.title}</h2>
                    <Badge tone={tone}>{statusLabel}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{fmtDay(m.date)}{m.audio_file && " · enregistrement audio"}</p>
                  {m.summary && <p className="mt-2 line-clamp-2 text-sm text-slate-600">{m.summary}</p>}
                  {m.tasks.length > 0 && <p className="mt-3 text-sm text-slate-500">{m.tasks.length} tâche{m.tasks.length > 1 && "s"}</p>}
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
