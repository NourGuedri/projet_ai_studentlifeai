"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import CourseForm from "@/components/CourseForm";
import { Alert, Badge, Button, Card, EmptyState, Loading, PageHeader, btnClass } from "@/components/ui";
import { api } from "@/lib/api";

export default function CourseDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [course, setCourse] = useState(null);
  const [quizzes, setQuizzes] = useState([]);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, q] = await Promise.all([api.get(`/learning/courses/${id}/`), api.get(`/learning/quizzes/?course=${id}`)]);
      setCourse(c);
      setQuizzes(q);
    } catch (err) { setError(err.message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  async function remove() {
    if (!confirm("Supprimer ce cours ? Ses quiz seront conservés mais détachés du cours.")) return;
    await api.del(`/learning/courses/${id}/`);
    router.replace("/learning/courses");
  }

  if (error) return <Alert>{error}</Alert>;
  if (!course) return <Loading />;
  const hasText = course.content.trim().length >= 50;
  const hasDocument = !!course.file;
  const practiceHref = `/learning/quizzes/practice?course=${course.id}`;

  return (
    <>
      <PageHeader title={course.title} subtitle={course.description}
        actions={<>
          <Link href={practiceHref} className={btnClass("success")}>S'entraîner avec l'IA</Link>
          <Button variant="secondary" onClick={() => setEditing(!editing)}>Modifier</Button>
          <Button variant="danger" onClick={remove}>Supprimer</Button>
        </>} />
      {course.subject && <div className="-mt-3 mb-5"><Badge>{course.subject}</Badge></div>}

      {editing && <div className="mb-6"><CourseForm course={course} onCancel={() => setEditing(false)} onSaved={async () => { setEditing(false); await load(); }} /></div>}

      <div className="space-y-6">
        {!hasText && !hasDocument && <Alert tone="info">Ce cours n'a pas encore assez de texte ni de document lisible pour générer un quiz. Ajoutez du texte ou un fichier PDF, DOCX, TXT ou MD avec « Modifier ».</Alert>}

        <section>
          <h2 className="mb-3 text-xl font-semibold">Quiz de ce cours</h2>
          {quizzes.length === 0 ? (
            <EmptyState title="Aucun quiz" text="Générez un quiz avec l'IA pour vous entraîner."
              action={<Link href={practiceHref} className={btnClass("success")}>Générer un quiz IA</Link>} />
          ) : (
            <ul className="space-y-3">
              {quizzes.map((q) => (
                <li key={q.id}>
                  <Card className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium">{q.title}</p>
                      <p className="text-sm text-slate-600">{q.question_count} questions{q.my_last_percent != null && `, dernier score : ${q.my_last_percent}%`}</p>
                    </div>
                    <Link href={`/learning/quizzes/${q.id}`} className={btnClass("primary", "sm")}>Passer le quiz</Link>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>

        {hasText && (
          <section>
            <h2 className="mb-3 text-xl font-semibold">Contenu du cours</h2>
            <Card><p className="max-h-80 overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-slate-700">{course.content}</p></Card>
          </section>
        )}
      </div>
    </>
  );
}
