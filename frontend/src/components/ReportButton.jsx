"use client";
import { useState } from "react";
import { Alert, Button, Card, Field, Select, Textarea } from "./ui";
import { api } from "@/lib/api";

const REASONS = [
  ["inappropriate", "Contenu inapproprié"],
  ["copyright", "Droits d'auteur"],
  ["incorrect", "Informations erronées"],
  ["spam", "Spam ou publicité"],
  ["other", "Autre"],
];

/** "Signaler" button + small form. targetType: "formation" | "quiz". */
export default function ReportButton({ targetType, targetId, size = "md" }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("inappropriate");
  const [details, setDetails] = useState("");
  const [state, setState] = useState({ busy: false, error: "", done: false });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: "", done: false });
    try {
      await api.post("/reports/", { target_type: targetType, target_id: targetId, reason, details });
      setState({ busy: false, error: "", done: true });
    } catch (err) {
      setState({ busy: false, error: err.message, done: false });
    }
  }

  if (state.done) return <span className="text-sm text-leaf-700" role="status">Signalement envoyé, merci.</span>;
  return (
    <>
      <Button variant="ghost" size={size === "sm" ? "sm" : "md"} onClick={() => setOpen(true)}>Signaler</Button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Signaler ce contenu">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setOpen(false)} />
          <Card className="relative w-full max-w-md">
            <form onSubmit={submit} className="space-y-4">
              <h2 className="text-lg font-semibold">Signaler ce contenu</h2>
              <Field label="Motif">
                <Select value={reason} onChange={(e) => setReason(e.target.value)}>
                  {REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </Field>
              <Field label="Précisions (facultatif)">
                <Textarea value={details} maxLength={1000} onChange={(e) => setDetails(e.target.value)} />
              </Field>
              <Alert>{state.error}</Alert>
              <div className="flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setOpen(false)}>Annuler</Button>
                <Button type="submit" loading={state.busy}>Envoyer</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </>
  );
}
