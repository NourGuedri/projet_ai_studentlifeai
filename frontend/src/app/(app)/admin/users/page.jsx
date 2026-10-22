"use client";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select } from "@/components/ui";
import { Pager, ROLE_LABELS, ROLE_TONES } from "@/components/admin";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/labels";

function NewUserForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({ email: "", password: "", first_name: "", last_name: "", role: "student" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try { await api.post("/admin/users/", form); onCreated(); } catch (err) { setError(err.message); setBusy(false); }
  }
  return (
    <Card className="mb-6">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Prénom"><Input value={form.first_name} onChange={set("first_name")} /></Field>
        <Field label="Nom"><Input value={form.last_name} onChange={set("last_name")} /></Field>
        <Field label="E-mail"><Input type="email" required value={form.email} onChange={set("email")} /></Field>
        <Field label="Mot de passe provisoire" hint="8 caractères minimum, pas trop courant."><Input type="password" required autoComplete="new-password" value={form.password} onChange={set("password")} /></Field>
        <Field label="Rôle">
          <Select value={form.role} onChange={set("role")}>
            {Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <div className="sm:col-span-2"><Alert>{error}</Alert></div>
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" variant="success" loading={busy}>Créer le compte</Button>
          <Button variant="secondary" onClick={onCancel}>Annuler</Button>
        </div>
      </form>
    </Card>
  );
}

export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [active, setActive] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page });
    if (query) params.set("q", query);
    if (role) params.set("role", role);
    if (active) params.set("active", active);
    try { setData(await api.get(`/admin/users/?${params}`)); setError(""); } catch (err) { setError(err.message); }
  }, [page, query, role, active]);
  useEffect(() => { load(); }, [load]);

  // Wait for the admin to stop typing before searching.
  useEffect(() => { const t = setTimeout(() => { setPage(1); setQuery(q.trim()); }, 300); return () => clearTimeout(t); }, [q]);

  async function run(fn, message) {
    setError(""); setNotice("");
    try { await fn(); await load(); if (message) setNotice(message); } catch (err) { setError(err.message); }
  }
  const update = (u, body, message) => run(() => api.patch(`/admin/users/${u.id}/`, body), message);
  const toggle = (u) => {
    if (u.is_active && !confirm(`Désactiver le compte de ${u.email} ? Cette personne ne pourra plus se connecter.`)) return;
    update(u, { is_active: !u.is_active }, u.is_active ? "Compte désactivé." : "Compte réactivé.");
  };
  const remove = (u) => {
    if (!confirm(`Supprimer définitivement ${u.email} ? Son profil, ses cours, ses résultats et ses formations seront supprimés.`)) return;
    run(() => api.del(`/admin/users/${u.id}/`), "Compte supprimé.");
  };

  return (
    <>
      <PageHeader title="Utilisateurs" subtitle="Gérez les comptes, les rôles et l'accès à la plateforme."
        actions={<Button onClick={() => setCreating(true)}>Nouveau compte</Button>} />
      {creating && <NewUserForm onCancel={() => setCreating(false)} onCreated={() => { setCreating(false); setNotice("Compte créé."); load(); }} />}

      <Card className="mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Rechercher"><Input type="search" placeholder="Nom ou e-mail" value={q} onChange={(e) => setQ(e.target.value)} /></Field>
        <Field label="Rôle">
          <Select value={role} onChange={(e) => { setPage(1); setRole(e.target.value); }}>
            <option value="">Tous les rôles</option>
            {Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Statut">
          <Select value={active} onChange={(e) => { setPage(1); setActive(e.target.value); }}>
            <option value="">Tous</option><option value="1">Actifs</option><option value="0">Désactivés</option>
          </Select>
        </Field>
      </Card>

      <div className="mb-4 space-y-2"><Alert>{error}</Alert><Alert tone="success">{notice}</Alert></div>

      {!data ? <Loading /> : data.results.length === 0 ? (
        <EmptyState title="Aucun utilisateur" text="Modifiez la recherche ou les filtres." />
      ) : (
        <>
          <ul className="space-y-3">
            {data.results.map((u) => {
              const isMe = u.id === me.id;
              return (
                <li key={u.id}>
                  <Card className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-medium">{[u.first_name, u.last_name].filter(Boolean).join(" ") || u.email}</p>
                        <Badge tone={ROLE_TONES[u.role]}>{ROLE_LABELS[u.role]}</Badge>
                        {!u.is_active && <Badge tone="red">Désactivé</Badge>}
                        {isMe && <Badge tone="slate">Vous</Badge>}
                      </div>
                      <p className="truncate text-sm text-slate-600">{u.email}</p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        Inscrit le {fmtDate(u.date_joined)}{u.last_login ? `, dernière connexion ${fmtDate(u.last_login)}` : ", jamais connecté"}
                        {u.role === "teacher" ? ` · ${u.formations_count} formation(s)` : ` · ${u.enrollments_count} inscription(s), ${u.attempts_count} quiz passé(s)`}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Select aria-label={`Rôle de ${u.email}`} className="w-auto" value={u.role} disabled={isMe}
                        onChange={(e) => update(u, { role: e.target.value }, "Rôle modifié.")}>
                        {Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </Select>
                      <Button variant="secondary" size="sm" disabled={isMe} onClick={() => toggle(u)}>{u.is_active ? "Désactiver" : "Réactiver"}</Button>
                      <Button variant="danger" size="sm" disabled={isMe} onClick={() => remove(u)}>Supprimer</Button>
                    </div>
                  </Card>
                </li>
              );
            })}
          </ul>
          <Pager page={page} count={data.count} onPage={setPage} />
        </>
      )}
    </>
  );
}
