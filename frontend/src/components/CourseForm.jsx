"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { Alert, Button, Card, Field, Input, Textarea } from "./ui";

/** Create (with optional file) or edit (text only) a course. */
export default function CourseForm({ course, subjects = [], onSaved, onCancel }) {
  const file = useRef(null);
  const [form, setForm] = useState({
    title: course?.title ?? "", subject: course?.subject ?? "", description: course?.description ?? "", content: course?.content ?? "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = new FormData();
      Object.entries(form).forEach(([k, v]) => data.append(k, v));
      if (!course && file.current?.files[0]) data.append("file", file.current.files[0]);
      const saved = course ? await api.form(`/learning/courses/${course.id}/`, data, "PATCH") : await api.form("/learning/courses/", data);
      await onSaved(saved);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Alert>{error}</Alert></div>
        <Field label="Titre du cours"><Input required value={form.title} onChange={set("title")} /></Field>
        <Field label="Matière">
          <Input list="subjects" value={form.subject} onChange={set("subject")} placeholder="Ex. : Réseaux" />
          <datalist id="subjects">{subjects.map((s) => <option key={s} value={s} />)}</datalist>
        </Field>
        <Field label="Description" className="sm:col-span-2"><Input value={form.description} onChange={set("description")} /></Field>
        {!course && (
          <Field label="Fichier du cours (PDF, DOCX, TXT)" hint="Son texte servira à générer des quiz." className="sm:col-span-2">
            <input ref={file} type="file" accept=".pdf,.docx,.txt,.md" className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700" />
          </Field>
        )}
        <Field label="Contenu du cours" hint="Collez votre cours ici si vous n'envoyez pas de fichier." className="sm:col-span-2">
          <Textarea rows={6} value={form.content} onChange={set("content")} />
        </Field>
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" variant="success" loading={busy}>{course ? "Enregistrer" : "Ajouter le cours"}</Button>
          <Button variant="ghost" onClick={onCancel}>Annuler</Button>
        </div>
      </form>
    </Card>
  );
}
