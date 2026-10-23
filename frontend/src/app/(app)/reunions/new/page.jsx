"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Card, Field, Input, PageHeader, ProgressBar, Textarea, btnClass, cx } from "@/components/ui";
import { api } from "@/lib/api";

const MAX_AUDIO_MB = 25;
const AUDIO_EXT = [".mp3", ".wav", ".m4a"];
const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time

export default function NewMeetingPage() {
  const router = useRouter();
  const [mode, setMode] = useState("text");
  const [form, setForm] = useState({ title: "", date: today(), transcript: "" });
  const [file, setFile] = useState(null);
  const [consent, setConsent] = useState(false);
  const [progress, setProgress] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  function pickFile(e) {
    const picked = e.target.files[0] ?? null;
    setError("");
    if (picked && !AUDIO_EXT.some((ext) => picked.name.toLowerCase().endsWith(ext))) {
      setError("Format non pris en charge. Utilisez un fichier MP3, WAV ou M4A.");
      e.target.value = "";
      return setFile(null);
    }
    if (picked && picked.size > MAX_AUDIO_MB * 1024 * 1024) {
      setError(`Fichier trop volumineux (${MAX_AUDIO_MB} Mo maximum).`);
      e.target.value = "";
      return setFile(null);
    }
    setFile(picked);
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (mode === "audio" && !file) return setError("Choisissez un fichier audio.");
    if (mode === "audio" && !consent) return setError("Confirmez le consentement des participants avant d'envoyer l'enregistrement.");
    if (mode === "text" && !form.transcript.trim()) return setError("Collez le texte de la réunion.");
    setBusy(true);
    try {
      let meeting;
      if (mode === "audio") {
        const data = new FormData();
        data.append("title", form.title);
        data.append("date", form.date);
        data.append("audio_file", file);
        data.append("consent_confirmed", "true");
        setProgress(0);
        meeting = await api.upload("/meetings/", data, setProgress);
      } else {
        meeting = await api.post("/meetings/", form);
      }
      router.push(`/reunions/${meeting.id}`);
    } catch (err) {
      setError(err.message);
      setProgress(null);
      setBusy(false);
    }
  }

  const tab = (value, text) => (
    <button type="button" onClick={() => { setMode(value); setError(""); }}
      className={cx("rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
        mode === value ? "border-brand-600 bg-brand-600 text-white" : "border-brand-200 bg-white text-brand-700 hover:bg-brand-50")}>
      {text}
    </button>
  );

  return (
    <>
      <PageHeader title="Nouvelle réunion" subtitle="Envoyez l'enregistrement audio ou collez directement le texte de la réunion." />
      <Card>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Alert>{error}</Alert></div>
          <Field label="Titre"><Input required value={form.title} onChange={set("title")} placeholder="Ex. : Point d'équipe PFE" /></Field>
          <Field label="Date"><Input required type="date" value={form.date} onChange={set("date")} /></Field>

          <div className="flex flex-wrap gap-2 sm:col-span-2">
            {tab("text", "Coller le texte")}
            {tab("audio", "Envoyer un audio")}
          </div>

          {mode === "audio" ? (
            <div className="space-y-4 sm:col-span-2">
              <Field label="Enregistrement (MP3, WAV, M4A)" hint={`${MAX_AUDIO_MB} Mo maximum.`}>
                <input type="file" accept={AUDIO_EXT.join(",")} onChange={pickFile}
                  className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700" />
              </Field>
              <label className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 accent-brand-600" />
                <span>Je confirme que tous les participants ont été informés et ont accepté que cette réunion soit enregistrée et transcrite.</span>
              </label>
              {progress !== null && <ProgressBar value={progress} tone="blue" />}
            </div>
          ) : (
            <Field label="Texte de la réunion" hint="Notes, compte rendu ou transcription existante." className="sm:col-span-2">
              <Textarea rows={10} value={form.transcript} onChange={set("transcript")} />
            </Field>
          )}

          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" variant="success" loading={busy}>Créer la réunion</Button>
            <Link href="/reunions" className={btnClass("ghost")}>Annuler</Link>
          </div>
        </form>
      </Card>
    </>
  );
}
