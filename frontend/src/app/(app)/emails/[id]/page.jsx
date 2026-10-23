"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AiCard, TaskList } from "@/components/AiResult";
import { Alert, Badge, Button, Card, Loading, PageHeader, Textarea, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/labels";

const ACTIONS = [
  ["classify", "Analyser l'importance"],
  ["summarize", "Résumer"],
  ["extract-tasks", "Extraire les tâches"],
  ["draft-reply", "Proposer une réponse"],
];

export default function EmailDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [email, setEmail] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [notFound, setNotFound] = useState("");
  const [extracted, setExtracted] = useState(false);

  function show(m) {
    setEmail(m);
    setDraft(m.draft_reply);
  }

  useEffect(() => {
    api.get(`/mails/${id}/`).then(show).catch((err) => setNotFound(err.message));
  }, [id]);

  async function run(action) {
    setBusy(action);
    setError("");
    setNotice("");
    try {
      const updated = await api.post(`/mails/${id}/${action}/`);
      setEmail(updated);
      // Keep unsaved edits of the draft unless a new draft was requested.
      if (action === "draft-reply") setDraft(updated.draft_reply);
      if (action === "extract-tasks") setExtracted(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function saveDraft() {
    setBusy("save");
    setError("");
    try {
      show(await api.patch(`/mails/${id}/`, { draft_reply: draft }));
      setNotice("Brouillon enregistré.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(draft);
      setNotice("Brouillon copié. Collez-le dans votre messagerie pour l'envoyer.");
    } catch {
      setError("Impossible de copier automatiquement. Sélectionnez le texte et copiez-le à la main.");
    }
  }

  async function remove() {
    if (!confirm("Supprimer cet e-mail ?")) return;
    await api.del(`/mails/${id}/`);
    router.replace("/emails");
  }

  if (notFound) return <Alert>{notFound}</Alert>;
  if (!email) return <Loading />;

  return (
    <>
      <PageHeader title={email.subject || "(sans objet)"}
        subtitle={`${email.sender || "Expéditeur inconnu"}${email.received_at ? ` · ${fmtDateTime(email.received_at)}` : ""}`}
        actions={<>
          <Link href="/emails" className={btnClass("ghost")}>Retour</Link>
          <Button variant="danger" onClick={remove}>Supprimer</Button>
        </>} />

      <div className="space-y-6">
        <Card className="flex flex-wrap gap-2">
          {ACTIONS.map(([action, text]) => (
            <Button key={action} variant="success" onClick={() => run(action)} loading={busy === action} disabled={!!busy}>{text}</Button>
          ))}
        </Card>
        <Alert>{error}</Alert>
        <Alert tone="success">{notice}</Alert>

        <Card>
          <h2 className="mb-3 font-display text-lg font-semibold">Contenu</h2>
          <p className="max-h-80 overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-slate-700">{email.body}</p>
        </Card>

        {email.is_important !== null && (
          <AiCard title="Importance">
            <div className="flex flex-wrap items-center gap-3">
              {email.is_important ? <Badge tone="red">Important</Badge> : <Badge tone="slate">Non important</Badge>}
              <p className="text-sm text-slate-700">{email.importance_reason}</p>
            </div>
          </AiCard>
        )}

        {email.summary && (
          <AiCard title="Résumé">
            <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{email.summary}</p>
          </AiCard>
        )}

        {(email.tasks.length > 0 || extracted) && (
          <AiCard title="Tâches"><TaskList tasks={email.tasks} /></AiCard>
        )}

        {(email.draft_reply || draft) && (
          <AiCard title="Brouillon de réponse">
            <Alert tone="info">Ce n'est qu'un brouillon : rien n'est envoyé automatiquement. Relisez-le, modifiez-le, puis copiez-le dans votre messagerie.</Alert>
            <Textarea rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} className="mt-3" />
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={copyDraft} disabled={!draft.trim()}>Copier</Button>
              <Button variant="secondary" onClick={saveDraft} loading={busy === "save"} disabled={draft === email.draft_reply || (!!busy && busy !== "save")}>Enregistrer</Button>
            </div>
          </AiCard>
        )}
      </div>
    </>
  );
}
