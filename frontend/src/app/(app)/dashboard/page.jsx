"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Alert, Badge, Card, EmptyState, Loading, PageHeader, ProgressBar, btnClass } from "@/components/ui";
import { BarChart, ROLE_LABELS, StatCard, timeAgo } from "@/components/admin";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const REC = {
  review: { tone: "red", text: "À réviser" },
  practice: { tone: "amber", text: "À consolider" },
  mastered: { tone: "green", text: "Maîtrisé" },
};

/** Latest unread notifications; renders nothing when there are none. */
function NotificationsCard() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/notifications/?unread=1").then(setItems).catch(() => {}); }, []);
  if (items.length === 0) return null;
  return (
    <Card className="mb-4 border-brand-200 bg-brand-50/50">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Notifications <Badge tone="green">{items.length} non lue(s)</Badge></h2>
        <Link href="/notifications" className={btnClass("secondary", "sm")}>Tout voir</Link>
      </div>
      <ul className="mt-3 space-y-2">
        {items.slice(0, 3).map((n) => (
          <li key={n.id} className="text-sm">
            <span className="font-medium">{n.title}</span>
            {n.message && <span className="text-slate-600"> · {n.message}</span>}
            <span className="ml-2 text-xs text-slate-500">{timeAgo(n.created_at)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

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
  const published = formations.filter((f) => f.is_published).length;
  const enrollments = formations.reduce((sum, f) => sum + (f.enrollments_count || 0), 0);
  const lessons = formations.reduce((sum, f) => sum + (f.lessons_count || 0), 0);
  return formations.length === 0 ? (
    <EmptyState title="Aucune formation pour l'instant" text="Créez votre première formation, ajoutez des leçons puis publiez-la." action={<Link href="/learning/teach" className={btnClass()}>Créer une formation</Link>} />
  ) : (
    <>
    <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard label="Formations" value={formations.length} hint={`${published} publiée(s)`} />
      <StatCard label="Inscriptions" value={enrollments} tone="green" />
      <StatCard label="Leçons" value={lessons} tone="slate" />
      <StatCard label="Brouillons" value={formations.length - published} tone="amber" />
    </div>
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
    </>
  );
}

const shortDate = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.get("/admin/stats/").then(setStats).catch((err) => setError(err.message)); }, []);
  if (error) return <Alert>{error}</Alert>;
  if (!stats) return <Loading />;
  const { users, learning, moderation, top_formations: top } = stats;
  const roleTotal = Math.max(1, users.total);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Utilisateurs" value={users.total} hint={`${users.new_30d} nouveau(x) en 30 jours`} />
        <StatCard label="Formations publiées" value={learning.formations_published} hint={`${learning.formations_total} au total`} tone="green" />
        <StatCard label="Inscriptions" value={learning.enrollments} tone="green" />
        <StatCard label="Réussite moyenne aux quiz" value={learning.success_rate === null ? "–" : `${learning.success_rate}%`} hint={`${learning.attempts} quiz passé(s)`} tone="slate" />
        <Link href="/admin/content" className="block rounded-xl focus-visible:outline-2 focus-visible:outline-brand-600">
          <StatCard label="Signalements ouverts" value={moderation.open_reports} tone={moderation.open_reports ? "red" : "slate"} hint="Voir les signalements" />
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="text-lg font-semibold">Nouveaux comptes par semaine</h2>
          <p className="mb-3 text-sm text-slate-600">8 dernières semaines (début de semaine)</p>
          <BarChart title="Nouveaux comptes par semaine" data={users.signups_by_week.map((w) => ({ label: shortDate(w.start), value: w.count }))} />
        </Card>
        <Card>
          <h2 className="text-lg font-semibold">Quiz passés par jour</h2>
          <p className="mb-3 text-sm text-slate-600">14 derniers jours</p>
          <BarChart tone="green" title="Quiz passés par jour" data={learning.attempts_by_day.map((d) => ({ label: d.date.slice(8, 10), value: d.count }))} />
        </Card>
        <Card>
          <h2 className="text-lg font-semibold">Répartition des comptes</h2>
          <ul className="mt-3 space-y-3">
            {Object.entries(users.by_role).map(([role, n]) => (
              <li key={role}>
                <div className="mb-1 flex justify-between text-sm"><span>{ROLE_LABELS[role]}</span><span className="font-medium">{n}</span></div>
                <ProgressBar value={(100 * n) / roleTotal} tone={role === "student" ? "blue" : "green"} />
              </li>
            ))}
          </ul>
          {users.inactive > 0 && <p className="mt-3 text-sm text-slate-600">{users.inactive} compte(s) désactivé(s).</p>}
          <Link href="/admin/users" className={btnClass("secondary", "sm", "mt-4")}>Gérer les utilisateurs</Link>
        </Card>
        <Card>
          <h2 className="text-lg font-semibold">Formations les plus suivies</h2>
          {top.length === 0 ? <p className="mt-3 text-sm text-slate-600">Aucune inscription pour le moment.</p> : (
            <ol className="mt-3 space-y-3">
              {top.map((f, i) => (
                <li key={f.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0"><span className="mr-2 font-semibold text-brand-600">{i + 1}.</span><Link href={`/learning/formations/${f.id}`} className="font-medium hover:underline">{f.title}</Link><span className="block truncate pl-5 text-xs text-slate-500">{f.teacher_name}</span></span>
                  <Badge tone="green">{f.enrollments} inscrit(s)</Badge>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-3 text-sm text-slate-600">{learning.courses} cours · {learning.quizzes} quiz, dont {learning.ai_quizzes} généré(s) par IA.</p>
        </Card>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const isStudent = user.role === "student";
  const isAdmin = user.role === "admin";
  const subtitle = isStudent ? "Voici où vous en êtes." : isAdmin ? "L'activité de la plateforme en un coup d'œil." : "Vos formations en un coup d'œil.";
  return (
    <>
      <PageHeader title={`Bonjour ${user.first_name || ""}`.trim()} subtitle={subtitle} />
      <NotificationsCard />
      {isStudent ? <StudentDashboard /> : isAdmin ? <AdminDashboard /> : <TeacherDashboard />}
    </>
  );
}
