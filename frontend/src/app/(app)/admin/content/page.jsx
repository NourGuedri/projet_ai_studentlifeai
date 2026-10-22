"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, Textarea, cx } from "@/components/ui";
import { Pager, fmtDateTime } from "@/components/admin";
import { api } from "@/lib/api";
import { LEVELS, label } from "@/lib/labels";

const TARGET = { formation: "Formation", quiz: "Quiz" };
const STATUS = { open: ["amber", "Ouvert"], resolved: ["green", "Traité"], dismissed: ["slate", "Rejeté"] };

function ReportCard({ report, onDone, onError }) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState("none");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const isOpen = report.status === "open";

  async function resolve(status) {
    const verb = action === "delete" ? "supprimer ce contenu" : action === "unpublish" ? "dépublier cette formation" : "";
    if (status === "resolved" && verb && !confirm(`Confirmer : ${verb} ?`)) return;
    setBusy(true);
    onError("");
    try {
      await api.post(`/admin/reports/${report.id}/resolve/`, { status, action: status === "dismissed" ? "none" : action, note });
      onDone(status === "resolved" ? "Signalement traité." : "Signalement rejeté.");
    } catch (err) { onError(err.message); setBusy(false); }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="blue">{TARGET[report.target_type]}</Badge>
            <p className="font-medium">{report.target_title}</p>
            {!report.target_exists && <Badge tone="red">Supprimé</Badge>}
            {report.target_exists && report.target_published === false && <Badge tone="slate">Non publié</Badge>}
          </div>
          <p className="mt-1 text-sm text-slate-600">
            <span className="font-medium">{report.reason_label}</span> · signalé par {report.reporter_name} · {fmtDateTime(report.created_at)}
            {report.owner_name && <> · auteur : {report.owner_name}</>}
          </p>
          {report.details && <p className="mt-2 whitespace-pre-line rounded-lg bg-brand-50 p-3 text-sm">{report.details}</p>}
        </div>
        <Badge tone={STATUS[report.status][0]}>{STATUS[report.status][1]}</Badge>
      </div>

      {!isOpen && (
        <p className="mt-2 text-sm text-slate-600">
          Traité par {report.handled_by_name || "un administrateur"} le {fmtDateTime(report.handled_at)}
          {report.resolution_note ? ` : ${report.resolution_note}` : "."}
        </p>
      )}

      {isOpen && !open && <Button className="mt-3" variant="secondary" size="sm" onClick={() => setOpen(true)}>Examiner</Button>}
      {isOpen && open && (
        <div className="mt-4 space-y-3 border-t border-brand-100 pt-4">
          <Field label="Action sur le contenu">
            <Select value={action} onChange={(e) => setAction(e.target.value)} disabled={!report.target_exists}>
              <option value="none">Aucune action</option>
              {report.target_type === "formation" && <option value="unpublish">Dépublier la formation</option>}
              <option value="delete">Supprimer le contenu</option>
            </Select>
          </Field>
          <Field label="Note (visible par l'auteur en cas d'action)">
            <Textarea value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button variant="success" size="sm" loading={busy} onClick={() => resolve("resolved")}>Marquer comme traité</Button>
            <Button variant="secondary" size="sm" loading={busy} onClick={() => resolve("dismissed")}>Rejeter le signalement</Button>
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>Fermer</Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function Reports() {
  const [status, setStatus] = useState("open");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try { setData(await api.get(`/admin/reports/?status=${status}&page=${page}`)); } catch (err) { setError(err.message); }
  }, [status, page]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filtrer par statut">
        {[["open", "Ouverts"], ["resolved", "Traités"], ["dismissed", "Rejetés"]].map(([v, l]) => (
          <Button key={v} size="sm" variant={status === v ? "primary" : "secondary"} aria-pressed={status === v} onClick={() => { setData(null); setPage(1); setStatus(v); }}>{l}</Button>
        ))}
      </div>
      <div className="mb-4 space-y-2"><Alert>{error}</Alert><Alert tone="success">{notice}</Alert></div>
      {!data ? <Loading /> : data.results.length === 0 ? (
        <EmptyState title={status === "open" ? "Aucun signalement en attente" : "Rien à afficher"} text="Les signalements envoyés par les utilisateurs apparaissent ici." />
      ) : (
        <>
          <ul className="space-y-3">
            {data.results.map((r) => (
              <li key={r.id}><ReportCard report={r} onError={setError} onDone={(m) => { setNotice(m); load(); }} /></li>
            ))}
          </ul>
          <Pager page={page} count={data.count} onPage={(p) => { setData(null); setPage(p); }} />
        </>
      )}
    </>
  );
}

function Formations() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [published, setPublished] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page });
    if (query) params.set("q", query);
    if (published) params.set("published", published);
    try { setData(await api.get(`/admin/formations/?${params}`)); setError(""); } catch (err) { setError(err.message); }
  }, [page, query, published]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setTimeout(() => { setPage(1); setQuery(q.trim()); }, 300); return () => clearTimeout(t); }, [q]);

  async function run(fn, message) {
    setError(""); setNotice("");
    try { await fn(); await load(); setNotice(message); } catch (err) { setError(err.message); }
  }
  const unpublish = (f) => {
    const reason = prompt(`Dépublier « ${f.title} » ? Motif (facultatif, envoyé à l'enseignant) :`);
    if (reason === null) return;
    run(() => api.post(`/admin/formations/${f.id}/unpublish/`, { reason }), "Formation dépubliée.");
  };
  const remove = (f) => confirm(`Supprimer définitivement « ${f.title} », ses leçons et ses quiz ?`) && run(() => api.del(`/admin/formations/${f.id}/`), "Formation supprimée.");

  return (
    <>
      <Card className="mb-4 grid gap-3 sm:grid-cols-2">
        <Field label="Rechercher"><Input type="search" placeholder="Titre ou enseignant" value={q} onChange={(e) => setQ(e.target.value)} /></Field>
        <Field label="Statut">
          <Select value={published} onChange={(e) => { setPage(1); setPublished(e.target.value); }}>
            <option value="">Toutes</option><option value="1">Publiées</option><option value="0">Brouillons</option>
          </Select>
        </Field>
      </Card>
      <div className="mb-4 space-y-2"><Alert>{error}</Alert><Alert tone="success">{notice}</Alert></div>
      {!data ? <Loading /> : data.results.length === 0 ? <EmptyState title="Aucune formation" /> : (
        <>
          <ul className="space-y-3">
            {data.results.map((f) => (
              <li key={f.id}>
                <Card className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{f.title}</p>
                      <Badge tone={f.is_published ? "green" : "slate"}>{f.is_published ? "Publiée" : "Brouillon"}</Badge>
                      {f.open_reports > 0 && <Badge tone="red">{f.open_reports} signalement(s)</Badge>}
                    </div>
                    <p className="text-sm text-slate-600">{f.teacher_name} · {label(LEVELS, f.level)}{f.category ? ` · ${f.category}` : ""}</p>
                    <p className="text-xs text-slate-500">{f.lessons_count} leçon(s) · {f.enrollments_count} inscrit(s)</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {f.is_published && <Link href={`/learning/formations/${f.id}`} className="inline-flex items-center rounded-lg border border-brand-200 bg-white px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50">Voir</Link>}
                    {f.is_published && <Button variant="secondary" size="sm" onClick={() => unpublish(f)}>Dépublier</Button>}
                    <Button variant="danger" size="sm" onClick={() => remove(f)}>Supprimer</Button>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <Pager page={page} count={data.count} onPage={setPage} />
        </>
      )}
    </>
  );
}

export default function AdminContentPage() {
  const [tab, setTab] = useState("reports");
  return (
    <>
      <PageHeader title="Contenus et signalements" subtitle="Traitez les signalements et modérez les formations publiées." />
      <div className="mb-6 flex gap-1 border-b border-brand-100" role="tablist">
        {[["reports", "Signalements"], ["formations", "Formations"]].map(([v, l]) => (
          <button key={v} role="tab" aria-selected={tab === v} onClick={() => setTab(v)}
            className={cx("-mb-px border-b-2 px-4 py-2 text-sm font-medium", tab === v ? "border-brand-600 text-brand-700" : "border-transparent text-slate-600 hover:text-navy-900")}>{l}</button>
        ))}
      </div>
      {tab === "reports" ? <Reports /> : <Formations />}
    </>
  );
}
