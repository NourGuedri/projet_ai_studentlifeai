"use client";
import { useState } from "react";
import { Alert, Button, Card, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";

const AUDIENCES = [["all", "Tous les utilisateurs"], ["student", "Étudiants"], ["teacher", "Enseignants"], ["admin", "Administrateurs"]];

export default function AnnouncementsPage() {
  const [form, setForm] = useState({ title: "", message: "", audience: "all", link: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    const who = AUDIENCES.find(([v]) => v === form.audience)[1].toLowerCase();
    if (!confirm(`Envoyer cette annonce à : ${who} ?`)) return;
    setBusy(true); setError(""); setSent(null);
    try {
      const res = await api.post("/admin/announcements/", form);
      setSent(res.sent);
      setForm({ title: "", message: "", audience: "all", link: "" });
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Annonces" subtitle="Envoyez une notification à tous les utilisateurs ou à un rôle précis (maintenance, nouveauté, rappel)." />
      <Card className="max-w-2xl">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Destinataires">
            <Select value={form.audience} onChange={set("audience")}>
              {AUDIENCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Titre"><Input required maxLength={150} value={form.title} onChange={set("title")} /></Field>
          <Field label="Message"><Textarea rows={4} maxLength={1000} value={form.message} onChange={set("message")} /></Field>
          <Field label="Lien interne (facultatif)" hint="Chemin dans l'application, par exemple /learning/formations."><Input placeholder="/dashboard" value={form.link} onChange={set("link")} /></Field>
          <Alert>{error}</Alert>
          {sent !== null && <Alert tone="success">Annonce envoyée à {sent} utilisateur(s).</Alert>}
          <Button type="submit" loading={busy}>Envoyer l'annonce</Button>
        </form>
      </Card>
    </>
  );
}
