"use client";
import { useCallback, useEffect, useState } from "react";
import SectionEditor from "@/components/SectionEditor";
import { Alert, Button, Card, Field, Input, Loading, PageHeader, Textarea, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { EXP_TYPES, LANG_LEVELS, LEVELS, fmtDate, label } from "@/lib/labels";

const join = (...parts) => parts.filter(Boolean).join(", ");
const years = (a, b) => (a && b ? `${a} – ${b}` : a || b || "");

const SECTIONS = {
  educations: {
    label: "Formation", addLabel: "Ajouter une formation", endpoint: "educations",
    emptyTitle: "Aucune formation", emptyText: "Ajoutez vos diplômes et cursus.",
    title: (i) => i.school, subtitle: (i) => join(i.degree, i.field, years(i.start_year, i.end_year)),
    fields: [
      { name: "school", label: "Établissement", required: true, wide: true },
      { name: "degree", label: "Diplôme" }, { name: "field", label: "Spécialité" },
      { name: "start_year", label: "Année de début", type: "number" }, { name: "end_year", label: "Année de fin", type: "number" },
      { name: "description", label: "Description", type: "textarea", wide: true },
    ],
  },
  skills: {
    label: "Compétences", addLabel: "Ajouter une compétence", endpoint: "skills",
    emptyTitle: "Aucune compétence", emptyText: "Listez vos langages, outils et savoir-faire.",
    title: (i) => i.name, subtitle: (i) => label(LEVELS, i.level),
    fields: [{ name: "name", label: "Compétence", required: true }, { name: "level", label: "Niveau", options: LEVELS }],
  },
  projects: {
    label: "Projets", addLabel: "Ajouter un projet", endpoint: "projects",
    emptyTitle: "Aucun projet", emptyText: "Vos projets de cours ou personnels comptent.",
    title: (i) => i.title, subtitle: (i) => i.tech_stack,
    fields: [
      { name: "title", label: "Titre", required: true, wide: true }, { name: "tech_stack", label: "Technologies", wide: true },
      { name: "url", label: "Lien", type: "url", wide: true }, { name: "description", label: "Description", type: "textarea", wide: true },
    ],
  },
  experiences: {
    label: "Expériences", addLabel: "Ajouter une expérience", endpoint: "experiences",
    emptyTitle: "Aucune expérience", emptyText: "Stages, emplois, missions freelance.",
    title: (i) => i.position,
    subtitle: (i) => join(i.company, label(EXP_TYPES, i.type), i.start_date && `${fmtDate(i.start_date)} – ${i.end_date ? fmtDate(i.end_date) : "en cours"}`),
    fields: [
      { name: "position", label: "Poste", required: true }, { name: "company", label: "Entreprise" },
      { name: "type", label: "Type", options: EXP_TYPES },
      { name: "start_date", label: "Début", type: "date" }, { name: "end_date", label: "Fin", type: "date", hint: "Laissez vide si en cours." },
      { name: "description", label: "Missions", type: "textarea", wide: true },
    ],
  },
  certifications: {
    label: "Certifications", addLabel: "Ajouter une certification", endpoint: "certifications",
    emptyTitle: "Aucune certification", emptyText: "Ajoutez vos certificats pour valoriser vos compétences.",
    title: (i) => i.name, subtitle: (i) => join(i.issuer, i.issue_date && fmtDate(i.issue_date)),
    fields: [
      { name: "name", label: "Intitulé", required: true, wide: true }, { name: "issuer", label: "Organisme" },
      { name: "issue_date", label: "Date d'obtention", type: "date" }, { name: "credential_url", label: "Lien de vérification", type: "url", wide: true },
    ],
  },
  languages: {
    label: "Langues", addLabel: "Ajouter une langue", endpoint: "languages",
    emptyTitle: "Aucune langue", emptyText: "Indiquez les langues que vous parlez.",
    title: (i) => i.name, subtitle: (i) => label(LANG_LEVELS, i.level),
    fields: [{ name: "name", label: "Langue", required: true }, { name: "level", label: "Niveau", options: LANG_LEVELS }],
  },
};
const TABS = [["about", "À propos"], ...Object.entries(SECTIONS).map(([k, v]) => [k, v.label])];

function AboutForm({ profile, onSaved }) {
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({
    first_name: user.first_name, last_name: user.last_name, phone: user.phone,
    headline: profile.headline, university: profile.university, study_level: profile.study_level, city: profile.city,
    bio: profile.bio, linkedin_url: profile.linkedin_url, github_url: profile.github_url,
  });
  const [msg, setMsg] = useState({ tone: "success", text: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setMsg({ tone: "success", text: "" });
    const { first_name, last_name, phone, ...rest } = form;
    try {
      setUser(await api.patch("/auth/me/", { first_name, last_name, phone }));
      await api.patch("/profile/", rest);
      await onSaved();
      setMsg({ tone: "success", text: "Modifications enregistrées." });
    } catch (err) {
      setMsg({ tone: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Alert tone={msg.tone}>{msg.text}</Alert></div>
        <Field label="Prénom"><Input value={form.first_name} onChange={set("first_name")} /></Field>
        <Field label="Nom"><Input value={form.last_name} onChange={set("last_name")} /></Field>
        <Field label="Téléphone"><Input type="tel" value={form.phone} onChange={set("phone")} /></Field>
        <Field label="Ville"><Input value={form.city} onChange={set("city")} /></Field>
        <Field label="Titre du profil" hint="Ex. : Étudiant ingénieur en développement web" className="sm:col-span-2"><Input maxLength={120} value={form.headline} onChange={set("headline")} /></Field>
        <Field label="Établissement"><Input value={form.university} onChange={set("university")} /></Field>
        <Field label="Niveau d'études"><Input value={form.study_level} onChange={set("study_level")} placeholder="Ex. : 3e année d'ingénieur" /></Field>
        <Field label="Présentation" className="sm:col-span-2"><Textarea rows={4} value={form.bio} onChange={set("bio")} /></Field>
        <Field label="LinkedIn"><Input type="url" value={form.linkedin_url} onChange={set("linkedin_url")} /></Field>
        <Field label="GitHub"><Input type="url" value={form.github_url} onChange={set("github_url")} /></Field>
        <div className="sm:col-span-2"><Button type="submit" variant="success" loading={busy}>Enregistrer</Button></div>
      </form>
    </Card>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState(null);
  const [tab, setTab] = useState("about");
  const refresh = useCallback(async () => setProfile(await api.get("/profile/")), []);
  useEffect(() => { refresh(); }, [refresh]);
  if (!profile) return <Loading />;

  return (
    <>
      <PageHeader title="Mon profil" subtitle={`Profil complété à ${profile.completion.percent}%. Plus il est complet, plus vos CV et recommandations seront précis.`} />
      <div className="-mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex w-max gap-1 rounded-xl border border-brand-100 bg-white p-1" role="tablist">
          {TABS.map(([key, text]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={cx("rounded-lg px-3.5 py-2 text-sm font-medium transition-colors", tab === key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-brand-50")}>
              {text}
            </button>
          ))}
        </div>
      </div>
      {tab === "about" ? <AboutForm profile={profile} onSaved={refresh} />
        : <SectionEditor key={tab} config={SECTIONS[tab]} items={profile[tab]} onChange={refresh} />}
    </>
  );
}
