"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import QuizEditor from "@/components/QuizEditor";
import { Alert, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function EditQuizPage() {
  const { user } = useAuth();
  const { id } = useParams();
  const router = useRouter();
  const [data, setData] = useState(null); // { quiz, course }
  const [error, setError] = useState("");
  const isTeacher = user.role === "teacher" || user.role === "admin";

  useEffect(() => {
    if (!isTeacher) {
      router.replace("/learning/quizzes");
      return;
    }
    (async () => {
      try {
        const quiz = await api.get(`/learning/quizzes/${id}/`);
        const course = quiz.course ? await api.get(`/learning/courses/${quiz.course}/`).catch(() => null) : null;
        setData({ quiz, course });
      } catch (err) { setError(err.message); }
    })();
  }, [id, isTeacher, router]);

  if (!isTeacher) return <Loading />;
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading />;
  if (!data.quiz.is_owner) return <Alert>Seul le formateur propriétaire de ce quiz peut le modifier.</Alert>;

  return (
    <>
      <PageHeader title="Modifier le quiz" subtitle="Les résultats déjà enregistrés sont conservés pour les questions que vous gardez." />
      <QuizEditor quiz={data.quiz} course={data.course} onSaved={() => router.push(`/learning/quizzes/${id}`)} />
    </>
  );
}
