"use client";
import { Button, Card, cx } from "./ui";

/** Number + label tile used on dashboards. `tone` colors the number. */
export function StatCard({ label, value, hint, tone = "blue" }) {
  const color = { blue: "text-brand-600", green: "text-leaf-600", amber: "text-amber-600", red: "text-red-600", slate: "text-navy-900" }[tone];
  return (
    <Card>
      <p className="text-sm text-slate-600">{label}</p>
      <p className={cx("mt-1 font-display text-3xl font-bold", color)}>{value ?? "–"}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}

/**
 * Small accessible bar chart (no chart library). `data` = [{ label, value }].
 * A text table alternative is exposed to screen readers.
 */
export function BarChart({ data, tone = "blue", height = 120, title }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const fill = tone === "green" ? "bg-leaf-500" : "bg-brand-500";
  return (
    <figure>
      {title && <figcaption className="sr-only">{title}</figcaption>}
      <div className="flex items-end gap-1.5" style={{ height }} role="img"
        aria-label={`${title ?? "Graphique"} : ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
        {data.map((d) => (
          <div key={d.label} className="group flex h-full min-w-0 flex-1 flex-col justify-end" title={`${d.label} : ${d.value}`}>
            <span className="mb-1 text-center text-[11px] font-medium text-slate-600">{d.value || ""}</span>
            <div className={cx("w-full rounded-t", d.value ? fill : "bg-brand-50")} style={{ height: `${Math.max(d.value ? 6 : 3, (d.value / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-1.5" aria-hidden="true">
        {data.map((d) => <span key={d.label} className="min-w-0 flex-1 truncate text-center text-[11px] text-slate-500">{d.label}</span>)}
      </div>
    </figure>
  );
}

/** Previous / next for the paginated admin lists ({count, results} from DRF). */
export function Pager({ page, count, pageSize = 20, onPage }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between gap-3 text-sm">
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Précédent</Button>
      <span className="text-slate-600">Page {page} sur {pages} ({count} résultats)</span>
      <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Suivant</Button>
    </div>
  );
}

export const ROLE_LABELS = { student: "Étudiant", teacher: "Enseignant", admin: "Administrateur" };
export const ROLE_TONES = { student: "blue", teacher: "green", admin: "amber" };

export const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

/** "5 min", "3 h", "2 j" ... for notification lists. */
export function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  if (s < 86400 * 30) return `il y a ${Math.floor(s / 86400)} j`;
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}
