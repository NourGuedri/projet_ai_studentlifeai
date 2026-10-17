"use client";
import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api.post("/auth/password-reset/", { email });
      setMessage(data.detail);
    } catch (err) {
      setError(err.status === 429 ? "Trop de demandes. Réessayez dans une heure." : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">Mot de passe oublié</h1>
        <p className="mt-1 text-sm text-slate-600">Saisissez votre adresse e-mail : nous vous envoyons un lien pour en choisir un nouveau.</p>
      </div>
      <Alert>{error}</Alert>
      {message ? (
        <Alert tone="success">{message}</Alert>
      ) : (
        <>
          <Field label="Adresse e-mail">
            <Input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" loading={busy} className="w-full">Envoyer le lien</Button>
        </>
      )}
      <p className="text-center text-sm">
        <Link href="/login" className="font-medium text-brand-700 underline">Retour à la connexion</Link>
      </p>
    </form>
  );
}
