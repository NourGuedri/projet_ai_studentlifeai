"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, ProgressBar, Textarea, btnClass, cx } from "@/components/ui";
import ReportButton from "@/components/ReportButton";
import { api } from "@/lib/api";
import { LEVELS, MATERIAL_KINDS, fmtSize, label } from "@/lib/labels";

const ACCEPT = ".pdf,.doc,.docx,.odt,.ppt,.pptx,.odp,.xls,.xlsx,.csv,.txt,.md,.zip,.png,.jpg,.jpeg,.gif,.webp,.mp3,.wav,.m4a,.mp4,.webm,.mov,.m4v";

/** Upload files one by one to a lesson. Returns the list of error messages (empty = all good). */
async function uploadFiles(lessonId, files, onProgress) {
  const errors = [];
  for (const [i, file] of files.entries()) {
    const form = new FormData();
    form.append("lesson", lessonId);
    form.append("file", file);
    try {
      await api.upload("/learning/materials/", form, (percent) => onProgress({ name: file.name, index: i + 1, total: files.length, percent }));
    } catch (err) {
      errors.push(`${file.name} : ${err.message}`);
    }
  }
  return errors;
}

function UploadProgress({ progress }) {
  if (!progress) return null;
  return (
    <div className="space-y-1 rounded-lg bg-brand-50 p-3 text-sm" aria-live="polite">
      <p className="truncate">Envoi de {progress.name} ({progress.index}/{progress.total}), {progress.percent}%</p>
      <ProgressBar value={progress.percent} tone="blue" />
    </div>
  );
}

function FilePicker({ files, setFiles }) {
  const input = useRef(null);
  return (
    <div className="space-y-2">
      <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only"
        onChange={(e) => { setFiles([...files, ...e.target.files]); e.target.value = ""; }} />
      <Button variant="secondary" size="sm" onClick={() => input.current.click()}>Choisir des fichiers</Button>
      {files.length > 0 && (
        <ul className="space-y-1 text-sm">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2 rounded-lg bg-brand-50 px-3 py-1.5">
              <span className="truncate">{f.name} <span className="text-slate-500">({fmtSize(f.size)})</span></span>
              <button type="button" className="text-red-700 hover:underline" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Retirer</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MaterialItem({ m, onDelete }) {
  return (
    <li className="rounded-lg border border-brand-100 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{m.name}</p>
          <p className="text-xs text-slate-500">{MATERIAL_KINDS[m.kind]}, {fmtSize(m.size)}</p>
        </div>
        <div className="flex gap-2">
          {m.kind === "pdf"
            ? <a href={m.url} target="_blank" rel="noreferrer" className={btnClass("secondary", "sm")}>Ouvrir</a>
            : m.kind !== "video" && m.kind !== "audio" && m.kind !== "image" && <a href={m.url} download={m.name} className={btnClass("secondary", "sm")}>Télécharger</a>}
          {onDelete && <Button size="sm" variant="danger" onClick={() => onDelete(m)}>Supprimer</Button>}
        </div>
      </div>
      {m.kind === "video" && <video controls preload="metadata" src={m.url} className="mt-3 max-h-[70vh] w-full rounded-lg bg-black" />}
      {m.kind === "audio" && <audio controls src={m.url} className="mt-3 w-full" />}
      {m.kind === "image" && /* eslint-disable-next-line @next/next/no-img-element */ <img src={m.url} alt={m.name} className="mt-3 max-h-96 rounded-lg" />}
    </li>
  );
}

function AddFiles({ lessonId, onDone }) {
  const [files, setFiles] = useState([]);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true);
    setError("");
    const errors = await uploadFiles(lessonId, files, setProgress);
    setProgress(null);
    setBusy(false);
    setFiles([]);
    if (errors.length) setError(errors.join(" — "));
    await onDone();
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed border-brand-200 p-3">
      <p className="text-sm font-medium">Ajouter des supports (PDF, Word, PowerPoint, vidéo...)</p>
      <Alert>{error}</Alert>
      <FilePicker files={files} setFiles={setFiles} />
      <UploadProgress progress={progress} />
      {files.length > 0 && <Button variant="success" size="sm" loading={busy} onClick={send}>Envoyer {files.length} fichier(s)</Button>}
    </div>
  );
}

function LessonForm({ formationId, count, onSaved }) {
  const [form, setForm] = useState({ title: "", content: "", video_url: "", resource_url: "" });
  const [files, setFiles] = useState([]);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const lesson = await api.post("/learning/lessons/", { ...form, formation: formationId, order: count });
      const errors = await uploadFiles(lesson.id, files, setProgress);
      setForm({ title: "", content: "", video_url: "", resource_url: "" });
      setFiles([]);
      if (errors.length) setError(`La leçon est créée, mais certains fichiers n'ont pas été envoyés : ${errors.join(" — ")}. Vous pouvez les rajouter depuis la leçon.`);
      await onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setProgress(null);
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Alert>{error}</Alert></div>
        <Field label="Titre de la leçon" className="sm:col-span-2"><Input required value={form.title} onChange={set("title")} /></Field>
        <Field label="Contenu" className="sm:col-span-2"><Textarea rows={5} value={form.content} onChange={set("content")} /></Field>
        <div className="space-y-1 sm:col-span-2">
          <p className="text-sm font-medium">Supports de cours</p>
          <p className="text-xs text-slate-500">PDF, Word, PowerPoint, Excel, images, audio ou vidéo (MP4, WebM, MOV). Les vidéos peuvent prendre un moment à envoyer.</p>
          <FilePicker files={files} setFiles={setFiles} />
        </div>
        <Field label="Lien vidéo (YouTube, Drive...)"><Input type="url" value={form.video_url} onChange={set("video_url")} placeholder="https://" /></Field>
        <Field label="Autre lien utile"><Input type="url" value={form.resource_url} onChange={set("resource_url")} placeholder="https://" /></Field>
        <div className="space-y-3 sm:col-span-2">
          <UploadProgress progress={progress} />
          <Button type="submit" variant="success" loading={busy}>Ajouter la leçon</Button>
        </div>
      </form>
    </Card>
  );
}

export default function FormationPage() {
  const { id } = useParams();
  const router = useRouter();
  const [f, setF] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null);

  const load = async () => {
    try { setF(await api.get(`/learning/formations/${id}/`)); } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(fn) {
    setBusy(true);
    setError("");
    try { await fn(); } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  const enroll = () => run(async () => setF(await api.post(`/learning/formations/${id}/enroll/`)));
  const toggle = (lessonId) => run(async () => setF(await api.post(`/learning/formations/${id}/toggle-lesson/`, { lesson_id: lessonId })));
  const publish = () => run(async () => setF(await api.patch(`/learning/formations/${id}/`, { is_published: !f.is_published })));
  const removeLesson = (lessonId) => run(async () => { if (confirm("Supprimer cette leçon et ses fichiers ?")) { await api.del(`/learning/lessons/${lessonId}/`); await load(); } });
  const removeMaterial = (m) => run(async () => { if (confirm(`Supprimer « ${m.name} » ?`)) { await api.del(`/learning/materials/${m.id}/`); await load(); } });
  const removeFormation = () => run(async () => {
    if (!confirm("Supprimer cette formation, ses leçons et ses fichiers ?")) return;
    await api.del(`/learning/formations/${id}/`);
    router.replace("/learning/teach");
  });

  if (!f) return error ? <Alert>{error}</Alert> : <Loading />;
  const locked = !f.is_owner && !f.enrolled;

  return (
    <>
      <PageHeader title={f.title} subtitle={`${f.teacher_name}, niveau ${label(LEVELS, f.level).toLowerCase()}${f.category ? `, ${f.category}` : ""}`}
        actions={f.is_owner ? (
          <>
            <Button variant={f.is_published ? "secondary" : "success"} loading={busy} onClick={publish}>{f.is_published ? "Dépublier" : "Publier"}</Button>
            <Button variant="danger" onClick={removeFormation}>Supprimer</Button>
          </>
        ) : (
          <>
            {!f.enrolled && <Button variant="success" loading={busy} onClick={enroll}>S'inscrire</Button>}
            {f.is_published && <ReportButton targetType="formation" targetId={f.id} />}
          </>
        )} />

      <div className="mb-4"><Alert>{error}</Alert></div>
      {f.description && <p className="mb-6 max-w-prose whitespace-pre-line text-slate-700">{f.description}</p>}

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {f.is_owner && <Badge tone={f.is_published ? "green" : "slate"}>{f.is_published ? "Publiée" : "Brouillon, invisible pour les étudiants"}</Badge>}
        {f.is_owner && <Badge>{f.enrollments_count} inscrit(s)</Badge>}
      </div>

      {f.enrolled && (
        <Card className="mb-6">
          <div className="mb-2 flex justify-between text-sm font-medium"><span>Ma progression</span><span>{f.progress}%</span></div>
          <ProgressBar value={f.progress} />
        </Card>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-xl font-semibold">Leçons</h2>
        {f.lessons.length === 0 ? (
          <EmptyState title="Aucune leçon" text={f.is_owner ? "Ajoutez votre première leçon ci-dessous." : "Le contenu arrive bientôt."} />
        ) : (
          <ol className="space-y-3">
            {f.lessons.map((l) => {
              const done = f.completed_lessons.includes(l.id);
              const files = l.materials ?? [];
              return (
                <li key={l.id}>
                  <Card className={cx(done && "border-leaf-500/50")}>
                    <div className="flex items-center gap-3">
                      {f.enrolled && (
                        <input type="checkbox" checked={done} disabled={busy} onChange={() => toggle(l.id)} aria-label={`Marquer « ${l.title} » comme terminée`} className="h-5 w-5 shrink-0 accent-leaf-600" />
                      )}
                      <button className="min-w-0 flex-1 text-left font-medium disabled:cursor-default" disabled={locked} onClick={() => setOpen(open === l.id ? null : l.id)}>
                        {l.title}
                        {!locked && files.length > 0 && <span className="ml-2 text-xs font-normal text-slate-500">{files.length} fichier(s)</span>}
                      </button>
                      {f.is_owner && <Button size="sm" variant="danger" onClick={() => removeLesson(l.id)}>Supprimer</Button>}
                    </div>
                    {open === l.id && !locked && (
                      <div className="mt-3 space-y-3 border-t border-brand-100 pt-3 text-sm">
                        {l.content && <p className="whitespace-pre-line text-slate-700">{l.content}</p>}
                        {(l.video_url || l.resource_url) && (
                          <div className="flex flex-wrap gap-3">
                            {l.video_url && <a href={l.video_url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 underline">Voir la vidéo</a>}
                            {l.resource_url && <a href={l.resource_url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 underline">Ouvrir le lien</a>}
                          </div>
                        )}
                        {files.length > 0 && (
                          <ul className="space-y-2">
                            {files.map((m) => <MaterialItem key={m.id} m={m} onDelete={f.is_owner ? removeMaterial : undefined} />)}
                          </ul>
                        )}
                        {f.is_owner && <AddFiles lessonId={l.id} onDone={load} />}
                      </div>
                    )}
                  </Card>
                </li>
              );
            })}
          </ol>
        )}
        {locked && f.lessons.length > 0 && <p className="mt-3 text-sm text-slate-600">Inscrivez-vous pour accéder au contenu des leçons.</p>}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-xl font-semibold">Quiz de la formation</h2>
        {f.quizzes.length === 0 ? (
          <EmptyState
            title="Aucun quiz"
            text={f.is_owner ? "Créez un quiz pour les étudiants inscrits à cette formation." : "Les quiz de cette formation apparaîtront ici."}
            action={f.is_owner && <Link href={`/learning/quizzes/new?formation=${f.id}`} className={btnClass("success")}>Créer un quiz</Link>}
          />
        ) : (
          <ul className="space-y-3">
            {f.quizzes.map((quiz) => (
              <li key={quiz.id}>
                <Card className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{quiz.title}</p>
                    <p className="text-sm text-slate-600">{quiz.question_count} questions</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href={`/learning/quizzes/${quiz.id}`} className={btnClass(f.is_owner ? "secondary" : "primary", "sm")}>
                      {f.is_owner ? "Voir le quiz" : "Passer le quiz"}
                    </Link>
                    {f.is_owner && (
                      <Link href={`/learning/quizzes/${quiz.id}/edit`} className={btnClass("secondary", "sm")}>Modifier</Link>
                    )}
                    {!f.is_owner && f.is_published && <ReportButton targetType="quiz" targetId={quiz.id} size="sm" />}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        )}
        {f.is_owner && f.quizzes.length > 0 && (
          <div className="mt-3">
            <Link href={`/learning/quizzes/new?formation=${f.id}`} className={btnClass("secondary", "sm")}>Ajouter un quiz</Link>
          </div>
        )}
      </section>

      {f.is_owner && (
        <section>
          <h2 className="mb-3 text-xl font-semibold">Ajouter une leçon</h2>
          <LessonForm formationId={f.id} count={f.lessons.length} onSaved={load} />
        </section>
      )}
    </>
  );
}
