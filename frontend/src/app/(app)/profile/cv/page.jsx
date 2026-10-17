"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Card, Loading, PageHeader, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { EXP_TYPES, LANG_LEVELS, LEVELS, label } from "@/lib/labels";

const SECTIONS = [
  ["skills", "Compétences", (i) => `${i.name} (${label(LEVELS, i.level)})`],
  ["educations", "Formation", (i) => [i.school, i.degree, i.field, [i.start_year, i.end_year].filter(Boolean).join("–")].filter(Boolean).join(", ")],
  ["experiences", "Expériences", (i) => [i.position, i.company, label(EXP_TYPES, i.type)].filter(Boolean).join(", ")],
  ["projects", "Projets", (i) => [i.title, i.tech_stack].filter(Boolean).join(", ")],
  ["certifications", "Certifications", (i) => [i.name, i.issuer].filter(Boolean).join(", ")],
  ["languages", "Langues", (i) => `${i.name} (${label(LANG_LEVELS, i.level)})`],
];
const SUMMARY = { skills: "compétence(s)", educations: "formation(s)", experiences: "expérience(s)", projects: "projet(s)", certifications: "certification(s)", languages: "langue(s)" };

export default function CVPage() {
  const input = useRef(null);
  const [profile, setProfile] = useState(null);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null); // { method, extracted }
  const [selected, setSelected] = useState({}); // { skills: Set, ... }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  useEffect(() => { api.get("/profile/").then(setProfile); }, []);

  async function upload() {
    setBusy(true); setError(""); setDone(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await api.form("/profile/cv/", form);
      setResult(data);
      setSelected(Object.fromEntries(SECTIONS.map(([key]) => [key, new Set(data.extracted[key].map((_, i) => i))])));
      setProfile(await api.get("/profile/"));
    } catch (err) { setError(err.message); setResult(null); }
    finally { setBusy(false); }
  }

  function toggle(key, index) {
    setSelected((s) => {
      const next = new Set(s[key]);
      next.has(index) ? next.delete(index) : next.add(index);
      return { ...s, [key]: next };
    });
  }

  async function apply() {
    setBusy(true); setError("");
    const ex = result.extracted;
    const body = { linkedin_url: ex.linkedin_url, github_url: ex.github_url, headline: ex.headline, bio: ex.bio };
    for (const [key] of SECTIONS) body[key] = ex[key].filter((_, i) => selected[key].has(i));
    try {
      const data = await api.post("/profile/cv/apply/", body);
      setDone(data.created);
      setResult(null); setFile(null);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  if (!profile) return <Loading />;
  const total = result ? SECTIONS.reduce((n, [key]) => n + selected[key].size, 0) : 0;

  return (
    <>
      <PageHeader title="Importer mon CV" subtitle="Déposez votre CV : nous en extrayons vos compétences, formations et expériences pour remplir votre profil. Vous vérifiez avant d'enregistrer." />
      <div className="space-y-5">
        <Alert>{error}</Alert>
        {done && (
          <Alert tone="success">
            Profil mis à jour : {Object.entries(done).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${SUMMARY[k]}`).join(", ") || "rien de nouveau à ajouter"}.{" "}
            <Link href="/profile" className="font-medium underline">Voir mon profil</Link>
          </Alert>
        )}

        <Card>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="font-medium">{file ? file.name : "Choisissez un fichier PDF ou DOCX (5 Mo max)"}</p>
              {profile.cv_url && !file && <a href={profile.cv_url} target="_blank" rel="noreferrer" className="text-sm text-brand-700 underline">Voir le dernier CV importé</a>}
            </div>
            <div className="flex gap-2">
              <input ref={input} type="file" accept=".pdf,.docx" className="sr-only" onChange={(e) => { setFile(e.target.files[0] || null); setResult(null); }} />
              <Button variant="secondary" onClick={() => input.current.click()}>Choisir un fichier</Button>
              <Button disabled={!file} loading={busy && !result} onClick={upload}>Analyser mon CV</Button>
            </div>
          </div>
        </Card>

        {result && (
          <>
            <Alert tone="info">
              {result.method === "ai"
                ? "Contenu extrait par l'IA : relisez-le avant de l'enregistrer."
                : "Extraction simple par mots-clés (la clé GEMINI_API_KEY n'est pas configurée). Relisez bien le résultat : l'IA donne de meilleurs résultats."}
            </Alert>
            {SECTIONS.filter(([key]) => result.extracted[key].length > 0).map(([key, title, show]) => (
              <Card key={key}>
                <div className="mb-3 flex items-center gap-2">
                  <h2 className="text-lg font-semibold">{title}</h2>
                  <Badge tone="slate">{selected[key].size} / {result.extracted[key].length}</Badge>
                </div>
                <ul className="space-y-2">
                  {result.extracted[key].map((item, i) => (
                    <li key={i}>
                      <label className="flex cursor-pointer items-start gap-3 rounded-lg p-2 hover:bg-brand-50">
                        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-leaf-600" checked={selected[key].has(i)} onChange={() => toggle(key, i)} />
                        <span className="text-sm">{show(item)}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
            {total === 0 && SECTIONS.every(([key]) => result.extracted[key].length === 0) && (
              <Alert>Nous n'avons trouvé aucune information exploitable. Ajoutez-les manuellement depuis votre profil.</Alert>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="success" loading={busy} disabled={total === 0} onClick={apply}>Ajouter {total} élément(s) à mon profil</Button>
              <Button variant="ghost" onClick={() => setResult(null)}>Annuler</Button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
