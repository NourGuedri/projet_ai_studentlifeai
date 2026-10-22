"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Loading, PageHeader, cx } from "@/components/ui";
import { timeAgo } from "@/components/admin";
import { api } from "@/lib/api";
import { useNotifications } from "@/lib/notifications";

const KIND = {
  info: { tone: "blue", text: "Info" },
  success: { tone: "green", text: "Succès" },
  warning: { tone: "amber", text: "Attention" },
  announcement: { tone: "slate", text: "Annonce" },
};

export default function NotificationsPage() {
  const { refresh } = useNotifications();
  const [items, setItems] = useState(null);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setItems(await api.get(`/notifications/${onlyUnread ? "?unread=1" : ""}`)); setError(""); } catch (err) { setError(err.message); }
  }, [onlyUnread]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn) => { try { await fn(); await load(); refresh(); } catch (err) { setError(err.message); } };
  const markRead = (n) => !n.is_read && act(() => api.post(`/notifications/${n.id}/read/`));
  const remove = (n) => act(() => api.del(`/notifications/${n.id}/`));
  const readAll = () => act(() => api.post("/notifications/read-all/"));

  const unreadCount = items?.filter((n) => !n.is_read).length ?? 0;
  return (
    <>
      <PageHeader title="Notifications" subtitle="Annonces, mises à jour et messages qui vous concernent."
        actions={<>
          <Button variant="secondary" onClick={() => setOnlyUnread(!onlyUnread)}>{onlyUnread ? "Tout afficher" : "Non lues seulement"}</Button>
          <Button variant="secondary" disabled={!unreadCount && !onlyUnread} onClick={readAll}>Tout marquer comme lu</Button>
        </>} />
      <div className="mb-4"><Alert>{error}</Alert></div>
      {!items ? <Loading /> : items.length === 0 ? (
        <EmptyState title={onlyUnread ? "Tout est lu" : "Aucune notification"} text="Les nouvelles notifications apparaîtront ici." />
      ) : (
        <ul className="space-y-3">
          {items.map((n) => (
            <li key={n.id}>
              <Card className={cx("flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", !n.is_read && "border-brand-200 bg-brand-50/50")}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {!n.is_read && <span className="h-2 w-2 rounded-full bg-leaf-500" aria-label="Non lue" />}
                    <p className="font-medium">{n.title}</p>
                    <Badge tone={KIND[n.kind]?.tone}>{KIND[n.kind]?.text}</Badge>
                  </div>
                  {n.message && <p className="mt-1 whitespace-pre-line text-sm text-slate-600">{n.message}</p>}
                  <p className="mt-1 text-xs text-slate-500">{timeAgo(n.created_at)}</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {n.link && <Link href={n.link} onClick={() => markRead(n)} className="inline-flex items-center rounded-lg border border-brand-200 bg-white px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50">Ouvrir</Link>}
                  {!n.is_read && <Button variant="ghost" size="sm" onClick={() => markRead(n)}>Marquer comme lu</Button>}
                  <Button variant="ghost" size="sm" onClick={() => remove(n)} aria-label={`Supprimer « ${n.title} »`}>Supprimer</Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
