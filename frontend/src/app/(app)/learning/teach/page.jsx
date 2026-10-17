"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LEVELS } from "@/lib/labels";

export default function TeachPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [formations, setFormations] = useState(null);
  const [form, setForm] = useState({ title: "", description: "", category: "", level: "beginner" });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const isTeacher = user.role === "teacher" || user.role === "admin";
  useEffect(() => {
    if (!isTeacher) { router.replace("/dashboard"); return; }
    api.get("/learning/formations/?mine=1").then(setFormations);
  }, [isTeacher, router]);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api.post("/learning/formations/", form);
      router.push(`/learning/formations/${created.id}`);
    } catch (err) { setError(err.message); setBusy(false); }
  }

  if (!isTeacher || !formations) return <Loading />;

  return (
    <>
      <PageHeader title="Mes formations" subtitle="Créez une formation, ajoutez des leçons et des quiz, puis publiez-la pour les étudiants."
        actions={!adding && <Button onClick={() => setAdding(true)}>Nouvelle formation</Button>} />
      {adding && (
        <Card className="mb-6">
          <form onSubmit={create} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><Alert>{error}</Alert></div>
            <Field label="Titre" className="sm:col-span-2"><Input required value={form.title} onChange={set("title")} /></Field>
            <Field label="Catégorie"><Input value={form.category} onChange={set("category")} placeholder="Ex. : Développement web" /></Field>
            <Field label="Niveau"><Select value={form.level} onChange={set("level")}>{LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
            <Field label="Description" className="sm:col-span-2"><Textarea rows={4} value={form.description} onChange={set("description")} /></Field>
            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit" variant="success" loading={busy}>Créer la formation</Button>
              <Button variant="ghost" onClick={() => setAdding(false)}>Annuler</Button>
            </div>
          </form>
        </Card>
      )}

      {formations.length === 0 && !adding ? (
        <EmptyState title="Aucune formation" text="Votre première formation sera un brouillon jusqu'à sa publication." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {formations.map((f) => (
            <Link key={f.id} href={`/learning/formations/${f.id}`} className="group">
              <Card className="h-full transition-colors group-hover:border-brand-500">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-display text-lg font-semibold">{f.title}</h2>
                  <Badge tone={f.is_published ? "green" : "slate"}>{f.is_published ? "Publiée" : "Brouillon"}</Badge>
                </div>
                <p className="mt-2 text-sm text-slate-600">{f.lessons_count} leçon(s), {f.enrollments_count} inscrit(s)</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
