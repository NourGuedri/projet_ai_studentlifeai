"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card, EmptyState, Loading, PageHeader, ProgressBar, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/labels";

const LEVEL = {
  review: { tone: "red", text: "À réviser", advice: "Refaites un quiz après avoir relu le cours, surtout les points manqués." },
  practice: { tone: "amber", text: "À consolider", advice: "Encore une session de révision et ce cours sera acquis." },
  mastered: { tone: "green", text: "Maîtrisé", advice: "Bon niveau : un quiz de temps en temps suffit pour l'entretenir." },
};

export default function ResultsPage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    Promise.all([api.get("/learning/recommendations/"), api.get("/learning/attempts/")]).then(([recs, attempts]) => setData({ recs, attempts }));
  }, []);
  if (!data) return <Loading />;
  const { recs, attempts } = data;
  const average = attempts.length ? Math.round(attempts.reduce((n, a) => n + a.percent, 0) / attempts.length) : 0;

  return (
    <>
      <PageHeader title="Résultats" subtitle="Vos scores et ce qu'il faut réviser en priorité." />
      {attempts.length === 0 ? (
        <EmptyState title="Aucun résultat" text="Passez un quiz pour voir vos scores et recevoir des conseils de révision."
          action={<Link href="/learning/quizzes" className={btnClass()}>Voir les quiz</Link>} />
      ) : (
        <div className="space-y-8">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card><p className="text-sm text-slate-600">Quiz passés</p><p className="font-display text-4xl font-bold">{attempts.length}</p></Card>
            <Card><p className="text-sm text-slate-600">Score moyen</p><p className="font-display text-4xl font-bold text-leaf-600">{average}%</p></Card>
          </div>

          {recs.length > 0 && (
            <section>
              <h2 className="mb-3 text-xl font-semibold">Révisions conseillées</h2>
              <div className="space-y-3">
                {recs.map((r) => (
                  <Card key={r.course_id}>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <Link href={`/learning/courses/${r.course_id}`} className="font-medium hover:underline">{r.course_title}</Link>
                      <Badge tone={LEVEL[r.level].tone}>{LEVEL[r.level].text}</Badge>
                    </div>
                    <div className="mt-2 flex items-center gap-3">
                      <div className="flex-1"><ProgressBar value={r.average} tone={r.level === "mastered" ? "green" : "blue"} /></div>
                      <span className="text-sm font-medium">{r.average}%</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-600">{LEVEL[r.level].advice}</p>
                    {r.missed_questions.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium">Points manqués au dernier quiz :</p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-600">{r.missed_questions.map((q) => <li key={q}>{q}</li>)}</ul>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-3 text-xl font-semibold">Historique</h2>
            <ul className="space-y-3">
              {attempts.map((a) => (
                <li key={a.id}>
                  <Card className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <Link href={`/learning/quizzes/${a.quiz}`} className="font-medium hover:underline">{a.quiz_title}</Link>
                      <p className="text-sm text-slate-500">{fmtDate(a.created_at)}{a.course_title && `, ${a.course_title}`}</p>
                    </div>
                    <Badge tone={a.percent >= 70 ? "green" : "blue"}>{a.score} / {a.total} ({a.percent}%)</Badge>
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
