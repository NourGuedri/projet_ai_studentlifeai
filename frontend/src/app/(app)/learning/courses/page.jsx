"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import CourseForm from "@/components/CourseForm";
import { Badge, Button, Card, EmptyState, Loading, PageHeader, cx } from "@/components/ui";
import { api } from "@/lib/api";

export default function CoursesPage() {
  const [courses, setCourses] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    const [c, s] = await Promise.all([
      api.get(`/learning/courses/${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`),
      api.get("/learning/courses/subjects/"),
    ]);
    setCourses(c);
    setSubjects(s);
  }, [subject]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <PageHeader title="Mes cours" subtitle="Ajoutez vos cours par matière, puis générez des quiz pour réviser."
        actions={!adding && <Button onClick={() => setAdding(true)}>Nouveau cours</Button>} />
      {adding && (
        <div className="mb-6">
          <CourseForm subjects={subjects} onCancel={() => setAdding(false)} onSaved={async () => { setAdding(false); await load(); }} />
        </div>
      )}

      {subjects.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {["", ...subjects].map((s) => (
            <button key={s || "all"} onClick={() => setSubject(s)}
              className={cx("rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors", subject === s ? "border-brand-600 bg-brand-600 text-white" : "border-brand-200 bg-white text-brand-700 hover:bg-brand-50")}>
              {s || "Toutes les matières"}
            </button>
          ))}
        </div>
      )}

      {!courses ? <Loading /> : courses.length === 0 ? (
        <EmptyState title="Aucun cours" text="Ajoutez un cours (fichier ou texte) pour commencer à réviser." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {courses.map((c) => (
            <Link key={c.id} href={`/learning/courses/${c.id}`} className="group">
              <Card className="h-full transition-colors group-hover:border-brand-500">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-display text-lg font-semibold">{c.title}</h2>
                  {c.subject && <Badge>{c.subject}</Badge>}
                </div>
                {c.description && <p className="mt-1 line-clamp-2 text-sm text-slate-600">{c.description}</p>}
                <p className="mt-3 text-sm text-slate-500">{c.quiz_count} quiz</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
