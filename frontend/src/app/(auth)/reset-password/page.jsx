"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, Button, Field, Input, Loading } from "@/components/ui";
import { api } from "@/lib/api";

function ResetForm() {
  const params = useSearchParams();
  const uid = params.get("uid");
  const token = params.get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (password !== confirm) return setError("Les deux mots de passe ne correspondent pas.");
    setBusy(true);
    try {
      await api.post("/auth/password-reset/confirm/", { uid, token, new_password: password });
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!uid || !token) {
    return (
      <div className="space-y-4">
        <Alert>Ce lien est incomplet. Utilisez le lien reçu par e-mail ou demandez-en un nouveau.</Alert>
        <Link href="/forgot-password" className="text-sm font-medium text-brand-700 underline">Demander un nouveau lien</Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">Nouveau mot de passe</h1>
        <p className="mt-1 text-sm text-slate-600">Choisissez un mot de passe que vous n'utilisez nulle part ailleurs.</p>
      </div>
      <Alert>{error}</Alert>
      {done ? (
        <>
          <Alert tone="success">Mot de passe modifié. Vous pouvez vous connecter.</Alert>
          <Link href="/login" className="block rounded-lg bg-brand-600 px-4 py-2.5 text-center text-sm font-medium text-white hover:bg-brand-700">Se connecter</Link>
        </>
      ) : (
        <>
          <Field label="Nouveau mot de passe" hint="8 caractères minimum, pas uniquement des chiffres.">
            <Input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Confirmer le mot de passe">
            <Input type="password" required minLength={8} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" loading={busy} className="w-full">Enregistrer le mot de passe</Button>
        </>
      )}
    </form>
  );
}

export default function ResetPasswordPage() {
  return <Suspense fallback={<Loading />}><ResetForm /></Suspense>;
}
