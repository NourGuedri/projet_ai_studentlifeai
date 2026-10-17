"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(form.email, form.password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">Connexion</h1>
        <p className="mt-1 text-sm text-slate-600">Retrouvez votre profil, vos cours et vos quiz.</p>
      </div>
      <Alert>{error}</Alert>
      <Field label="Adresse e-mail">
        <Input type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
      </Field>
      <Field label="Mot de passe">
        <Input type="password" required autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
      </Field>
      <p className="-mt-2 text-right text-sm">
        <Link href="/forgot-password" className="font-medium text-brand-700 underline">Mot de passe oublié ?</Link>
      </p>
      <Button type="submit" loading={busy} className="w-full">Se connecter</Button>
      <p className="text-center text-sm text-slate-600">
        Pas encore de compte ? <Link href="/register" className="font-medium text-brand-700 underline">Créer un compte</Link>
      </p>
    </form>
  );
}
