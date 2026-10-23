"use client";
import { fmtDay } from "@/lib/labels";
import { Badge, Card } from "./ui";

/** Card holding an AI result, always labelled as such. */
export function AiCard({ title, actions, children }) {
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        <div className="flex items-center gap-2">
          {actions}
          <Badge tone="amber">Généré par l'IA</Badge>
        </div>
      </div>
      {children}
    </Card>
  );
}

/** Tasks in the shared {title, assignee, due_date} format. */
export function TaskList({ tasks }) {
  if (!tasks?.length) return <p className="text-sm text-slate-500">Aucune tâche détectée.</p>;
  return (
    <ul className="divide-y divide-brand-50">
      {tasks.map((task, i) => (
        <li key={i} className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0">
          <span className="text-sm font-medium text-navy-900">{task.title}</span>
          <span className="flex flex-wrap gap-2">
            {task.assignee && <Badge tone="slate">{task.assignee}</Badge>}
            {task.due_date ? <Badge tone="red">Échéance : {fmtDay(task.due_date)}</Badge> : <Badge tone="slate">Sans échéance</Badge>}
          </span>
        </li>
      ))}
    </ul>
  );
}
