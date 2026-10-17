"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card, EmptyState, Loading, PageHeader, ProgressBar, btnClass } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const REC = {
  review: { tone: "red", text: "À réviser" },
  practice: { tone: "amber", text: "À consolider" },
  mastered: { tone: "green", text: "Maîtrisé" },
};

function StudentDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => {
    Promise.all([
      api.get("/profile/"), api.get("/learning/recommendations/"),
      api.get("/learning/attempts/"), api.get("/learning/formations/"),
    ]).then(([profile, recs, attempts, formations]) =>
      setData({ profile, recs, attempts, formations: formations.filter((f) => f.enrolled) }));
  }, []);
  if (!data) return <Loading />;
  const { profile, recs, attempts, formations } = data;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <h2 className="text-lg font-semibold">Votre profil</h2>
        <p className="mt-3 font-display text-4xl font-bold text-brand-600">{profile.completion.percent}%</p>
        <div className="mt-2"><ProgressBar value={profile.completion.percent} tone="blue" /></div>
        {profile.completion.missing.length > 0 ? (
          <p className="mt-3 text-sm text-slate-600">À compléter : {profile.completion.missing.slice(0, 4).join(", ")}.</p>
        ) : <p className="mt-3 text-sm text-leaf-700">Votre profil est complet.</p>}
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href="/profile" className={btnClass("secondary", "sm")}>Modifier le profil</Link>
          {!profile.cv_url && <Link href="/profile/cv" className={btnClass("primary", "sm")}>Importer mon CV</Link>}
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">Révisions conseillées</h2>
        {recs.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600">Faites un quiz sur l'un de vos cours pour recevoir des conseils.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {recs.slice(0, 3).map((r) => (
              <li key={r.course_id} className="flex items-center justify-between gap-3">
                <Link href={`/learning/courses/${r.course_id}`} className="min-w-0 truncate text-sm font-medium hover:underline">{r.course_title}</Link>
                <span className="flex shrink-0 items-center gap-2 text-sm text-slate-600">{r.average}% <Badge tone={REC[r.level].tone}>{REC[r.level].text}</Badge></span>
              </li>
            ))}
          </ul>
        )}
        <Link href="/learning/courses" className={btnClass("secondary", "sm", "mt-4")}>Mes cours</Link>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">Dernier quiz</h2>
        {attempts.length === 0 ? <p className="mt-3 text-sm text-slate-600">Aucun quiz passé pour le moment.</p> : (
          <div className="mt-3">
            <p className="text-sm font-medium">{attempts[0].quiz_title}</p>
            <p className="mt-1 text-sm text-slate-600">{attempts[0].score} / {attempts[0].total} bonnes réponses</p>
            <div className="mt-2"><ProgressBar value={attempts[0].percent} /></div>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">Mes formations</h2>
        {formations.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600">Vous n'êtes inscrit à aucune formation.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {formations.slice(0, 3).map((f) => (
              <li key={f.id}>
                <Link href={`/learning/formations/${f.id}`} className="text-sm font-medium hover:underline">{f.title}</Link>
                <div className="mt-1"><ProgressBar value={f.progress} /></div>
              </li>
            ))}
          </ul>
        )}
        <Link href="/learning/formations" className={btnClass("secondary", "sm", "mt-4")}>Voir le catalogue</Link>
      </Card>
    </div>
  );
}

function TeacherDashboard() {
  const [formations, setFormations] = useState(null);
  useEffect(() => { api.get("/learning/formations/?mine=1").then(setFormations); }, []);
  if (!formations) return <Loading />;
  return formations.length === 0 ? (
    <EmptyState title="Aucune formation pour l'instant" text="Créez votre première formation, ajoutez des leçons puis publiez-la." action={<Link href="/learning/teach" className={btnClass()}>Créer une formation</Link>} />
  ) : (
    <div className="grid gap-4 md:grid-cols-2">
      {formations.map((f) => (
        <Card key={f.id}>
          <div className="flex items-start justify-between gap-2">
            <Link href={`/learning/formations/${f.id}`} className="font-display text-lg font-semibold hover:underline">{f.title}</Link>
            <Badge tone={f.is_published ? "green" : "slate"}>{f.is_published ? "Publiée" : "Brouillon"}</Badge>
          </div>
          <p className="mt-2 text-sm text-slate-600">{f.lessons_count} leçon(s), {f.enrollments_count} inscrit(s)</p>
        </Card>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const isStudent = user.role === "student";
  return (
    <>
      <PageHeader title={`Bonjour ${user.first_name || ""}`.trim()} subtitle={isStudent ? "Voici où vous en êtes." : "Vos formations en un coup d'œil."} />
      {isStudent ? <StudentDashboard /> : <TeacherDashboard />}
    </>
  );
}
