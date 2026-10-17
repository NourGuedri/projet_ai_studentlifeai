"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Field, Input, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", password: "", role: "student" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await register(form);
      router.replace("/dashboard");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">Créer un compte</h1>
        <p className="mt-1 text-sm text-slate-600">Cela prend moins d'une minute.</p>
      </div>
      <Alert>{error}</Alert>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Prénom"><Input required value={form.first_name} onChange={set("first_name")} autoComplete="given-name" /></Field>
        <Field label="Nom"><Input required value={form.last_name} onChange={set("last_name")} autoComplete="family-name" /></Field>
      </div>
      <Field label="Adresse e-mail">
        <Input type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
      </Field>
      <Field label="Mot de passe" hint="8 caractères minimum, pas uniquement des chiffres.">
        <Input type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set("password")} />
      </Field>
      <Field label="Je suis">
        <Select value={form.role} onChange={set("role")}>
          <option value="student">Étudiant</option>
          <option value="teacher">Enseignant / formateur</option>
        </Select>
      </Field>
      <Button type="submit" loading={busy} className="w-full">Créer mon compte</Button>
      <p className="text-center text-sm text-slate-600">
        Déjà inscrit ? <Link href="/login" className="font-medium text-brand-700 underline">Se connecter</Link>
      </p>
    </form>
  );
}
