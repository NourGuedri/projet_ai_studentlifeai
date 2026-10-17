"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, Loading, PageHeader, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function QuizzesPage() {
  const { user } = useAuth();
  const isTeacher = user.role === "teacher" || user.role === "admin";
  const [quizzes, setQuizzes] = useState(null);
  useEffect(() => { api.get("/learning/quizzes/").then(setQuizzes); }, []);

  async function remove(quiz) {
    if (!confirm(`Supprimer le quiz « ${quiz.title} » et ses résultats ?`)) return;
    try {
      await api.del(`/learning/quizzes/${quiz.id}/`);
      setQuizzes((items) => items.filter((item) => item.id !== quiz.id));
    } catch (error) {
      alert(error.message);
    }
  }

  return (
    <>
      <PageHeader title="Quiz" subtitle={isTeacher ? "Créez et gérez vos quiz, ou consultez ceux disponibles." : "Passez les quiz de vos formations ou générez un quiz IA pour vous entraîner."}
        actions={isTeacher
          ? <Link href="/learning/quizzes/new" className={btnClass()}>Créer un quiz</Link>
          : <Link href="/learning/quizzes/practice" className={btnClass()}>Générer un quiz IA</Link>} />
      {!quizzes ? <Loading /> : quizzes.length === 0 ? (
        <EmptyState title="Aucun quiz" text={isTeacher ? "Créez un quiz pour vos étudiants depuis vos formations." : "Inscrivez-vous à une formation pour accéder aux quiz, ou générez un quiz IA pour vous entraîner."}
          action={!isTeacher && <Link href="/learning/quizzes/practice" className={btnClass()}>Générer un quiz IA</Link>} />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {quizzes.map((q) => (
            <li key={q.id}>
              <Card className="flex h-full flex-col justify-between gap-4">
                <div>
                  <p className="font-display text-lg font-semibold">{q.title}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {q.course_title && <Badge>{q.course_title}</Badge>}
                    {q.formation_title && <Badge tone="green">{q.formation_title}</Badge>}
                    {q.ai_generated && <Badge tone="slate">Généré par l'IA</Badge>}
                  </div>
                  <p className="mt-3 text-sm text-slate-600">{q.question_count} questions{q.my_last_percent != null && `, dernier score : ${q.my_last_percent}%`}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link href={`/learning/quizzes/${q.id}`} className={btnClass(isTeacher ? "secondary" : "primary", "sm")}>
                    {isTeacher ? "Voir le quiz" : "Passer le quiz"}
                  </Link>
                  {isTeacher && q.is_owner && (
                    <>
                      <Link href={`/learning/quizzes/${q.id}/edit`} className={btnClass("secondary", "sm")}>Modifier</Link>
                      <Button variant="danger" size="sm" onClick={() => remove(q)}>Supprimer</Button>
                    </>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
