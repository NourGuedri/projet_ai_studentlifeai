"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import QuizEditor from "@/components/QuizEditor";
import { Alert, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function NewQuiz() {
  const { user } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const courseId = params.get("course");
  const formationId = params.get("formation");
  const [course, setCourse] = useState(null);
  const [formation, setFormation] = useState(null);
  const [ready, setReady] = useState(!courseId && !formationId);
  const [error, setError] = useState("");
  const isTeacher = user.role === "teacher" || user.role === "admin";

  useEffect(() => {
    if (!isTeacher) {
      router.replace(courseId ? `/learning/quizzes/practice?course=${courseId}` : "/learning/quizzes/practice");
      return;
    }
    const sourceRequest = courseId
      ? api.get(`/learning/courses/${courseId}/`).then(setCourse)
      : formationId
        ? api.get(`/learning/formations/${formationId}/`).then(setFormation)
        : Promise.resolve();
    sourceRequest.catch((e) => setError(e.message)).finally(() => setReady(true));
  }, [courseId, formationId, isTeacher, router]);

  if (!isTeacher) return <Loading />;
  if (!ready) return <Loading />;
  return (
    <>
      <PageHeader title="Nouveau quiz" subtitle={course ? `À partir du cours « ${course.title} »` : formation ? `Pour la formation « ${formation.title} »` : "Écrivez vos questions ou générez-les à partir d'un texte."} />
      <div className="mb-4"><Alert>{error}</Alert></div>
      <QuizEditor course={course} formation={formation} formationId={formationId ? Number(formationId) : null}
        onSaved={(quiz) => router.push(formationId ? `/learning/formations/${formationId}` : `/learning/quizzes/${quiz.id}`)} />
    </>
  );
}

export default function NewQuizPage() {
  return <Suspense fallback={<Loading />}><NewQuiz /></Suspense>;
}
