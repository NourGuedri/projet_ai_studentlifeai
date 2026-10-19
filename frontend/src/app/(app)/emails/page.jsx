"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Textarea, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/labels";

// Current local date and time in the "YYYY-MM-DDTHH:MM" format of <input type="datetime-local">.
function nowLocal() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function EmailForm({ onSaved, onCancel }) {
  const [form, setForm] = useState(() => ({ sender: "", subject: "", received_at: nowLocal(), body: "" }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const received = form.received_at ? new Date(form.received_at).toISOString() : null;
      await onSaved(await api.post("/mails/", { ...form, received_at: received }));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Alert>{error}</Alert></div>
        <Field label="Expéditeur"><Input value={form.sender} onChange={set("sender")} placeholder="Ex. : scolarite@univ.tn" /></Field>
        <Field label="Reçu le"><Input type="datetime-local" value={form.received_at} onChange={set("received_at")} /></Field>
        <Field label="Objet" className="sm:col-span-2"><Input value={form.subject} onChange={set("subject")} /></Field>
        <Field label="Contenu de l'e-mail" hint="Copiez-collez le texte de l'e-mail depuis votre messagerie." className="sm:col-span-2">
          <Textarea required rows={8} value={form.body} onChange={set("body")} />
        </Field>
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" variant="success" loading={busy}>Ajouter l'e-mail</Button>
          <Button variant="ghost" onClick={onCancel}>Annuler</Button>
        </div>
      </form>
    </Card>
  );
}

function ImportanceBadge({ value }) {
  if (value === true) return <Badge tone="red">Important</Badge>;
  if (value === false) return <Badge tone="slate">Non important</Badge>;
  return <Badge tone="blue">Non analysé</Badge>;
}

export default function EmailsPage() {
  const [emails, setEmails] = useState(null);
  const [importantOnly, setImportantOnly] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setEmails(await api.get(`/mails/${importantOnly ? "?important=true" : ""}`));
    } catch (err) { setError(err.message); }
  }, [importantOnly]);
  useEffect(() => { load(); }, [load]);

  const filter = (value, text) => (
    <button onClick={() => setImportantOnly(value)}
      className={cx("rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
        importantOnly === value ? "border-brand-600 bg-brand-600 text-white" : "border-brand-200 bg-white text-brand-700 hover:bg-brand-50")}>
      {text}
    </button>
  );

  return (
    <>
      <PageHeader title="E-mails" subtitle="Collez vos e-mails pour repérer les importants, les résumer, extraire les tâches et préparer une réponse."
        actions={!adding && <Button onClick={() => setAdding(true)}>Ajouter un e-mail</Button>} />
      {adding && (
        <div className="mb-6">
          <EmailForm onCancel={() => setAdding(false)} onSaved={async () => { setAdding(false); await load(); }} />
        </div>
      )}

      <div className="mb-5 flex flex-wrap gap-2">
        {filter(false, "Tous")}
        {filter(true, "Importants")}
      </div>
      <Alert>{error}</Alert>

      {!emails ? (!error && <Loading />) : emails.length === 0 ? (
        <EmptyState title={importantOnly ? "Aucun e-mail important" : "Aucun e-mail"}
          text={importantOnly ? "Analysez l'importance de vos e-mails pour les retrouver ici." : "Ajoutez un e-mail en copiant-collant son contenu."} />
      ) : (
        <ul className="space-y-3">
          {emails.map((m) => (
            <li key={m.id}>
              <Link href={`/emails/${m.id}`} className="group block">
                <Card className="transition-colors group-hover:border-brand-500">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{m.subject || "(sans objet)"}</p>
                      <p className="truncate text-sm text-slate-500">{m.sender || "Expéditeur inconnu"}{m.received_at && ` · ${fmtDateTime(m.received_at)}`}</p>
                    </div>
                    <ImportanceBadge value={m.is_important} />
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-slate-600">{m.summary || m.body}</p>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
