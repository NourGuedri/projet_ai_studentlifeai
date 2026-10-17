"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card, EmptyState, Loading, PageHeader, ProgressBar, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { LEVELS, label } from "@/lib/labels";

export default function FormationsPage() {
  const [formations, setFormations] = useState(null);
  const [onlyMine, setOnlyMine] = useState(false);
  useEffect(() => { api.get("/learning/formations/").then(setFormations); }, []);
  if (!formations) return <Loading />;
  const list = onlyMine ? formations.filter((f) => f.enrolled) : formations;

  return (
    <>
      <PageHeader title="Formations" subtitle="Les formations publiées par les enseignants. Inscrivez-vous pour accéder aux leçons et aux quiz." />
      <div className="mb-5 flex gap-2">
        {[[false, "Catalogue"], [true, "Mes inscriptions"]].map(([value, text]) => (
          <button key={text} onClick={() => setOnlyMine(value)}
            className={cx("rounded-full border px-3.5 py-1.5 text-sm font-medium", onlyMine === value ? "border-brand-600 bg-brand-600 text-white" : "border-brand-200 bg-white text-brand-700 hover:bg-brand-50")}>
            {text}
          </button>
        ))}
      </div>
      {list.length === 0 ? (
        <EmptyState title={onlyMine ? "Aucune inscription" : "Aucune formation publiée"} text={onlyMine ? "Parcourez le catalogue pour vous inscrire." : "Revenez bientôt."} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {list.map((f) => (
            <Link key={f.id} href={`/learning/formations/${f.id}`} className="group">
              <Card className="flex h-full flex-col gap-3 transition-colors group-hover:border-brand-500">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-display text-lg font-semibold">{f.title}</h2>
                  <Badge tone={f.is_published ? "blue" : "slate"}>{f.is_published ? label(LEVELS, f.level) : "Brouillon"}</Badge>
                </div>
                <p className="line-clamp-2 text-sm text-slate-600">{f.description}</p>
                <p className="mt-auto text-sm text-slate-500">{f.teacher_name}, {f.lessons_count} leçon(s)</p>
                {f.enrolled && <ProgressBar value={f.progress} />}
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
