"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

const Ctx = createContext({ unread: 0, refresh: () => {} });
const POLL_MS = 60_000;

/** Keeps the unread counter of the bell up to date (every minute and when the tab regains focus). */
export function NotificationsProvider({ children }) {
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);

  const refresh = useCallback(async () => {
    try { setUnread((await api.get("/notifications/unread-count/")).count); } catch { /* the bell is optional */ }
  }, []);

  useEffect(() => {
    if (!user) { setUnread(0); return; }
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    const onFocus = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onFocus);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", onFocus); };
  }, [user, refresh]);

  return <Ctx.Provider value={{ unread, refresh }}>{children}</Ctx.Provider>;
}

export const useNotifications = () => useContext(Ctx);
