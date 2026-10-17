"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokens } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokens.access && !tokens.refresh) { setLoading(false); return; }
    api.get("/auth/me/").then(setUser).catch(() => tokens.clear()).finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await api.post("/auth/login/", { email: email.trim().toLowerCase(), password });
    tokens.set(data.access, data.refresh);
    setUser(data.user);
    return data.user;
  }, []);

  const register = useCallback(async (form) => {
    await api.post("/auth/register/", { ...form, email: form.email.trim().toLowerCase() });
    return login(form.email, form.password);
  }, [login]);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout/", { refresh: tokens.refresh }); } catch {}
    tokens.clear();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
